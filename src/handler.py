"""消息过滤与处理"""

from claude_agent_sdk import ClaudeSDKClient
from claude_agent_sdk.types import AssistantMessage, ResultMessage, TextBlock

import src.permissions as permissions
from src.config import OWNER_ID, BOT_NAME
from src.lark import add_reaction, remove_reaction, reply_message

BOT_MENTION = f"@{BOT_NAME}"


def compute_session_id(event: dict) -> str:
    """根据事件计算 session ID：P2P 按用户，群聊按群+用户"""
    chat_type = event.get("chat_type", "p2p")
    sender_id = event.get("sender_id", "")
    chat_id = event.get("chat_id", "unknown")
    if chat_type == "p2p":
        return f"p2p_{sender_id}"
    return f"group_{chat_id}_{sender_id}"


def should_respond(event: dict) -> bool:
    """判断是否应该响应这条消息"""
    if event.get("sender_type") == "bot":
        return False

    chat_type = event.get("chat_type", "")
    content = event.get("content", "")

    if chat_type == "p2p":
        return True

    if chat_type == "group":
        if BOT_MENTION in content:
            return True

    return False


async def handle_message(client: ClaudeSDKClient, event: dict):
    """处理单条飞书消息"""
    content = event.get("content", "").strip()
    message_id = event.get("message_id", "")
    sender_id = event.get("sender_id", "")
    chat_type = event.get("chat_type", "p2p")

    if not content or not message_id:
        return

    content = content.replace(BOT_MENTION, "").strip()

    permissions.set_sender(sender_id)

    sender_label = "所有者" if sender_id == OWNER_ID else "同事"
    prompt = f"[{sender_label}] 在{'群聊' if chat_type == 'group' else '私聊'}中说：{content}"

    session_id = compute_session_id(event)
    await client.query(prompt, session_id=session_id)

    # 收集回复，首条消息到达时打表情表示"正在处理"
    reply_text = ""
    reaction_id = None
    async for msg in client.receive_response():
        if isinstance(msg, AssistantMessage):
            if reaction_id is None:
                reaction_id = add_reaction(message_id)
            for block in msg.content:
                if isinstance(block, TextBlock):
                    reply_text += block.text
        elif isinstance(msg, ResultMessage):
            if msg.is_error and not reply_text:
                reply_text = "抱歉，处理时出了点问题。"
            break

    # 处理完成，移除"正在处理"表情
    if reaction_id:
        remove_reaction(message_id, reaction_id)

    if reply_text.strip():
        reply_message(message_id, reply_text.strip())
