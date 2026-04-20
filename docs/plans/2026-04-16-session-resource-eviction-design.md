# Session 资源回收设计

## 问题定义

当前架构中，每个 session 持有独立的 Claude 子进程（~525MB 内存，含 MCP 子进程），只增不减。随着用户数增长，资源占用线性增加：

- 11 个 session 全部在线 = ~5.7GB 内存 + 55 个进程
- 大部分 session 长期空闲（数据显示 6/11 空闲超过 24 小时）
- 空闲 session 的进程持续占用资源但无产出

## 设计目标

1. **降低资源占用**：回收空闲 session 的进程资源
2. **保持响应速度**：高频用户无感知
3. **保留上下文**：回收后仍可通过 `--resume` 恢复对话历史

## 方案选择

**采用 LRU 按需回收策略**：

- 新 session 创建时检查总数，超过阈值则回收最久未活跃的
- 回收动作：断开进程 + 取消 reader task + 清空 FIFO，保留元数据
- 下次消息到达时自动 `--resume` 恢复上下文

**拒绝的方案**：
- 定时扫描回收：增加后台任务复杂度，可能回收即将活跃的 session
- 基于内存压力动态回收：实现复杂，收益不明显

## 详细设计

### 1. 回收触发

**时机**：`ClientPool.get()` 创建新 client 前

**条件**：`len(self._clients) >= max_active_clients`

**动作**：调用 `_evict_lru()` 回收最久未活跃的 session

### 2. LRU 选择算法

```python
def _select_lru_session(self) -> str | None:
    """选择最久未活跃的 session（基于 store 中的 last_active）"""
    if not self._store:
        return None
    
    sessions = self._store.load_all()
    if not sessions:
        return None
    
    # 按 last_active 升序排序，取第一个
    sorted_sessions = sorted(
        sessions.items(),
        key=lambda x: x[1].get("last_active", ""),
    )
    return sorted_sessions[0][0]
```

### 3. 回收动作

```python
async def _evict_lru(self) -> bool:
    """回收最久未活跃的 session"""
    session_id = self._select_lru_session()
    if not session_id:
        return False
    
    # 1. 断开 client（杀掉 Claude 子进程）
    client = self._clients.pop(session_id, None)
    if client:
        await client.disconnect()
    
    # 2. 取消 reader task
    if self._dispatcher:
        self._dispatcher.cancel_reader(session_id)
    
    # 3. 清空 FIFO 队列
    pending = self._pending.pop(session_id, None)
    if pending and len(pending) > 0:
        log_debug(f"[Eviction] 丢弃 {len(pending)} 条待处理消息")
    
    # 4. 保留 store 元数据（不调用 store.remove()）
    
    log_debug(f"[Eviction] session={session_id} evicted")
    return True
```

### 4. 恢复机制

当前 `pool.get()` 已支持 `--resume`，无需修改：

```python
async def get(self, session_id: str) -> ClaudeSDKClient:
    # ...
    if session_id not in self._clients:
        # 检查是否需要回收
        if len(self._clients) >= self._max_active_clients:
            await self._evict_lru()
        
        # 如果 store 中有 claude_session_id，用 --resume 恢复
        stored_sid = self.get_claude_session_id(session_id)
        if stored_sid:
            opts = dataclasses.replace(self._options, resume=stored_sid)
        # ...
```

### 5. 配置

`config.json` 增加配置项：

```json
{
  "max_active_clients": 5
}
```

`src/config.py` 读取：

```python
MAX_ACTIVE_CLIENTS = CONFIG.get("max_active_clients", 5)
```

### 6. 可观测性

**日志**：
- 回收时：`[Eviction] session=<id> evicted (idle=<seconds>s)`
- FIFO 非空时：`[Eviction] 丢弃 N 条待处理消息`

**API**：`/api/status` 增加字段：

```json
{
  "active_clients": 3,
  "max_active_clients": 5,
  "total_sessions": 11
}
```

**Dashboard**：状态卡片增加「活跃进程」显示：

```
┌─────────────────┐
│ 活跃进程        │
│ 3 / 5           │
└─────────────────┘
```

## 实现清单

1. `src/pool.py`
   - 增加 `_max_active_clients` 属性
   - 增加 `_dispatcher` 引用（用于取消 reader）
   - 实现 `_select_lru_session()`
   - 实现 `_evict_lru()`
   - 修改 `get()` 在创建前检查阈值

2. `src/config.py`
   - 增加 `MAX_ACTIVE_CLIENTS` 配置读取

3. `src/main.py`
   - 传递 `dispatcher` 引用给 `ClientPool`

4. `src/server.py`
   - `/api/status` 增加 `active_clients` 字段

5. `src/dashboard.html`
   - 状态卡片增加活跃进程显示

6. `src/__tests__/pool.py`
   - 测试 LRU 回收逻辑
   - 测试元数据保留
   - 测试 resume 恢复

7. `config.example.json`
   - 增加 `max_active_clients` 示例

## 测试策略

### 单元测试

- `test_evicts_lru_when_exceeds_limit`：超过阈值时回收最久未活跃的
- `test_preserves_metadata_after_eviction`：回收后元数据仍在 store
- `test_resume_after_eviction`：回收后下次消息能 resume
- `test_no_eviction_below_limit`：未超阈值时不回收
- `test_eviction_with_pending_messages`：FIFO 非空时的回收行为

### 集成测试

- 高频用户无感知：3 个活跃用户持续对话，无延迟
- 低频用户 resume：回收后再发消息，上下文保留
- Dashboard 可观测：活跃进程数实时更新

### 性能测试

- 回收耗时 < 100ms
- Resume 延迟 < 2 秒

## 预期效果

| 场景 | 优化前 | 优化后 |
|------|--------|--------|
| 20 个用户，5 个高频 | 20 进程，~10GB | 5 进程，~2.6GB |
| 100 个用户，10 个高频 | 100 进程，~50GB | 10 进程，~5.2GB |
| 高频用户体验 | 无感知 | 无感知 |
| 低频用户体验 | 无感知 | 首次回复延迟 1-2 秒 |

## 风险与缓解

| 风险 | 缓解措施 |
|------|----------|
| 回收时 FIFO 非空（用户正在等待回复） | 记录 warning，下次消息重新处理 |
| Resume 失败导致上下文丢失 | Resume 失败时降级为新 session，记录 error |
| 并发回收与新消息冲突 | 使用 per-session lock 保护回收操作 |
| 阈值设置不当 | 可配置，默认 5 个（覆盖大多数场景） |

## 后续优化方向

1. **智能预测**：根据用户历史活跃模式动态调整阈值
2. **分级存储**：高频用户常驻内存，低频用户 Redis 缓存
3. **进程池复用**：多个 session 共享 Claude 进程（需 SDK 支持）
4. **冷启动优化**：预热常用 session，减少 resume 延迟
