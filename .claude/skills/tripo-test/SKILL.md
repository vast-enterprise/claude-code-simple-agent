---
name: tripo-test
description: |
  集成测试方法论：指导 agent 完成各类测试工作。
  定义测试分类体系、每类测试的执行方法、以及什么是好的测试。
  从 tripo-requirement step 8 中独立出来，可在任何测试场景中使用。

  触发条件（任一命中即触发）：
  - tripo-requirement 步骤 8.3 显式调用
  - 用户说"跑测试"、"集成测试"、"UI 测试"、"验证功能"
  - bugfix 验证、regression 测试、PR 验证
  - 任何需要启动服务并验证功能的场景
---

# 集成测试方法论

## 零、开始测试前

> 🔴 **先对齐，再动手**

```
收到测试指令
│
├── 1. 是否有测试计划文档？
│   ├── 有 → 读取计划，确认本轮场景已在计划中
│   │        ├── 有新场景未覆盖 → 先更新计划文档 → 再执行
│   │        └── 计划已覆盖 → 进入下方决策树
│   └── 无 → 先输出测试计划（列出要测什么、用什么工具、预期结果），确认后再执行
│
├── 2. 验证指标对齐：
│   - 用户期望验证什么？（预期结果）
│   - 我实际要测什么？（测试操作）
│   - 两者一致才开始
│
└── 3. 进入测试分类决策树 ↓
```

## 一、测试分类

### 怎么选：判定决策树

```
要验证什么？
│
├── HTTP 接口能否正确返回数据？
│   └── → API 测试
│
├── 页面上能否看到某个元素/样式？
│   └── → UI 渲染测试
│
├── 用户点击/输入后页面状态是否正确变化？
│   └── → UI 交互测试
│
├── <meta>、OG 标签、SEO 数据是否正确？
│   └── → SEO 测试（浏览器必须，curl 不行）
│
└── CMS 数据 → 前端页面的完整链路？
    └── → 跨仓库联调测试（组合以上类型）
```

### 五类测试速查

| # | 类型 | 验证对象 | 工具 | 证据形式 |
|---|------|---------|------|---------|
| 1 | API 测试 | HTTP 请求+响应 | curl / httpie | 请求命令 + 响应 body |
| 2 | UI 渲染测试 | DOM 元素存在性、样式 | playwright snapshot / screenshot | snapshot 输出 + 截图 |
| 3 | UI 交互测试 | 操作后 UI 状态变化 | playwright click/fill + screenshot | 操作前后截图对比 |
| 4 | SEO 测试 | meta/OG/结构化数据 | playwright eval / snapshot | eval 返回值 + snapshot |
| 5 | 跨仓库联调 | 端到端数据流 | 组合以上工具 | 每层一份证据 |

---

## 二、每类测试怎么做

### 1. API 测试

**准备**：
- 确认服务已启动（`curl http://localhost:<port>/health` 或类似 endpoint）
- 准备测试数据（按 API 文档准备完整参数，不是只填一个字段）

**执行**：
```bash
# 标准格式：完整请求 + 响应
curl -X POST http://localhost:3000/api/xxx \
  -H "Content-Type: application/json" \
  -d '{"field1": "value1", "field2": "value2"}' \
  -w "\n%{http_code}"
```

**判定**：
- HTTP 状态码符合预期
- 响应 body 包含预期字段和值
- 错误场景也要测（缺字段、无权限、不存在的 ID）

---

### 2. UI 渲染测试

**准备**：
- 服务已启动且可访问
- 确认访问地址（本地 HTTP，非 HTTPS）

**执行**：
```
1. playwright open http://localhost:<port>/target-page
2. playwright snapshot                    → 确认 DOM 中有目标元素
3. playwright screenshot                  → 视觉截图留证
```

**判定**：
- snapshot 中包含目标元素（按钮/文本/图片）
- 截图中元素在预期位置、样式正确
- 如有响应式需求，需在不同视口宽度下各截一次

---

### 3. UI 交互测试

**准备**：
- 同 UI 渲染测试
- 明确操作序列：点什么 → 填什么 → 期望看到什么

