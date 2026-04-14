"""飞书交互：消息回复、表情反馈、富消息解析"""

from __future__ import annotations

import json
import subprocess

from src.config import log_debug, log_error


def add_reaction(message_id: str, emoji_type: str = "OnIt") -> str | None:
    """给消息打表情回复，返回 reaction_id 用于后续删除"""
    params = json.dumps({"message_id": message_id})
    data = json.dumps({"reaction_type": {"emoji_type": emoji_type}})
    result = subprocess.run(
        [
            "lark-cli", "im", "reactions", "create",
            "--params", params, "--data", data, "--as", "bot",
        ],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode == 0:
        try:
            resp = json.loads(result.stdout)
            return resp.get("data", {}).get("reaction_id")
        except (json.JSONDecodeError, KeyError):
            pass
    return None


def remove_reaction(message_id: str, reaction_id: str):
    """移除消息上的表情回复"""
    params = json.dumps({"message_id": message_id, "reaction_id": reaction_id})
    result = subprocess.run(
        [
            "lark-cli", "im", "reactions", "delete",
            "--params", params, "--as", "bot",
        ],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode != 0:
        log_error(f"移除表情失败: {result.stderr[:200]}")


def resolve_user_name(open_id: str) -> str | None:
    """通过 lark-cli 解析 open_id 为用户名，失败返回 None"""
    result = subprocess.run(
        [
            "lark-cli", "contact", "+get-user",
            "--user-id", open_id, "--user-id-type", "open_id",
            "--as", "bot", "-q", ".data.user.name",
        ],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    return None


def resolve_chat_name(chat_id: str) -> str | None:
    """通过 lark-cli 解析 chat_id 为群名，失败返回 None"""
    params = json.dumps({"chat_id": chat_id})
    result = subprocess.run(
        [
            "lark-cli", "im", "chats", "get",
            "--params", params, "--as", "bot", "-q", ".data.name",
        ],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    return None


# ---------------------------------------------------------------------------
# 富消息解析：merge_forward / image / file / audio / video / sticker
# ---------------------------------------------------------------------------

_MERGE_FORWARD_MARKERS = ("[Merged forward]", "Merged and Forwarded Message")


def _extract_post_text(content: dict) -> str:
    """从 post 富文本结构中提取纯文本"""
    lines: list[str] = []
    # post 外层按语言包一层，取第一个语言
    inner = content
    if "zh_cn" in content:
        inner = content["zh_cn"]
    elif "en_us" in content:
        inner = content["en_us"]
    elif "ja_jp" in content:
        inner = content["ja_jp"]

    title = inner.get("title", "")
    if title:
        lines.append(title)

    for paragraph in inner.get("content", []):
        parts: list[str] = []
        for elem in paragraph:
            tag = elem.get("tag", "")
            if tag in ("text", "a"):
                parts.append(elem.get("text", ""))
            elif tag == "at":
                parts.append(f"@{elem.get('user_name', elem.get('user_id', ''))}")
            elif tag == "emotion":
                parts.append(f"[{elem.get('emoji_type', 'emoji')}]")
            elif tag == "code_block":
                lang = elem.get("language", "")
                code = elem.get("text", "")
                parts.append(f"```{lang}\n{code}\n```")
            elif tag == "img":
                parts.append("[图片]")
            elif tag == "media":
                parts.append("[视频]")
        lines.append("".join(parts))

    return "\n".join(lines)


def _extract_message_text(msg_type: str, content_str: str) -> str:
    """从单条消息的 body.content 提取可读文本"""
    if not content_str:
        return f"[{msg_type}消息]"

    try:
        content = json.loads(content_str)
    except json.JSONDecodeError:
        return content_str

    if msg_type == "text":
        return content.get("text", "")
    if msg_type == "post":
        return _extract_post_text(content)
    if msg_type == "image":
        return "[图片]"
    if msg_type == "file":
        return f"[文件: {content.get('file_name', '未知')}]"
    if msg_type == "audio":
        return "[语音]"
    if msg_type == "video":
        return "[视频]"
    if msg_type == "sticker":
        return "[表情包]"
    if msg_type == "interactive":
        # 卡片消息，尽量提取标题
        title = content.get("header", {}).get("title", {}).get("content", "")
        return f"[卡片: {title}]" if title else "[卡片消息]"
    return f"[{msg_type}消息]"


def _fetch_merge_forward_content(message_id: str) -> str | None:
    """用 lark-cli +messages-mget 获取合并转发的已展开文本内容。

    lark-cli 内置了 merge_forward 展开，返回 <forwarded_messages>…</forwarded_messages>
    格式的可读文本，比手动调 API 逐条解析子消息更可靠。
    """
    result = subprocess.run(
        [
            "lark-cli", "im", "+messages-mget",
            "--message-ids", message_id,
            "--as", "bot", "--format", "json",
        ],
        capture_output=True, text=True, timeout=15,
    )
    if result.returncode != 0:
        log_error(f"获取合并转发消息失败: {result.stderr[:200]}")
        return None

    try:
        resp = json.loads(result.stdout)
        messages = resp.get("data", {}).get("messages", [])
    except (json.JSONDecodeError, KeyError):
        log_error(f"解析合并转发响应失败: {result.stdout[:200]}")
        return None

    if not messages:
        return None

    # +messages-mget 对 merge_forward 返回的 content 已是展开的文本
    content = messages[0].get("content", "")
    return content.strip() if content.strip() else None


def resolve_rich_content(event: dict) -> str | None:
    """解析非纯文本消息类型，返回可读文本。纯文本返回 None（不需要解析）。"""
    message_type = event.get("message_type", "")
    content = event.get("content", "").strip()
    message_id = event.get("message_id", "")

    # 1. merge_forward：通过 message_type 或内容标记检测
    if message_type == "merge_forward" or content in _MERGE_FORWARD_MARKERS:
        if not message_id:
            return None
        expanded = _fetch_merge_forward_content(message_id)
        if expanded:
            log_debug(f"合并转发消息已展开: {len(expanded)} chars")
            return f"[合并转发消息]\n{expanded}"
        return "[合并转发消息: 无法获取子消息内容]"

    # 2. 其他富媒体类型
    if message_type == "image":
        return "[图片消息]"
    if message_type == "file":
        return f"[文件消息: {content}]" if content else "[文件消息]"
    if message_type == "audio":
        return "[语音消息]"
    if message_type == "video":
        return "[视频消息]"
    if message_type == "sticker":
        return "[表情包消息]"
    if message_type == "media":
        return "[媒体消息]"

    # 纯文本 / post / interactive 等已由 compact 提取了文字，不需要额外解析
    return None


def reply_message(message_id: str, text: str):
    """通过 lark-cli 回复飞书消息"""
    if len(text) > 4000:
        text = text[:3950] + "\n\n...(回复过长，已截断)"

    data = json.dumps({"msg_type": "text", "content": json.dumps({"text": text})})
    result = subprocess.run(
        [
            "lark-cli", "api", "POST",
            f"/open-apis/im/v1/messages/{message_id}/reply",
            "--data", data, "--as", "bot", "--format", "data",
        ],
        capture_output=True, text=True, timeout=15,
    )
    if result.returncode != 0:
        log_error(f"回复消息失败: {result.stderr[:200]}")
