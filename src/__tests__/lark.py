"""lark 模块测试：回复、表情、富消息解析、图片下载"""

import json
import logging
from unittest.mock import MagicMock, call, patch

from src.lark import (
    add_reaction,
    remove_reaction,
    reply_message,
    resolve_rich_content,
    download_message_image,
    _extract_post_text,
    _extract_message_text,
    _resolve_inline_images,
    _convert_md_tables,
    send_to_target,
)


class TestConvertMdTables:
    """飞书不支持 markdown 表格，需转纯文本"""

    def test_basic_table(self):
        md = "| a | b |\n|---|---|\n| 1 | 2 |\n"
        result = _convert_md_tables(md)
        assert "```" in result  # 代码块包裹
        assert "a" in result
        assert "1" in result

    def test_preserves_surrounding_text(self):
        md = "前文\n\n| x | y |\n|---|---|\n| 3 | 4 |\n\n后文"
        result = _convert_md_tables(md)
        assert "前文" in result
        assert "后文" in result
        assert "3" in result

    def test_no_table_unchanged(self):
        text = "普通文字\n没有表格"
        assert _convert_md_tables(text) == text

    def test_multiple_tables(self):
        md = "| a | b |\n|---|---|\n| 1 | 2 |\n\n| x | y |\n|---|---|\n| 3 | 4 |\n"
        result = _convert_md_tables(md)
        assert "1" in result
        assert "3" in result

    def test_chinese_content_alignment(self):
        md = "| 文件 | 问题 |\n|------|------|\n| a.ts | 空渲染 |\n"
        result = _convert_md_tables(md)
        assert "文件" in result
        assert "空渲染" in result


