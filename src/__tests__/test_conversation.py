"""_parse_session_log + conversation API 端点测试"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

from src.server import _parse_session_log, _get_claude_log_dir, _create_app
from src.metrics import MetricsCollector


# ── 纯函数测试：_parse_session_log ──


class TestParseSessionLog:
    """测试 JSONL 日志解析"""

    def _write_jsonl(self, tmp: Path, entries: list[dict]) -> Path:
        log = tmp / "test.jsonl"
        with open(log, "w") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")
        return log

    def test_empty_file(self, tmp_path):
        log = tmp_path / "empty.jsonl"
        log.write_text("")
        assert _parse_session_log(log) == []

    def test_nonexistent_file(self, tmp_path):
        log = tmp_path / "nope.jsonl"
        assert _parse_session_log(log) == []

    def test_user_text_message(self, tmp_path):
        log = self._write_jsonl(tmp_path, [
            {"type": "user", "message": {"role": "user", "content": "hello"}, "timestamp": "T1"},
        ])
        msgs = _parse_session_log(log)
        assert len(msgs) == 1
        assert msgs[0] == {"role": "user", "content": "hello", "timestamp": "T1"}

    def test_assistant_text_and_tool_use(self, tmp_path):
        log = self._write_jsonl(tmp_path, [
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "model": "claude-sonnet-4-6-20250514",
                    "content": [
                        {"type": "thinking", "thinking": "hmm"},  # 应跳过
                        {"type": "text", "text": "reply"},
                        {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "ls"}},
                    ],
                },
                "timestamp": "T2",
            },
        ])
        msgs = _parse_session_log(log)
        assert len(msgs) == 1
        assert msgs[0]["role"] == "assistant"
        assert msgs[0]["model"] == "claude-sonnet-4-6-20250514"
        assert len(msgs[0]["blocks"]) == 2  # thinking 被跳过
        assert msgs[0]["blocks"][0] == {"type": "text", "text": "reply"}
        assert msgs[0]["blocks"][1] == {
            "type": "tool_use", "name": "Bash", "input": {"command": "ls"}, "id": "t1",
        }

    def test_assistant_model_empty_when_missing(self, tmp_path):
        """JSONL 中无 model 字段时，返回空字符串"""
        log = self._write_jsonl(tmp_path, [
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "no model"}],
                },
                "timestamp": "T7",
            },
        ])
        msgs = _parse_session_log(log)
        assert msgs[0]["model"] == ""

    def test_tool_result_string_content(self, tmp_path):
        log = self._write_jsonl(tmp_path, [
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [
                        {"type": "tool_result", "tool_use_id": "t1", "content": "file1.py"},
                    ],
                },
                "timestamp": "T3",
            },
        ])
        msgs = _parse_session_log(log)
        assert len(msgs) == 1
        assert msgs[0]["role"] == "tool_result"
        assert msgs[0]["tool_use_id"] == "t1"
        assert msgs[0]["content"] == "file1.py"

    def test_tool_result_list_content(self, tmp_path):
        log = self._write_jsonl(tmp_path, [
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "t2",
                            "content": [
                                {"type": "text", "text": "line1"},
                                {"type": "text", "text": "line2"},
                            ],
                        },
                    ],
                },
                "timestamp": "T4",
            },
        ])
        msgs = _parse_session_log(log)
        assert len(msgs) == 1
        assert msgs[0]["content"] == "line1\nline2"

    def test_tool_result_content_truncated(self, tmp_path):
        long_content = "x" * 6000
        log = self._write_jsonl(tmp_path, [
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [
                        {"type": "tool_result", "tool_use_id": "t3", "content": long_content},
                    ],
                },
                "timestamp": "T5",
            },
        ])
        msgs = _parse_session_log(log)
        assert len(msgs[0]["content"]) == 5000

    def test_skips_unknown_types(self, tmp_path):
        log = self._write_jsonl(tmp_path, [
            {"type": "queue-operation", "timestamp": "T0"},
            {"type": "attachment", "message": {}, "timestamp": "T0"},
        ])
        assert _parse_session_log(log) == []

    def test_skips_malformed_json(self, tmp_path):
        log = tmp_path / "bad.jsonl"
        log.write_text('{"type":"user","message":{"role":"user","content":"ok"},"timestamp":"T1"}\nnot json\n')
        msgs = _parse_session_log(log)
        assert len(msgs) == 1

    def test_assistant_only_thinking_blocks_skipped(self, tmp_path):
        """assistant 消息如果只有 thinking block，整条消息不应出现"""
        log = self._write_jsonl(tmp_path, [
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "thinking", "thinking": "just thinking..."},
                    ],
                },
                "timestamp": "T6",
            },
        ])
        msgs = _parse_session_log(log)
        assert len(msgs) == 0  # blocks 为空，整条消息不输出


# ── _get_claude_log_dir 测试 ──


class TestGetClaudeLogDir:
    def test_path_encoding(self):
        log_dir = _get_claude_log_dir()
        # 应以 ~/.claude/projects/ 开头
        assert str(log_dir).startswith(str(Path.home() / ".claude" / "projects"))
        # 路径中不应含 /Users/ 等斜杠（编码后是 -Users-）
        dir_name = log_dir.name
        assert dir_name.startswith("-")
        assert "/" not in dir_name


# ── API 端点测试 ──


class TestConversationAPI(AioHTTPTestCase):
    async def get_application(self):
        self.mock_pool = MagicMock()
        self.mock_pool.list_sessions.return_value = {
            "p2p_ou_test": {
                "message_count": 5,
                "last_active": "2026-04-13T10:00:00Z",
                "created_at": "2026-04-13T09:00:00Z",
            }
        }
        self.mock_pool.remove = MagicMock()
        self.mock_pool.get_claude_session_id = MagicMock(return_value=None)

        self.metrics = MetricsCollector()
        return _create_app(self.mock_pool, self.metrics)

    @unittest_run_loop
    async def test_conversation_no_claude_session(self):
        """没有 claude_session_id 时返回 error + 空 messages"""
        resp = await self.client.get("/api/sessions/p2p_ou_test/conversation")
        assert resp.status == 200
        data = await resp.json()
        assert data["session_id"] == "p2p_ou_test"
        assert "error" in data
        assert data["messages"] == []

    @unittest_run_loop
    async def test_conversation_with_log(self):
        """有 claude_session_id 且日志文件存在时，返回解析后的消息"""
        self.mock_pool.get_claude_session_id.return_value = "fake-claude-sid"

        # 创建临时日志文件
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            log_file = log_dir / "fake-claude-sid.jsonl"
            log_file.write_text(
                json.dumps({
                    "type": "user",
                    "message": {"role": "user", "content": "hi"},
                    "timestamp": "T1",
                }) + "\n"
            )

            with patch("src.server._get_claude_log_dir", return_value=log_dir):
                resp = await self.client.get("/api/sessions/p2p_ou_test/conversation")
                assert resp.status == 200
                data = await resp.json()
                assert data["session_id"] == "p2p_ou_test"
                assert data["claude_session_id"] == "fake-claude-sid"
                assert len(data["messages"]) == 1
                assert data["messages"][0]["content"] == "hi"

    @unittest_run_loop
    async def test_conversation_log_not_found(self):
        """有 claude_session_id 但日志文件不存在时，返回空 messages"""
        self.mock_pool.get_claude_session_id.return_value = "nonexistent-sid"

        with patch("src.server._get_claude_log_dir", return_value=Path("/tmp/nonexistent_dir_12345")):
            resp = await self.client.get("/api/sessions/p2p_ou_test/conversation")
            assert resp.status == 200
            data = await resp.json()
            assert data["messages"] == []
            assert "error" not in data  # 日志文件不存在不算 error，只是空消息


class TestSessionPage(AioHTTPTestCase):
    async def get_application(self):
        self.mock_pool = MagicMock()
        self.mock_pool.list_sessions.return_value = {}
        self.mock_pool.remove = MagicMock()
        self.metrics = MetricsCollector()
        return _create_app(self.mock_pool, self.metrics)

    @unittest_run_loop
    async def test_session_page_exists(self):
        """session.html 存在时返回 200"""
        with tempfile.NamedTemporaryFile(suffix=".html", mode="w", delete=False) as f:
            f.write("<html><body>Session</body></html>")
            tmp_path = Path(f.name)

        try:
            with patch("src.server._SESSION_PAGE_PATH", tmp_path):
                resp = await self.client.get("/session.html")
                assert resp.status == 200
        finally:
            tmp_path.unlink()

    @unittest_run_loop
    async def test_session_page_not_found(self):
        """session.html 不存在时返回 404"""
        with patch("src.server._SESSION_PAGE_PATH", Path("/tmp/nonexistent_session_page.html")):
            resp = await self.client.get("/session.html")
            assert resp.status == 404
