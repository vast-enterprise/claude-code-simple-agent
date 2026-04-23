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