class TestReplyMessage:
    @patch("src.lark.subprocess.run")
    def test_sends_markdown_format(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        reply_message("om_123", "**hello**")
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[:2] == ["lark-cli", "im"]
        assert "--markdown" in args
        assert "--message-id" in args
        idx = args.index("--message-id")
        assert args[idx + 1] == "om_123"
        idx = args.index("--markdown")
        assert args[idx + 1] == "**hello**"

    @patch("src.lark.subprocess.run")
    def test_truncates_long_text(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        reply_message("om_123", "x" * 20000)
        args = mock_run.call_args[0][0]
        idx = args.index("--markdown")
        sent_text = args[idx + 1]
        assert len(sent_text) < 15100
        assert "截断" in sent_text

    @patch("src.lark.subprocess.run")
    def test_fallback_to_plain_text_on_failure(self, mock_run):
        # 第一次 markdown 失败，第二次 plain text 成功
        mock_run.side_effect = [
            MagicMock(returncode=1, stderr="markdown error"),
            MagicMock(returncode=0),
        ]
        reply_message("om_123", "hello")
        assert mock_run.call_count == 2
        # 第二次调用应该用 api POST（plain text fallback）
        fallback_args = mock_run.call_args_list[1][0][0]
        assert "api" in fallback_args
        assert "POST" in fallback_args

    @patch("src.lark.subprocess.run")
    def test_logs_failure(self, mock_run, caplog):
        mock_run.return_value = MagicMock(returncode=1, stderr="API error")
        with caplog.at_level(logging.ERROR, logger="avatar"):
            reply_message("om_123", "hello")
        assert "回复消息失败" in caplog.text


# ── 富消息解析 ──────────────────────────────────────────


class TestExtractPostText:
    """飞书 post 富文本 → 纯文本"""

    def test_basic_post(self):
        post = {"zh_cn": {"title": "标题", "content": [
            [{"tag": "text", "text": "第一行"}, {"tag": "a", "text": "链接", "href": "https://x.com"}],
            [{"tag": "at", "user_name": "张三"}],
        ]}}
        result = _extract_post_text(post)
        assert "标题" in result
        assert "第一行" in result
        assert "链接" in result
        assert "@张三" in result

    def test_code_block(self):
        post = {"zh_cn": {"title": "", "content": [
            [{"tag": "code_block", "language": "python", "text": "print('hi')"}],
        ]}}
        result = _extract_post_text(post)
        assert "```python" in result
        assert "print('hi')" in result

    def test_image_and_media_placeholders(self):
        post = {"zh_cn": {"title": "", "content": [
            [{"tag": "img", "image_key": "img_xxx"}],
            [{"tag": "media", "file_key": "file_xxx"}],
        ]}}
        result = _extract_post_text(post)
        assert "[图片]" in result
        assert "[视频]" in result

    def test_empty_post(self):
        assert _extract_post_text({"zh_cn": {"title": "", "content": []}}) == ""

    def test_fallback_language(self):
        post = {"en_us": {"title": "Title", "content": [
            [{"tag": "text", "text": "English content"}],
        ]}}
        result = _extract_post_text(post)
        assert "Title" in result
        assert "English content" in result


class TestExtractMessageText:
    """单条消息 body.content → 可读文本"""

    def test_text_message(self):
        assert _extract_message_text("text", json.dumps({"text": "hello"})) == "hello"

    def test_image_message(self):
        assert _extract_message_text("image", json.dumps({"image_key": "img_xxx"})) == "[图片]"

    def test_file_message(self):
        assert "report.pdf" in _extract_message_text("file", json.dumps({"file_name": "report.pdf"}))

    def test_audio_message(self):
        assert _extract_message_text("audio", "{}") == "[语音]"

    def test_interactive_card_with_title(self):
        content = json.dumps({"header": {"title": {"content": "卡片标题"}}})
        result = _extract_message_text("interactive", content)
        assert "卡片标题" in result

    def test_unknown_type(self):
        result = _extract_message_text("share_calendar", "{}")
        assert "share_calendar" in result

    def test_empty_content(self):
        result = _extract_message_text("text", "")
        assert "text" in result


class TestResolveRichContent:
    """resolve_rich_content 入口函数"""

    def test_text_returns_none(self):
        """纯文本消息不需要解析"""
        assert resolve_rich_content({"message_type": "text", "content": "你好", "message_id": "om_1"}) is None

    def test_plain_content_no_images_returns_none(self):
        """不含图片的普通内容不需要解析"""
        assert resolve_rich_content({"message_type": "", "content": "普通消息", "message_id": "om_1"}) is None

    @patch("src.lark._fetch_merge_forward_content")
    def test_merge_forward_by_type(self, mock_fetch):
        mock_fetch.return_value = "展开的内容"
        result = resolve_rich_content({
            "message_type": "merge_forward", "content": "[Merged forward]", "message_id": "om_1",
        })
        assert "[合并转发消息]" in result
        assert "展开的内容" in result

    @patch("src.lark._fetch_merge_forward_content")
    def test_merge_forward_by_content_marker(self, mock_fetch):
        """compact 可能不给 message_type，靠 content 标记识别"""
        mock_fetch.return_value = "子消息内容"
        result = resolve_rich_content({
            "message_type": "", "content": "Merged and Forwarded Message", "message_id": "om_1",
        })
        assert "子消息内容" in result

    @patch("src.lark.download_message_image", return_value="data/images/test.png")
    @patch("src.lark._get_message_image_key", return_value="img_v3_test")
    def test_image_message(self, mock_key, mock_dl):
        result = resolve_rich_content({
            "message_type": "image", "content": "", "message_id": "om_1",
        })
        assert "图片" in result
        mock_key.assert_called_once_with("om_1")
        mock_dl.assert_called_once_with("om_1", "img_v3_test")

    @patch("src.lark._get_message_image_key", return_value=None)
    def test_image_message_no_key(self, mock_key):
        result = resolve_rich_content({
            "message_type": "image", "content": "", "message_id": "om_1",
        })
        assert "无法下载" in result

    def test_audio_message(self):
        assert resolve_rich_content({"message_type": "audio", "content": "", "message_id": "om_1"}) == "[语音消息]"

    def test_file_message(self):
        result = resolve_rich_content({"message_type": "file", "content": "doc.pdf", "message_id": "om_1"})
        assert "doc.pdf" in result

    @patch("src.lark._resolve_inline_images")
    def test_inline_images_catchall(self, mock_resolve):
        """post 消息内含 [Image: img_xxx] 应被兜底处理"""
        mock_resolve.return_value = "文字 [图片已下载: /tmp/img.png]"
        result = resolve_rich_content({
            "message_type": "",
            "content": "文字 [Image: img_v3_test_key]",
            "message_id": "om_1",
        })
        assert "图片已下载" in result
        mock_resolve.assert_called_once()

    def test_inline_images_catchall_no_match(self):
        """内容不含 [Image:] 时不触发兜底"""
        result = resolve_rich_content({
            "message_type": "",
            "content": "普通文字 没有图片",
            "message_id": "om_1",
        })
        assert result is None


class TestResolveInlineImages:
    """_resolve_inline_images: [Image: xxx] 占位符替换"""

    @patch("src.lark.download_message_image")
    def test_replaces_single_image(self, mock_dl):
        mock_dl.return_value = "data/images/img_test.png"
        text = "before [Image: img_v3_test] after"
        result = _resolve_inline_images("om_1", text)
        assert "[Image:" not in result
        assert "图片已下载" in result
        assert "before" in result
        assert "after" in result

    @patch("src.lark.download_message_image")
    def test_replaces_multiple_images(self, mock_dl):
        mock_dl.return_value = "data/images/test.png"
        text = "[Image: img_v3_a] 中间 [Image: img_v3_b]"
        result = _resolve_inline_images("om_1", text)
        assert result.count("图片已下载") == 2
        assert "中间" in result

    @patch("src.lark.download_message_image", return_value=None)
    def test_download_failure_shows_fallback(self, mock_dl):
        text = "[Image: img_v3_fail]"
        result = _resolve_inline_images("om_1", text)
        assert "下载失败" in result

    def test_no_images_returns_unchanged(self):
        text = "no images here"
        assert _resolve_inline_images("om_1", text) == text


class TestDownloadMessageImage:
    """download_message_image: lark-cli 图片下载"""

    @patch("src.lark.subprocess.run")
    def test_successful_download(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=0)
        with patch("src.lark._IMAGES_DIR", tmp_path), patch("src.lark.ROOT", tmp_path.parent):
            result = download_message_image("om_1", "img_v3_test")
        assert result is not None
        assert "img_v3_test" in result

    @patch("src.lark.subprocess.run")
    def test_download_failure_returns_none(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stderr="error")
        result = download_message_image("om_1", "img_v3_fail")
        assert result is None

    @patch("src.lark.subprocess.run")
    def test_cached_file_skips_download(self, mock_run, tmp_path):
        """已下载的文件不重复请求"""
        img = tmp_path / "img_v3_cached.png"
        img.write_bytes(b"fake png data")
        with patch("src.lark._IMAGES_DIR", tmp_path):
            result = download_message_image("om_1", "img_v3_cached")
        mock_run.assert_not_called()
        assert result is not None


class TestAddReaction:
    @patch("src.lark.subprocess.run")
    def test_returns_reaction_id(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"data": {"reaction_id": "r_abc"}})
        )
        assert add_reaction("om_123") == "r_abc"

    @patch("src.lark.subprocess.run")
    def test_returns_none_on_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        assert add_reaction("om_123") is None


