# How to 编写和运行测试

Avatar 项目的测试策略指南。框架为 pytest，所有测试为纯单元测试，外部 I/O 全部 mock。

## 1. 目录结构

测试文件与源码同级放置在 `src/__tests__/` 下，文件名直接对应被测模块（无 `test_` 前缀）：

```
src/
├── __tests__/
│   ├── __init__.py
│   ├── handler.py              ← 测试 src/handler.py
│   ├── lark.py                 ← 测试 src/lark.py
│   ├── permissions.py          ← 测试 src/permissions.py
│   ├── pool.py                 ← 测试 src/pool.py
│   └── test_conversation.py    ← 测试 src/server.py (_parse_session_log + conversation API)
├── handler.py
├── lark.py
├── permissions.py
├── pool.py
├── config.py
└── main.py
```

## 2. pytest 配置

`pyproject.toml:10-15` 中定义：

- `testpaths = ["src/__tests__"]` — 测试发现路径
- `python_files = "*.py"` — 匹配所有 .py（因为文件无 `test_` 前缀）
- `python_classes = "Test*"` — 类名以 Test 开头
- `python_functions = "test_*"` — 方法名以 test_ 开头
- `pythonpath = ["."]` — 项目根目录加入 Python 路径，支持 `from src.xxx import` 写法

## 3. 运行方式

```bash
python3 -m pytest -v
```

## 4. Mock 策略

四种模式，按被测模块选用：

1. **subprocess mock**（用于 `lark.py`）：`@patch("src.lark.subprocess.run")` 拦截子进程调用，通过 `MagicMock(returncode=..., stdout=..., stderr=...)` 控制返回值。参考 `src/__tests__/lark.py:11-18`。

2. **pool mock + AsyncMock + async generator**（用于 `handler.py`）：通过 `_make_mock_pool(messages)` 工厂函数构造 mock pool（`src/__tests__/handler.py:61-74`）——`pool.get = AsyncMock(return_value=client)`，`client.query = AsyncMock()`，`client.receive_response` 赋值为返回 async generator 的真实 `async def` 函数（不能用 `AsyncMock`，因为 `async for` 需要真实的 async iterable）。lark 函数通过 `@patch("src.handler.*")` 拦截。

3. **全局变量直写**（用于 `permissions.py`）：直接操作 `permissions._current_sender_id` 模拟不同发送者身份。`ctx` 通过 `pytest.fixture(autouse=True)` 注入为 `MagicMock()`，仅满足函数签名。

4. **ClaudeSDKClient mock**（用于 `pool.py`）：`@patch("src.pool.ClaudeSDKClient")` 拦截 client 构造，`mock_instance.connect = AsyncMock()` 控制连接行为。参考 `src/__tests__/pool.py:21-34`。

**日志断言迁移：** `lark.py` 和 `session.py` 已从 `print(stderr)` 迁移到 `logging.getLogger("avatar")`，测试中使用 `caplog.at_level(logging.ERROR, logger="avatar")` 断言日志内容（替代 `capsys.readouterr().err`）。参考 `src/__tests__/lark.py:30-34`。

## 5. async 测试辅助

项目未使用 `pytest-asyncio`。所有 async 测试通过同步 wrapper 调用：

```python
def run_async(coro):
    return asyncio.run(coro)
```

`handler.py`、`permissions.py` 和 `pool.py` 的测试文件中各自定义了相同的 `run_async`。

## 6. 命名规范

- 测试类：`Test` + 被测函数名（PascalCase），如 `TestReplyMessage`、`TestPermissionGate`
- 测试方法：`test_<行为>_<场景>`（snake_case），描述预期行为而非实现细节，如 `test_truncates_long_text`、`test_non_owner_blocked_on_deploy`
- 辅助方法：`_` 前缀表示私有，如 `_event(...)`

## 7. 当前覆盖范围与空白点

| 模块 | 用例数 | 覆盖情况 |
|------|--------|----------|
| `lark.py` | 41 | `_convert_md_tables`(5: 基本表格/保留周围文本/无表格不变/多表格/中文对齐) `reply_message`(4: markdown格式/截断/降级fallback/失败日志) `_extract_post_text`(5: 基本/代码块/图片媒体/空/多语言) `_extract_message_text`(7: text/image/file/audio/interactive/未知/空) `resolve_rich_content`(9: 纯文本/merge_forward/图片/音频/文件/兜底内联图片) `_resolve_inline_images`(4: 单图/多图/失败/无图) `download_message_image`(3: 成功/失败/缓存) `add_reaction`(2) `remove_reaction`(1) |
| `handler.py` | 33 | `should_respond`(7) `compute_session_id`(5) `_build_prompt`(4: 所有者+私聊+名字/同事+群聊+群名+ID/无store降级/群聊无群名) `send_message`(11: query+入队/路由session/恢复session_id/slash透传/普通前缀/清@mention/空跳过/clear/interrupt/interrupt无client/群聊路由) `session_reader`(6: 完整流程+reaction/错误回复/保存session_id/1:1出队/metrics/无client退出) |
| `permissions.py` | 5+4 parametrize | `permission_gate` 全部 4 个逻辑分支 |
| `pool.py` | 5 | `get` 创建+连接(1) 复用(1) 不同 session 独立(1) `shutdown`(1) 并发去重(1) |
| `server.py` (test_conversation.py) | 14 | `_parse_session_log`(10: 空文件/不存在/用户消息/assistant+tool_use/model字段/model缺失/tool_result字符串/列表/截断/未知类型/畸形JSON/纯thinking跳过) `_get_claude_log_dir`(1) conversation API(3: 无session/有日志/日志不存在) |

已知空白点：

- **`config.py`** — 无测试（模块导入时立即执行，`config.json` 缺失直接 `sys.exit(1)`）
- **`main.py`** — 无测试（入口脚本、事件循环、子进程生命周期管理）
- **`lark.py`** — `resolve_user_name`/`resolve_chat_name` 未覆盖
- **`pool.py`** — `connect()` 失败后的 `disconnect()` + re-raise 路径未覆盖；`--resume` 路径未覆盖
- **`handler.py`** — `_ensure_display_names` 未覆盖；分段发送（多个 AssistantMessage → 逐条回复）逻辑未覆盖
