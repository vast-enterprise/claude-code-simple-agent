# 编码规范

本文档从项目源码中提炼编码规范，作为开发时的快速查阅参考。

## 1. 核心摘要

项目为 Python >= 3.12 异步服务，运行时依赖 `claude-agent-sdk` 和 `aiohttp`，使用 `pyproject.toml` 管理依赖，pytest 运行测试。代码组织遵循扁平模块结构，测试与源码同级 colocated，所有飞书交互通过 `lark-cli` subprocess 完成且强制 `--as bot`。

## 2. 模块组织

- 源码位于 `src/`，每个模块一个文件，职责单一（config / lark / permissions / handler / pool / session / main / notify / store / metrics / server）+ 两个前端页面（dashboard.html / session.html）
- 测试位于 `src/__tests__/`，与 `src/` 同级 colocated，文件名与被测模块一致
- `src/__init__.py` 和 `src/__tests__/__init__.py` 均为空包标记文件
- 配置：`pyproject.toml` (`[tool.pytest.ini_options]`) — `testpaths = ["src/__tests__"]`, `pythonpath = ["."]`

## 3. 命名规范

| 类别 | 规则 | 示例 |
|------|------|------|
| 模块文件 | snake_case，单词简短 | `handler.py`, `permissions.py` |
| 公开函数 | snake_case，动词开头 | `should_respond`, `handle_message`, `add_reaction` |
| 私有变量 | `_` 前缀 | `_current_sender_id`, `_config_path` |
| 常量 | UPPER_SNAKE_CASE | `OWNER_ID`, `SENSITIVE`, `ROOT`, `CONFIG` |
| 测试类 | `Test` + 被测函数名 PascalCase | `TestReplyMessage`, `TestPermissionGate` |
| 测试方法 | `test_` + 行为描述 snake_case | `test_truncates_long_text`, `test_non_owner_blocked_on_deploy` |
| 测试辅助 | `_` 前缀表示私有 | `_event(...)`, `_ctx` |

## 4. 异步处理模式

- 业务异步函数使用 `async def` + `await`，入口通过 `asyncio.run(main())` 驱动
- SDK 流式响应使用 `async for msg in client.receive_response()` 消费
- 测试中不使用 `pytest-asyncio`，统一通过同步辅助函数包装：`run_async(coro) = asyncio.run(coro)`
- Mock async 方法：`client.query = AsyncMock()`；mock async generator：定义真实 `async def` 函数并赋值给 `client.receive_response`

## 5. 错误处理与日志模式

- 项目使用 `logging.getLogger("avatar")` 统一日志系统，通过 `log_debug()`、`log_info()`、`log_error()` 函数输出（`src/config.py:20-29`）
- `AVATAR_DEBUG=1` 环境变量开启 DEBUG 级别，默认 INFO
- subprocess 调用失败：检查 `returncode != 0`，通过 `log_error()` 记录 stderr 前 200 字符，不抛异常
- 返回值降级：失败时返回 `None`（如 `add_reaction`）或静默跳过（如 `remove_reaction`）
- 配置缺失：`config.json` 不存在时 `sys.exit(1)`，硬退出
- 消息处理异常：session worker 中 `try/except Exception` 捕获并 `log_error()`，不中断事件循环

## 6. 导入规范

- 标准库在前，第三方库居中，项目内模块在后，各组之间空行分隔
- 项目内导入使用绝对路径：`from src.config import OWNER_ID`，`import src.permissions as permissions`
- 测试中 patch 路径指向被测模块命名空间：`@patch("src.handler.reply_message")`（非 `src.lark.reply_message`）

## 7. lark-cli 调用铁律

- 所有 `lark-cli` 命令必须携带 `--as bot`，无例外
- 使用 `subprocess.run` 同步调用，设置 `capture_output=True, text=True, timeout=N`
- 参数通过 `json.dumps()` 序列化后传入 `--params` / `--data`
- 回复消息超 4000 字符时截断至 3950 并追加截断提示

## 8. 源码真相

- **模块结构**: `pyproject.toml:10-15` — pytest 配置与路径定义
- **lark-cli 调用**: `src/lark.py` (`add_reaction`, `remove_reaction`, `reply_message`) — 全部 subprocess + `--as bot`
- **日志系统**: `src/config.py:9-29` — `logging.getLogger("avatar")` + `log_debug/log_info/log_error`
- **错误处理**: `src/lark.py:40`, `src/lark.py:58` — `log_error()` 日志模式
- **原子写入**: `src/store.py:58-73` — `tmpfile → fsync → os.replace` 模式
- **异步入口**: `src/main.py:158-159` — `asyncio.run(main())`
- **测试 async 包装**: `src/__tests__/handler.py:15-16`, `src/__tests__/pool.py:11-12` — `run_async` 辅助函数
- **导入风格**: `src/handler.py:1-8` — 三段式导入示例