class TestRemoveReaction:
    @patch("src.lark.subprocess.run")
    def test_logs_failure(self, mock_run, caplog):
        mock_run.return_value = MagicMock(returncode=1, stderr="not found")
        with caplog.at_level(logging.ERROR, logger="avatar"):
            remove_reaction("om_123", "r_abc")
        assert "移除表情失败" in caplog.text


# ── send_to_target 测试 ──────────────────────────────────────────

class TestSendToTarget:
    """send_to_target: 主动发消息到指定 chat_id / open_id"""

    @patch("src.lark.subprocess.run")
    def test_send_to_target_open_id(self, mock_run):
        """target_id=ou_xxx → 使用 --user-id ou_xxx（+messages-send）"""
        mock_run.return_value = MagicMock(returncode=0)
        send_to_target("ou_xxx", "hello")
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        # 必须使用正确子命令
        assert "+messages-send" in args
        # 用户 ID 通过 --user-id 传递，不是 --params
        assert "--user-id" in args
        idx = args.index("--user-id")
        assert args[idx + 1] == "ou_xxx"
        # 不应含旧的 --params 参数
        assert "--params" not in args

    @patch("src.lark.subprocess.run")
    def test_send_to_target_chat_id(self, mock_run):
        """target_id=oc_xxx → 使用 --chat-id oc_xxx（+messages-send）"""
        mock_run.return_value = MagicMock(returncode=0)
        send_to_target("oc_xxx", "hello")
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        # 必须使用正确子命令
        assert "+messages-send" in args
        # 群 chat_id 通过 --chat-id 传递
        assert "--chat-id" in args
        idx = args.index("--chat-id")
        assert args[idx + 1] == "oc_xxx"
        # 不应含旧的 --params 参数
        assert "--params" not in args

    @patch("src.lark.subprocess.run")
    def test_send_to_target_truncates_long_text(self, mock_run):
        """>15000 字符触发截断"""
        mock_run.return_value = MagicMock(returncode=0)
        send_to_target("ou_xxx", "x" * 20000)
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        # 文本通过 --text 参数传递
        idx = args.index("--text")
        sent_text = args[idx + 1]
        assert len(sent_text) < 15100
        assert "截断" in sent_text

    @patch("src.lark._convert_md_tables")
    @patch("src.lark.subprocess.run")
    def test_send_to_target_converts_md_tables(self, mock_run, mock_convert):
        """复用 _convert_md_tables（helper 被调用）"""
        mock_run.return_value = MagicMock(returncode=0)
        mock_convert.return_value = "converted"
        send_to_target("ou_xxx", "| a | b |\n|---|---|\n| 1 | 2 |\n")
        mock_convert.assert_called_once()

    @patch("src.lark.subprocess.run")
    def test_send_to_target_logs_on_failure(self, mock_run, caplog):
        """subprocess returncode!=0 → log_error 调用，不抛"""
        mock_run.return_value = MagicMock(returncode=1, stderr="api error")
        with caplog.at_level(logging.ERROR, logger="avatar"):
            send_to_target("ou_xxx", "hello")  # 不应抛出异常
        assert "发送消息失败" in caplog.text

    @patch("src.lark._convert_md_tables")
    @patch("src.lark.subprocess.run")
    def test_reply_message_still_uses_shared_helper(self, mock_run, mock_convert):
        """reply_message 抽出 _prepare_markdown_text helper 后行为不退化"""
        mock_run.return_value = MagicMock(returncode=0)
        mock_convert.return_value = "converted"
        reply_message("om_123", "| a | b |\n|---|---|\n| 1 | 2 |\n")
        # _convert_md_tables 必须被调用（shared helper 路径）
        mock_convert.assert_called_once()
