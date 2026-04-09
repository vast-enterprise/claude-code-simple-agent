<!-- This entire block is your raw intelligence report for other agents. It is NOT a final document. -->

### Code Sections (The Evidence)

- `src/__tests__/lark.py` (`TestReplyMessage`): 3 个测试，覆盖 `reply_message` 的正常发送、长文本截断、失败日志输出。
- `src/__tests__/lark.py` (`TestAddReaction`): 2 个测试，覆盖 `add_reaction` 成功返回 reaction_id、失败返回 None。
- `src/__tests__/lark.py` (`TestRemoveReaction`): 1 个测试，覆盖 `remove_reaction` 失败时的 stderr 日志。
- `src/__tests__/handler.py` (`TestShouldRespond`): 7 个测试，覆盖 `should_respond` 的全部分支：p2p 用户消息、bot 消息过滤、群聊 @bot、群聊无 @、群聊 @all、空内容 p2p、缺字段。
- `src/__tests__/handler.py` (`TestHandleMessage`): 4 个测试，覆盖 `handle_message` 的完整流程（回复+清理表情）、空内容跳过、错误结果回复兜底、群聊 @ 提及清洗。
- `src/__tests__/permissions.py` (`TestPermissionGate`): 5 个测试，覆盖 `permission_gate` 的所有者允许敏感命令、非所有者阻断敏感命令、非所有者允许安全命令、非 Bash 工具始终允许，以及 4 条敏感命令的参数化测试。
- `src/lark.py` (`reply_message`): 截断阈值 4000 字符，截断后保留 3950 字符并追加 `...(回复过长，已截断)`。
- `src/lark.py` (`add_reaction`, `remove_reaction`): 通过 `subprocess.run` 调用 `lark-cli`，均使用 `--as bot`。
- `src/handler.py` (`handle_message`): async 函数，通过 `async for` 消费 `client.receive_response()` 生成器；在首条 `AssistantMessage` 到达时调用 `add_reaction`，`ResultMessage` 到达后 break，最后调用 `remove_reaction`。
- `src/handler.py` (`should_respond`): 纯同步函数，无外部依赖。
- `src/permissions.py` (`permission_gate`): async 函数，依赖全局变量 `_current_sender_id`；`SENSITIVE` 列表包含 `deploy`, `git push`, `git merge`, `git reset`, `rm -rf`, `drop `。
- `src/config.py` (`OWNER_ID`): 从 `config.json` 读取 `owner_open_id`，测试中直接 import 此常量作为所有者 ID。

---

### Report (The Answers)

#### result

**测试覆盖范围**

- `lark.py`：覆盖 `reply_message`（3）、`add_reaction`（2）、`remove_reaction`（1），共 6 个测试。未覆盖 `add_reaction` 的 JSON 解析异常路径（`JSONDecodeError`/`KeyError`）。
- `handler.py`：覆盖 `should_respond`（7）、`handle_message`（4），共 11 个测试。未覆盖 `handle_message` 中 `reaction_id` 为 None 时不调用 `remove_reaction` 的路径（源码有此逻辑，测试 `test_replies_error_on_failure` 间接触及但未显式断言）。
- `permissions.py`：覆盖 `permission_gate` 全部 4 个逻辑分支 + 4 条参数化敏感命令，共 5 个测试（含 `@pytest.mark.parametrize` 展开为 4 个子用例）。

**Mock 策略**

- 全部使用 `unittest.mock`，无第三方 mock 库。
- `lark.py` 测试：`@patch("src.lark.subprocess.run")` 拦截子进程调用，通过 `MagicMock(returncode=..., stdout=..., stderr=...)` 控制返回值。
- `handler.py` 测试：`client` 为 `MagicMock()`，`client.query` 替换为 `AsyncMock()`；`client.receive_response` 直接赋值为返回 async generator 的普通 async 函数（`fake_response`/`fake_error`），不使用 `AsyncMock`。`reply_message`、`add_reaction`、`remove_reaction` 均通过 `@patch("src.handler.*")` 拦截。
- `permissions.py` 测试：直接写入全局变量 `permissions._current_sender_id` 来模拟不同发送者身份；`ctx` 通过 `pytest.fixture(autouse=True)` 注入为 `MagicMock()`，但 `permission_gate` 实现中未使用 `context` 参数，fixture 仅为满足函数签名。

**Async 处理方式**

- 两个测试文件（`handler.py`、`permissions.py`）均定义了相同的辅助函数 `run_async(coro) = asyncio.run(coro)`，用于在同步测试方法中运行协程。
- 未使用 `pytest-asyncio`，所有 async 测试均通过 `run_async()` 包装后以同步方式调用。

**命名规范**

- 测试类命名：`Test` + 被测函数/类名（PascalCase），如 `TestReplyMessage`、`TestHandleMessage`、`TestPermissionGate`。
- 测试方法命名：`test_` + 行为描述（snake_case），描述预期行为而非实现细节，如 `test_truncates_long_text`、`test_non_owner_blocked_on_deploy`、`test_cleans_at_mention_from_prompt`。
- 辅助方法：`_event(...)` 以下划线前缀表示私有，用于构造测试事件字典。

#### conclusions

- 三个测试文件合计 22 个测试方法（`permissions.py` 的参数化展开后为 25 个用例）。
- 所有外部 I/O（subprocess、SDK client）均被 mock，测试为纯单元测试，无网络/进程依赖。
- async 代码统一用 `asyncio.run()` 包装，不依赖 pytest 插件。
- `permissions.py` 测试通过直接操作模块级全局变量 `_current_sender_id` 来设置测试状态，与源码注释中"仅适用于串行处理"的警告一致。
- `lark.py` 的截断逻辑测试断言截断后长度 `< 4100`，与源码截断点 3950 + 追加文本吻合。
- `handler.py` 测试中 `fake_response` 是普通 async def 返回 async generator，而非 `AsyncMock`，这是因为 `receive_response` 在源码中被 `async for` 消费，需要真实的 async iterable。

#### relations

- `src/__tests__/handler.py` import `src.handler.should_respond` 和 `src.handler.handle_message`，同时 import `src.config.OWNER_ID` 和 `src.permissions` 模块。
- `src/__tests__/permissions.py` import `src.permissions.permission_gate`、`PermissionResultAllow`、`PermissionResultDeny`，并直接操作 `src.permissions._current_sender_id`。
- `src/__tests__/lark.py` import `src.lark.add_reaction`、`remove_reaction`、`reply_message`，patch 路径为 `src.lark.subprocess.run`。
- `src/handler.py` 在运行时调用 `src/lark.py` 的三个函数，测试通过 `@patch("src.handler.*")` 拦截这些调用（patch 目标是 handler 模块的命名空间，而非 lark 模块本身）。
- `src/handler.py` 在运行时写入 `src/permissions._current_sender_id`，测试中 `TestHandleMessage` 未直接验证此行为，`TestPermissionGate` 则直接操作该变量。
