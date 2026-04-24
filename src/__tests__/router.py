# src/__tests__/router.py
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.router import (
    _compute_base_session_id,
    _compute_full_session_id,
    _extract_suffix_from_session_id,
)


def test_compute_base_session_id_p2p():
    event = {"chat_type": "p2p", "sender_id": "ou_123"}
    assert _compute_base_session_id(event) == "p2p_ou_123"


def test_compute_base_session_id_group():
    event = {"chat_type": "group", "chat_id": "oc_abc", "sender_id": "ou_123"}
    assert _compute_base_session_id(event) == "group_oc_abc_ou_123"


def test_compute_full_session_id_with_suffix():
    assert _compute_full_session_id("p2p_ou_123", "cms") == "p2p_ou_123_cms"


def test_compute_full_session_id_without_suffix():
    assert _compute_full_session_id("p2p_ou_123", None) == "p2p_ou_123"


def test_extract_suffix_from_session_id():
    assert _extract_suffix_from_session_id("p2p_ou_123_cms", "p2p_ou_123") == "cms"


def test_extract_suffix_returns_none_for_base():
    assert _extract_suffix_from_session_id("p2p_ou_123", "p2p_ou_123") is None


# === route_message 路由测试 ===

from src.router import route_message


def run_async(coro):
    return asyncio.run(coro)


def _make_event(content="hello", sender_id="ou_123", chat_type="p2p"):
    return {
        "content": content,
        "message_id": "om_test",
        "sender_id": sender_id,
        "chat_type": chat_type,
        "sender_type": "user",
    }


def _make_mocks():
    pool = MagicMock()
    pool.get = AsyncMock()
    pool.list_sessions = MagicMock(return_value={})
    pool.remove = AsyncMock(return_value=True)
    pool.get_client = MagicMock(return_value=None)

    dispatcher = MagicMock()
    dispatcher.dispatch = AsyncMock()
    dispatcher.cancel_reader = MagicMock()

    defaults = MagicMock()
    defaults.get_default = MagicMock(return_value=None)
    defaults.set_default = MagicMock()
    defaults.remove_user = MagicMock()

    return pool, dispatcher, defaults


# === /new ===


@patch("src.router.resolve_rich_content", return_value=None)
@patch("src.router.reply_message")
def test_new_command_dispatches(mock_reply, mock_rich):
    pool, dispatcher, defaults = _make_mocks()
    event = _make_event(content="/new cms翻译 查查这个需求")
    run_async(route_message(pool, event, dispatcher, defaults))
    dispatcher.dispatch.assert_called_once()
    assert dispatcher.dispatch.call_args[0][0] == "p2p_ou_123_cms翻译"


@patch("src.router.resolve_rich_content", return_value=None)
@patch("src.router.reply_message")
def test_new_command_dispatches_group_chat(mock_reply, mock_rich):
    pool, dispatcher, defaults = _make_mocks()
    event = {
        "message_id": "om_123",
        "chat_type": "group",
        "chat_id": "oc_456",
        "sender": {"sender_id": {"open_id": "ou_123"}},
        "content": "/new cms翻译 查查这个需求",
    }
    run_async(route_message(pool, event, dispatcher, defaults))
    dispatcher.dispatch.assert_called_once()
    # verify group chat session routing works as expected
    assert dispatcher.dispatch.call_args[0][0] == "group_oc_456_ou_123_cms翻译"


@patch("src.router.resolve_rich_content", return_value=None)
@patch("src.router.reply_message")
def test_new_command_missing_suffix(mock_reply, mock_rich):
    pool, dispatcher, defaults = _make_mocks()
    event = _make_event(content="/new")
    run_async(route_message(pool, event, dispatcher, defaults))
    mock_reply.assert_called_once()
    assert "用法" in mock_reply.call_args[0][1]
    dispatcher.dispatch.assert_not_called()


@patch("src.router.resolve_rich_content", return_value=None)
@patch("src.router.reply_message")
def test_new_command_missing_message(mock_reply, mock_rich):
    pool, dispatcher, defaults = _make_mocks()
    event = _make_event(content="/new cms翻译")
    run_async(route_message(pool, event, dispatcher, defaults))
    mock_reply.assert_called_once()
    assert "用法" in mock_reply.call_args[0][1]


# === $suffix ===


@patch("src.router.resolve_rich_content", return_value=None)
@patch("src.router.reply_message")
def test_dollar_prefix_routes_to_suffix(mock_reply, mock_rich):
    pool, dispatcher, defaults = _make_mocks()
    pool.list_sessions = MagicMock(return_value={
        "p2p_ou_123_cms": {"created_at": "2026-04-23T10:00:00"}
    })
    event = _make_event(content="$cms 帮我查一下")
    run_async(route_message(pool, event, dispatcher, defaults))
    dispatcher.dispatch.assert_called_once()
    mock_reply.assert_not_called()