**执行**：
```
1. playwright screenshot                  → 操作前截图（基线）
2. playwright click <uid>                 → 执行交互
3. playwright wait-for "预期文本"         → 等待 UI 响应
4. playwright screenshot                  → 操作后截图（结果）
```

**判定**：
- 操作前后截图有明确可见的差异
- UI 状态变化符合预期（弹窗出现/消失、数据更新、按钮状态切换）
- 无 console error

---

### 4. SEO 测试

**为什么 curl 不行**：
- `useSeoMeta` / `useHead` 等框架 API 可能在客户端执行
- curl 只拿到 SSR HTML，不包含 JS 执行后注入的 `<meta>` 标签
- 必须用浏览器让 JS 执行完毕后再检查

**执行**：
```
1. playwright open http://localhost:<port>/target-page
2. playwright eval "document.querySelector('meta[name=description]')?.content"
3. playwright eval "document.querySelector('meta[property=\"og:image\"]')?.content"
4. playwright snapshot   → 检查 <head> 区域完整性
```

**判定**：
- 每个 meta 标签返回非空值
- OG image URL 可访问
- title 和 description 内容与数据源一致

---

### 5. 跨仓库联调测试

**准备**：
- → 查 `tripo-repos` skill 各仓库的 **Dev 启动注意事项**（含分支检查、依赖、环境变量、启动参数）
- 所有涉及仓库的服务按顺序启动（通常 CMS 先启动，前端后启动）

**执行**：分层验证，每层独立出证据
```
层 1: CMS API → curl 验证数据正确返回
层 2: 前端 SSR → playwright snapshot 验证页面结构
层 3: 前端交互 → playwright click/screenshot 验证动态功能
层 4: SEO → playwright eval 验证 meta 标签
```

**判定**：
- 每层独立通过
- 数据从 CMS → 前端 API → 页面渲染的链路完整
- 修改 CMS 数据后，前端能正确反映变化

---

## 三、什么是好的测试

### 3.1 好测试的三个特征

1. **可追溯**：看到测试报告的人能复现每一步
   - 贴了什么命令、得到什么输出、基于什么判断 PASS/FAIL
   
2. **有对比**：不是单点验证，而是有基线对照
   - 操作前 vs 操作后
   - 预期值 vs 实际值
   - 正常 case vs 错误 case

3. **覆盖完整**：不只测 happy path
   - 正常输入 + 异常输入 + 边界值
   - 必填字段全填 + 可选字段至少一个非默认值

### 3.2 证据标准

**铁律：证据先贴，结论后出**

```
✅ 正确：
[截图/输出] → "截图显示按钮已渲染在右上角" → PASS

❌ 错误：
PASS → （没有证据）
```

| 有效证据 | 无效证据 |
|---------|---------|
| curl 请求+完整响应 | "我验证过了" |
| playwright screenshot 截图 | "页面加载正常" |
| playwright snapshot DOM 输出 | "功能工作" |
| console 日志截取 | "没有报错" |
| 测试命令 + 完整输出 | 对过程的文字描述 |

### 3.3 测试数据要求

- 按组件 props / API 参数的**完整要求**准备，不是随便填
- 必填字段全部赋值
- 至少一个可选字段用非默认值（验证非默认路径）
- 至少一个边界值（空字符串、超长文本、特殊字符）

### 3.4 测试工具使用原则

1. **用户指定了工具 → 必须用该工具**，遇到障碍先排障，不私自替换
2. **遇到工具障碍 → 先向用户说明问题和排障结果**，获得许可后才能用替代方案
3. **替代方案必须标注**：在报告中写明 `⚠️ 工具替代: <原因>`

### 3.5 FAIL 分流规则

测试场景 FAIL 时：

```
失败原因明确吗？（如：返回值不对、缺字段、样式错位）
├── 是 → 留在 tripo-test，修复后重测
└── 否（不知道为什么失败）→ 切换 tripo-diagnose 做根因分析
```

### 3.6 降级条件

仅以下情况允许标记 `⚠️ DEFERRED`（附原因和补测计划）：
- 服务无法启动（贴启动日志）
- 依赖外部服务且不可 mock（说明具体依赖）
- 工具替代已获用户许可（标注替代原因）
