"""DefaultsStore 单元测试"""

import tempfile
from pathlib import Path

from src.defaults_store import DefaultsStore


def test_get_default_returns_none_when_empty():
    with tempfile.TemporaryDirectory() as d:
        store = DefaultsStore(Path(d) / "session_defaults.json")
        assert store.get_default("p2p_ou_123") is None


def test_get_default_returns_stored_suffix():
    with tempfile.TemporaryDirectory() as d:
        store = DefaultsStore(Path(d) / "session_defaults.json")
        store.set_default("p2p_ou_123", "cms翻译")
        assert store.get_default("p2p_ou_123") == "cms翻译"


def test_get_default_returns_none_for_original_session():
    with tempfile.TemporaryDirectory() as d:
        store = DefaultsStore(Path(d) / "session_defaults.json")
        store.set_default("p2p_ou_123", None)
        assert store.get_default("p2p_ou_123") is None


def test_set_default_overwrites_existing():
    with tempfile.TemporaryDirectory() as d:
        store = DefaultsStore(Path(d) / "session_defaults.json")
        store.set_default("p2p_ou_123", "old")
        store.set_default("p2p_ou_123", "new")
        assert store.get_default("p2p_ou_123") == "new"


def test_remove_user_deletes_entry():
    with tempfile.TemporaryDirectory() as d:
        store = DefaultsStore(Path(d) / "session_defaults.json")
        store.set_default("p2p_ou_123", "cms")
        store.remove_user("p2p_ou_123")
        assert store.get_default("p2p_ou_123") is None


def test_remove_user_nonexistent_is_noop():
    with tempfile.TemporaryDirectory() as d:
        store = DefaultsStore(Path(d) / "session_defaults.json")
        store.remove_user("nonexistent")  # 不报错


def test_persistence_across_instances():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "session_defaults.json"
        store1 = DefaultsStore(path)
        store1.set_default("p2p_ou_123", "cms")
        store2 = DefaultsStore(path)
        assert store2.get_default("p2p_ou_123") == "cms"


def test_corrupted_file_resets():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "session_defaults.json"
        path.write_text("not json")
        store = DefaultsStore(path)
        assert store.get_default("p2p_ou_123") is None