@patch("src.router.resolve_rich_content", return_value=None)
@patch("src.router.reply_message")
def test_dollar_prefix_nonexistent_session(mock_reply, mock_rich):
    pool, dispatcher, defaults = _make_mocks()
    event = _make_event(content="$不存在 消息")
    run_async(route_message(pool, event, dispatcher, defaults))
    mock_reply.assert_called_once()
    assert "不存在" in mock_reply.call_args[0][1]
    dispatcher.dispatch.assert_not_called()


# === /switch ===


@patch("src.router.resolve_rich_content", return_value=None)
@patch("src.router.reply_message")
def test_switch_to_existing_suffix(mock_reply, mock_rich):
    pool, dispatcher, defaults = _make_mocks()
    pool.list_sessions = MagicMock(return_value={
        "p2p_ou_123_cms": {"created_at": "2026-04-23T10:00:00"}
    })
    event = _make_event(content="/switch cms")
    run_async(route_message(pool, event, dispatcher, defaults))
    defaults.set_default.assert_called_once_with("p2p_ou_123", "cms")
    mock_reply.assert_called_once()
    assert "已切换" in mock_reply.call_args[0][1]


@patch("src.router.resolve_rich_content", return_value=None)
@patch("src.router.reply_message")
def test_switch_to_original_session(mock_reply, mock_rich):
    pool, dispatcher, defaults = _make_mocks()
    event = _make_event(content="/switch")
    run_async(route_message(pool, event, dispatcher, defaults))
    defaults.set_default.assert_called_once_with("p2p_ou_123", None)
    assert "原始会话" in mock_reply.call_args[0][1]


@patch("src.router.resolve_rich_content", return_value=None)
@patch("src.router.reply_message")
def test_switch_to_nonexistent_suffix(mock_reply, mock_rich):
    pool, dispatcher, defaults = _make_mocks()
    event = _make_event(content="/switch 不存在")
    run_async(route_message(pool, event, dispatcher, defaults))
    defaults.set_default.assert_not_called()
    assert "不存在" in mock_reply.call_args[0][1]


# === 普通消息 ===


@patch("src.router.resolve_rich_content", return_value=None)
@patch("src.router.reply_message")
def test_normal_message_goes_to_default_session(mock_reply, mock_rich):
    pool, dispatcher, defaults = _make_mocks()
    event = _make_event(content="hello world")
    run_async(route_message(pool, event, dispatcher, defaults))
    dispatcher.dispatch.assert_called_once()


@patch("src.router.resolve_rich_content", return_value=None)
@patch("src.router.reply_message")
def test_normal_message_uses_switched_default(mock_reply, mock_rich):
    pool, dispatcher, defaults = _make_mocks()
    defaults.get_default = MagicMock(return_value="cms")
    event = _make_event(content="hello")
    run_async(route_message(pool, event, dispatcher, defaults))
    dispatcher.dispatch.assert_called_once()
    call_args = dispatcher.dispatch.call_args[0]
    assert call_args[0] == "p2p_ou_123_cms"  # session_id


# === /sessions ===


@patch("src.router.resolve_rich_content", return_value=None)
@patch("src.router.reply_message")
def test_sessions_lists_user_sessions(mock_reply, mock_rich):
    pool, dispatcher, defaults = _make_mocks()
    pool.list_sessions = MagicMock(return_value={
        "p2p_ou_123": {"created_at": "2026-04-23T09:00:00"},
        "p2p_ou_123_cms": {"created_at": "2026-04-23T10:00:00"},
        "p2p_ou_other": {"created_at": "2026-04-23T11:00:00"},  # 别人的
    })
    event = _make_event(content="/sessions")
    run_async(route_message(pool, event, dispatcher, defaults))
    mock_reply.assert_called_once()
    text = mock_reply.call_args[0][1]
    assert "原始会话" in text
    assert "cms" in text
    assert "ou_other" not in text  # 不应包含别人的会话


@patch("src.router.resolve_rich_content", return_value=None)
@patch("src.router.reply_message")
def test_sessions_empty(mock_reply, mock_rich):
    pool, dispatcher, defaults = _make_mocks()
    event = _make_event(content="/sessions")
    run_async(route_message(pool, event, dispatcher, defaults))
    mock_reply.assert_called_once()
    assert "没有" in mock_reply.call_args[0][1]


# === /clear ===


@patch("src.router.resolve_rich_content", return_value=None)
@patch("src.router.reply_message")
def test_clear_specific_suffix(mock_reply, mock_rich):
    pool, dispatcher, defaults = _make_mocks()
    pool.list_sessions = MagicMock(return_value={
        "p2p_ou_123_cms": {"created_at": "2026-04-23T10:00:00"},
    })
    pool.remove = AsyncMock(return_value=True)
    event = _make_event(content="/clear cms")
    run_async(route_message(pool, event, dispatcher, defaults))
    dispatcher.cancel_reader.assert_called_once_with("p2p_ou_123_cms")
    pool.remove.assert_called_once_with("p2p_ou_123_cms")
    assert "已清除" in mock_reply.call_args[0][1]


