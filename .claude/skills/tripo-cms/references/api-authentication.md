# CMS API 认证与登录（CMS 特有）

> 通用认证元数据（URL、API Key 变量名、共享账户、Playwright 凭证变量）→ `tripo-repos` 的 tripo-cms "认证与凭证"段
> 禁止动作（不写 users.hash/salt/apiKey 等）→ `developer` / `tester` / `diagnose` agent "我不越的线"
> 本文只记录 Payload CMS 特有、别处无法复用的内容

## Payload 登录失败常见原因（诊断时参考）

1. `.env` 里的明文密码与 DB 里 `hash` 对应的明文不一致（被人改过但 `.env` 没同步）
2. `loginAttempts` 爆表，`lockUntil` 锁着账户（登录返回消息含 "locked"）
3. Payload 版本升级后 hash 算法变更（罕见但可能）
4. `apiKey / apiKeyIndex / enableAPIKey` 脏数据阻塞登录流程

## 密码对不上时的合法恢复路径

1. 停下 AskUserQuestion：要换已知密码还是需要先还原某个原值
2. 用户授权后走 Payload 官方流程（任选其一）：
   - Payload admin UI 的 "Forgot Password"
   - `POST /api/users/forgot-password` + `POST /api/users/reset-password`（走 auth 钩子、不绕过任何业务逻辑）
3. **不**走 `db.users.updateOne({$set: {hash, salt}})`——无论"改回原值"还是"设新值"

## Payload auth 字段速查（只读诊断用）

| 字段 | 作用 | 诊断价值 |
|------|------|---------|
| `loginAttempts` | 失败登录计数 | 高值说明曾被持续尝试 |
| `lockUntil` | 锁定到期时间 | 非空说明账户当前锁定 |
| `hash` / `salt` | pbkdf2-sha256 / 25000 轮 / 512B | 长度异常可能说明格式损坏 |
| `apiKey` / `apiKeyIndex` / `enableAPIKey` | API Key 流程字段（HMAC + encrypt 钩子） | 不应被手工写入 |
