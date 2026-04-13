import json
import tempfile
from pathlib import Path
from src.store import SessionStore


def test_save_and_load():
    with tempfile.TemporaryDirectory() as d:
        store = SessionStore(Path(d) / "sessions.json")
        store.save("s1", {"message_count": 0})
        loaded = store.load_all()
        assert "s1" in loaded
        assert loaded["s1"]["message_count"] == 0
        assert "created_at" in loaded["s1"]


def test_remove():
    with tempfile.TemporaryDirectory() as d:
        store = SessionStore(Path(d) / "sessions.json")
        store.save("s1", {})
        assert store.remove("s1") is True
        assert "s1" not in store.load_all()


def test_remove_nonexistent():
    with tempfile.TemporaryDirectory() as d:
        store = SessionStore(Path(d) / "sessions.json")
        assert store.remove("s1") is False


def test_update_active():
    with tempfile.TemporaryDirectory() as d:
        store = SessionStore(Path(d) / "sessions.json")
        store.save("s1", {"message_count": 0})
        store.update_active("s1")
        data = store.load_all()
        assert data["s1"]["message_count"] == 1


def test_load_nonexistent():
    with tempfile.TemporaryDirectory() as d:
        store = SessionStore(Path(d) / "sessions.json")
        assert store.load_all() == {}


def test_persistence_across_instances():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "sessions.json"
        store1 = SessionStore(path)
        store1.save("s1", {"message_count": 5})
        store2 = SessionStore(path)
        assert store2.load_all()["s1"]["message_count"] == 5


def test_corrupted_file():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "sessions.json"
        path.write_text("not json")
        store = SessionStore(path)
        assert store.load_all() == {}


# ── 归档相关测试 ──


def test_archive_creates_history():
    with tempfile.TemporaryDirectory() as d:
        store = SessionStore(Path(d) / "sessions.json")
        store.save("s1", {"claude_session_id": "abc123", "sender_name": "Alice"})
        assert store.archive("s1") is True

        history = store.load_history()
        assert len(history) == 1
        assert history[0]["session_id"] == "s1"
        assert history[0]["claude_session_id"] == "abc123"
        assert history[0]["sender_name"] == "Alice"
        assert "archived_at" in history[0]


def test_archive_nonexistent_returns_false():
    with tempfile.TemporaryDirectory() as d:
        store = SessionStore(Path(d) / "sessions.json")
        assert store.archive("nonexistent") is False


def test_archive_does_not_remove_from_active():
    """archive 只复制到历史，不从活跃列表删除"""
    with tempfile.TemporaryDirectory() as d:
        store = SessionStore(Path(d) / "sessions.json")
        store.save("s1", {})
        store.archive("s1")
        assert "s1" in store.load_all()


def test_archive_multiple_same_session():
    """同一 session_id 可多次归档"""
    with tempfile.TemporaryDirectory() as d:
        store = SessionStore(Path(d) / "sessions.json")
        store.save("s1", {"message_count": 5})
        store.archive("s1")

        # 模拟删除再创建新 session
        store.remove("s1")
        store.save("s1", {"message_count": 10})
        store.archive("s1")

        history = store.load_history()
        assert len(history) == 2
        assert history[0]["message_count"] == 5
        assert history[1]["message_count"] == 10


def test_load_history_empty():
    with tempfile.TemporaryDirectory() as d:
        store = SessionStore(Path(d) / "sessions.json")
        assert store.load_history() == []


def test_load_history_corrupted():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "sessions.json"
        store = SessionStore(path)
        # 写入损坏的历史文件
        (Path(d) / "sessions_history.json").write_text("not json")
        assert store.load_history() == []


def test_load_history_not_a_list():
    """历史文件内容不是列表时返回空"""
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "sessions.json"
        store = SessionStore(path)
        (Path(d) / "sessions_history.json").write_text('{"key": "value"}')
        assert store.load_history() == []


def test_archive_then_remove_full_flow():
    """完整流程：save → archive → remove → 验证 active 空、history 有"""
    with tempfile.TemporaryDirectory() as d:
        store = SessionStore(Path(d) / "sessions.json")
        store.save("s1", {"claude_session_id": "cid-1"})
        store.archive("s1")
        store.remove("s1")

        assert store.load_all() == {}
        history = store.load_history()
        assert len(history) == 1
        assert history[0]["claude_session_id"] == "cid-1"