@patch("src.router.resolve_rich_content", return_value=None)
@patch("src.router.reply_message")
def test_clear_nonexistent_session(mock_reply, mock_rich):
    pool, dispatcher, defaults = _make_mocks()
    event = _make_event(content="/clear 不存在")
    run_async(route_message(pool, event, dispatcher, defaults))
    pool.remove.assert_not_called()
    assert "不存在" in mock_reply.call_args[0][1]


@patch("src.router.resolve_rich_content", return_value=None)
@patch("src.router.reply_message")
def test_clear_resets_default_if_clearing_default(mock_reply, mock_rich):
    pool, dispatcher, defaults = _make_mocks()
    defaults.get_default = MagicMock(return_value="cms")
    pool.list_sessions = MagicMock(return_value={
        "p2p_ou_123_cms": {"created_at": "2026-04-23T10:00:00"},
    })
    pool.remove = AsyncMock(return_value=True)
    event = _make_event(content="/clear cms")
    run_async(route_message(pool, event, dispatcher, defaults))
    defaults.set_default.assert_called_once_with("p2p_ou_123", None)


@patch("src.router.resolve_rich_content", return_value=None)
@patch("src.router.reply_message")
def test_clear_no_arg_clears_current_default(mock_reply, mock_rich):
    pool, dispatcher, defaults = _make_mocks()
    defaults.get_default = MagicMock(return_value="cms")
    pool.list_sessions = MagicMock(return_value={
        "p2p_ou_123_cms": {"created_at": "2026-04-23T10:00:00"},
    })
    pool.remove = AsyncMock(return_value=True)
    event = _make_event(content="/clear")
    run_async(route_message(pool, event, dispatcher, defaults))
    pool.remove.assert_called_once_with("p2p_ou_123_cms")
    defaults.set_default.assert_called_once_with("p2p_ou_123", None)


# === /clear-all ===


@patch("src.router.resolve_rich_content", return_value=None)
@patch("src.router.reply_message")
def test_clear_all_removes_all_user_sessions(mock_reply, mock_rich):
    pool, dispatcher, defaults = _make_mocks()
    pool.list_sessions = MagicMock(return_value={
        "p2p_ou_123": {"created_at": "2026-04-23T09:00:00"},
        "p2p_ou_123_cms": {"created_at": "2026-04-23T10:00:00"},
        "p2p_ou_other": {"created_at": "2026-04-23T11:00:00"},
    })
    pool.remove = AsyncMock(return_value=True)
    event = _make_event(content="/clear-all")
    run_async(route_message(pool, event, dispatcher, defaults))
    # 只清除 ou_123 的两个会话
    assert pool.remove.call_count == 2
    defaults.remove_user.assert_called_once_with("p2p_ou_123")
    assert "2" in mock_reply.call_args[0][1]


@patch("src.router.resolve_rich_content", return_value=None)
@patch("src.router.reply_message")
def test_clear_all_empty(mock_reply, mock_rich):
    pool, dispatcher, defaults = _make_mocks()
    event = _make_event(content="/clear-all")
    run_async(route_message(pool, event, dispatcher, defaults))
    pool.remove.assert_not_called()
    assert "没有" in mock_reply.call_args[0][1]


# === /interrupt ===


@patch("src.router.resolve_rich_content", return_value=None)
@patch("src.router.reply_message")
def test_interrupt_active_session(mock_reply, mock_rich):
    pool, dispatcher, defaults = _make_mocks()
    mock_client = AsyncMock()
    pool.get_client = MagicMock(return_value=mock_client)
    event = _make_event(content="/interrupt cms")
    run_async(route_message(pool, event, dispatcher, defaults))
    mock_client.interrupt.assert_called_once()
    assert "中断信号" in mock_reply.call_args[0][1]


@patch("src.router.resolve_rich_content", return_value=None)
@patch("src.router.reply_message")
def test_interrupt_nonexistent_session(mock_reply, mock_rich):
    pool, dispatcher, defaults = _make_mocks()
    pool.get_client = MagicMock(return_value=None)
    event = _make_event(content="/interrupt 不存在")
    run_async(route_message(pool, event, dispatcher, defaults))
    assert "不存在" in mock_reply.call_args[0][1]


@patch("src.router.resolve_rich_content", return_value=None)
@patch("src.router.reply_message")
def test_interrupt_default_session(mock_reply, mock_rich):
    pool, dispatcher, defaults = _make_mocks()
    mock_client = AsyncMock()
    pool.get_client = MagicMock(return_value=mock_client)
    event = _make_event(content="/interrupt")
    run_async(route_message(pool, event, dispatcher, defaults))
    # 无 suffix → 中断 base session (p2p_ou_123)
    pool.get_client.assert_called_once_with("p2p_ou_123")
    mock_client.interrupt.assert_called_once()
