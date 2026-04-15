"""飞书交互：消息回复、表情反馈、富消息解析、图片下载"""

from __future__ import annotations

import json
import os
import re
import subprocess

from src.config import ROOT, log_debug, log_error

# 图片存储目录
_IMAGES_DIR = ROOT / "data" / "images"


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
_IMAGE_KEY_PATTERN = re.compile(r"\[Image: (img_[^\]]+)\]")


def download_message_image(message_id: str, image_key: str) -> str | None:
    """下载消息中的图片到本地，返回相对路径。失败返回 None。"""
    os.makedirs(_IMAGES_DIR, exist_ok=True)
    # 用 image_key 作文件名（去掉不安全字符）
    safe_name = re.sub(r"[^a-zA-Z0-9_\-]", "_", image_key) + ".png"
    rel_path = f"data/images/{safe_name}"

    # 如果已下载过，直接返回
    full_path = _IMAGES_DIR / safe_name
    if full_path.exists() and full_path.stat().st_size > 0:
        return rel_path

    result = subprocess.run(
        [
            "lark-cli", "im", "+messages-resources-download",
            "--message-id", message_id,
            "--file-key", image_key,
            "--type", "image",
            "--output", rel_path,
            "--as", "bot",
        ],
        capture_output=True, text=True, timeout=30,
        cwd=str(ROOT),
    )
    if result.returncode != 0:
        log_error(f"下载图片失败 ({image_key}): {result.stderr[:200]}")
        return None

    log_debug(f"图片已下载: {rel_path}")
    return rel_path


def _get_message_image_key(message_id: str) -> str | None:
    """通过 API 获取 image 消息的 image_key"""
    result = subprocess.run(
        [
            "lark-cli", "api", "GET",
            f"/open-apis/im/v1/messages/{message_id}",
            "--as", "bot", "--format", "json",
        ],
        capture_output=True, text=True, timeout=15,
    )
    if result.returncode != 0:
        return None
    try:
        resp = json.loads(result.stdout)
        items = resp.get("data", {}).get("items", [])
        for item in items:
            if item.get("msg_type") == "image":
                content = json.loads(item.get("body", {}).get("content", "{}"))
                return content.get("image_key")
    except (json.JSONDecodeError, KeyError):
        pass
    return None


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


def _resolve_inline_images(message_id: str, text: str) -> str:
    """解析文本中的 [Image: img_xxx] 占位符，下载图片并替换为文件路径引用。"""
    image_keys = _IMAGE_KEY_PATTERN.findall(text)
    if not image_keys:
        return text

    for image_key in image_keys:
        path = download_message_image(message_id, image_key)
        if path:
            full_path = _IMAGES_DIR / (re.sub(r"[^a-zA-Z0-9_\-]", "_", image_key) + ".png")
            text = text.replace(
                f"[Image: {image_key}]",
                f"[图片已下载: {full_path}]",
            )
        else:
            text = text.replace(
                f"[Image: {image_key}]",
                f"[图片: {image_key} (下载失败)]",
            )

    return text


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
    if not content.strip():
        return None

    # 下载文本中的 [Image: img_xxx] 图片
    content = _resolve_inline_images(message_id, content)
    return content.strip()


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

    # 2. 单张图片消息
    if message_type == "image":
        if not message_id:
            return "[图片消息]"
        image_key = _get_message_image_key(message_id)
        if image_key:
            path = download_message_image(message_id, image_key)
            if path:
                full_path = _IMAGES_DIR / (re.sub(r"[^a-zA-Z0-9_\-]", "_", image_key) + ".png")
                return f"[图片消息，已下载到: {full_path}]"
        return "[图片消息: 无法下载]"
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

    # 兜底：任何消息内容中含 [Image: img_xxx] 占位符时，下载图片并替换
    # 覆盖场景：post 消息里的内联图片、compact 格式生成的图片占位符
    if message_id and _IMAGE_KEY_PATTERN.search(content):
        resolved = _resolve_inline_images(message_id, content)
        if resolved != content:
            return resolved

    # 纯文本 / 无图片的 post / interactive 等，不需要额外解析
    return None


_MD_TABLE_PATTERN = re.compile(
    r"(?:^|\n)"                         # 表格前：行首或换行
    r"(\|[^\n]+\|\n)"                   # 表头行
    r"(\|[\s:]*-+[\s:]*(?:\|[\s:]*-+[\s:]*)*\|\n)"  # 分隔行
    r"((?:\|[^\n]+\|\n?)+)",            # 数据行（1+行）
    re.MULTILINE,
)


def _md_table_to_text(match: re.Match) -> str:
    """将一个 markdown 表格转为代码块包裹的对齐文本（飞书 md tag 不支持表格）"""
    header_line = match.group(1).strip()
    data_block = match.group(3).strip()

    def parse_row(line: str) -> list[str]:
        cells = line.strip().strip("|").split("|")
        return [c.strip() for c in cells]

    headers = parse_row(header_line)
    rows = [parse_row(line) for line in data_block.split("\n") if line.strip()]

    # 计算每列最大宽度（中文字符算 2 宽度）
    def display_width(s: str) -> int:
        w = 0
        for ch in s:
            w += 2 if ord(ch) > 0x7F else 1
        return w

    all_rows = [headers] + rows
    col_count = max(len(r) for r in all_rows)
    for r in all_rows:
        while len(r) < col_count:
            r.append("")

    widths = [max(display_width(r[i]) for r in all_rows) for i in range(col_count)]

    def pad_cell(s: str, width: int) -> str:
        padding = width - display_width(s)
        return s + " " * max(0, padding)

    lines = []
    lines.append(" | ".join(pad_cell(headers[i], widths[i]) for i in range(col_count)))
    lines.append(" | ".join("-" * widths[i] for i in range(col_count)))
    for row in rows:
        lines.append(" | ".join(pad_cell(row[i], widths[i]) for i in range(col_count)))

    return "\n```\n" + "\n".join(lines) + "\n```\n"


def _convert_md_tables(text: str) -> str:
    """将文本中所有 markdown 表格转为纯文本对齐格式"""
    return _MD_TABLE_PATTERN.sub(_md_table_to_text, text)


def reply_message(message_id: str, text: str):
    """通过 lark-cli 回复飞书消息（markdown 富文本格式）"""
    if len(text) > 15000:
        text = text[:14950] + "\n\n...(回复过长，已截断)"

    # 飞书 md tag 不支持表格，发送前转为纯文本格式
    text = _convert_md_tables(text)

    result = subprocess.run(
        [
            "lark-cli", "im", "+messages-reply",
            "--message-id", message_id,
            "--markdown", text,
            "--as", "bot",
        ],
        capture_output=True, text=True, timeout=15,
    )
    if result.returncode != 0:
        log_error(f"回复消息失败(markdown): {result.stderr[:200]}")
        # fallback: 如果 markdown 回复失败，降级为纯文本
        _reply_plain_text(message_id, text)


def _reply_plain_text(message_id: str, text: str):
    """纯文本回复（markdown 失败时的降级方案）"""
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
        log_error(f"回复消息失败(fallback): {result.stderr[:200]}")
