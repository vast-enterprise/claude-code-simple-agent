from src.metrics import MetricsCollector


def test_record_message():
    m = MetricsCollector()
    m.record_message("s1", "你好", True, "你好！")
    assert m.total_messages == 1
    assert m.total_errors == 0
    assert len(m.message_log) == 1
    assert m.message_log[0]["session_id"] == "s1"
    assert m.message_log[0]["success"] is True


def test_record_error():
    m = MetricsCollector()
    m.record_message("s1", "测试", False, "")
    assert m.total_errors == 1
    assert m.total_messages == 1


def test_ring_buffer_limit():
    m = MetricsCollector(max_log=5)
    for i in range(10):
        m.record_message("s1", f"msg{i}", True, "ok")
    assert len(m.message_log) == 5
    assert m.total_messages == 10


def test_status():
    m = MetricsCollector()
    m.record_message("s1", "hi", True, "hey")
    s = m.status()
    assert "uptime" in s
    assert s["total_messages"] == 1
    assert s["total_errors"] == 0
    assert s["error_rate"] == "0.0%"


def test_content_preview_truncation():
    m = MetricsCollector()
    long_content = "a" * 100
    m.record_message("s1", long_content, True, "ok")
    assert len(m.message_log[0]["content_preview"]) == 50
