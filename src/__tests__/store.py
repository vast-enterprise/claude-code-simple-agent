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
