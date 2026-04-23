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
