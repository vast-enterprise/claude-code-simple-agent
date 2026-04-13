import time
from unittest.mock import patch, MagicMock
from src.notify import notify_error, _throttle_cache


def test_notify_error_calls_lark_cli():
    _throttle_cache.clear()
    with patch("src.notify._notify_config", {"enabled": True, "receive_id": "ou_test", "receive_id_type": "open_id"}):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            notify_error("测试标题", "测试详情")
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert "lark-cli" in args


def test_notify_error_throttle():
    _throttle_cache.clear()
    with patch("src.notify._notify_config", {"enabled": True, "receive_id": "ou_test", "receive_id_type": "open_id"}):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            notify_error("同类错误", "详情1")
            notify_error("同类错误", "详情2")
            assert mock_run.call_count == 1


def test_notify_error_disabled():
    _throttle_cache.clear()
    with patch("src.notify._notify_config", {"enabled": False}):
        with patch("subprocess.run") as mock_run:
            notify_error("标题", "详情")
            mock_run.assert_not_called()


def test_notify_error_failure_does_not_throttle():
    """发送失败时不应写入节流缓存，允许重试"""
    _throttle_cache.clear()
    with patch("src.notify._notify_config", {"enabled": True, "receive_id": "ou_test", "receive_id_type": "open_id"}):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="error")
            notify_error("失败标题", "详情")
            assert "失败标题" not in _throttle_cache
            # 第二次调用不被节流，仍然尝试发送
            notify_error("失败标题", "详情2")
            assert mock_run.call_count == 2


def test_notify_error_success_writes_throttle():
    """发送成功后才写入节流缓存"""
    _throttle_cache.clear()
    with patch("src.notify._notify_config", {"enabled": True, "receive_id": "ou_test", "receive_id_type": "open_id"}):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            notify_error("成功标题", "详情")
            assert "成功标题" in _throttle_cache
