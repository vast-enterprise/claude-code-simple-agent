"""飞书交互：消息回复、表情反馈"""

import json
import subprocess

from src.config import log_error


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
