"""lark 模块测试"""

import json
import logging
from unittest.mock import MagicMock, patch

from src.lark import add_reaction, remove_reaction, reply_message


class TestReplyMessage:
    @patch("src.lark.subprocess.run")
    def test_sends_correct_command(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        reply_message("om_123", "hello")
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "lark-cli" in args
        assert "om_123" in args[3]

    @patch("src.lark.subprocess.run")
    def test_truncates_long_text(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        reply_message("om_123", "x" * 5000)
        sent_data = json.loads(mock_run.call_args[0][0][5])
        content = json.loads(sent_data["content"])
        assert len(content["text"]) < 4100
        assert "截断" in content["text"]

    @patch("src.lark.subprocess.run")
    def test_logs_failure(self, mock_run, caplog):
        mock_run.return_value = MagicMock(returncode=1, stderr="API error")
        with caplog.at_level(logging.ERROR, logger="avatar"):
            reply_message("om_123", "hello")
        assert "回复消息失败" in caplog.text


class TestAddReaction:
    @patch("src.lark.subprocess.run")
    def test_returns_reaction_id(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"data": {"reaction_id": "r_abc"}})
        )
        assert add_reaction("om_123") == "r_abc"

    @patch("src.lark.subprocess.run")
    def test_returns_none_on_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        assert add_reaction("om_123") is None


class TestRemoveReaction:
    @patch("src.lark.subprocess.run")
    def test_logs_failure(self, mock_run, caplog):
        mock_run.return_value = MagicMock(returncode=1, stderr="not found")
        with caplog.at_level(logging.ERROR, logger="avatar"):
            remove_reaction("om_123", "r_abc")
        assert "移除表情失败" in caplog.text
