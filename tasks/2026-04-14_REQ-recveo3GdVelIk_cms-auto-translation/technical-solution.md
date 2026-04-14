# 技术方案：CMS 接入自动翻译能力

## 需求概述

为 CMS 所有含 localized 字段的集合（Posts, GeoPosts, Pages 等）提供文档级、字段级、批量翻译能力，以及翻译状态追踪和 REST API。

## 技术调研结论（2026-04-14）

### @payload-enchants/translator@1.3.0（原设计方案依赖）

| 维度 | 结论 |
|------|------|
| 最新版本 | 1.3.0（2024-11-23 发布，**5 个月未更新**） |
| peerDeps | `payload: ^3.1.0`（语义上兼容 3.69，但未实测） |
| 已知 Bug | **Payload 3.58+ Lexical 空字段崩溃**：空 RichText 字段触发翻译时，`JSON.parse(undefined)` 报错 |
| REST API | **无**，仅 Admin UI + Local API（`translateOperation`） |
| Resolver | openAI / google / libre / copy + 自定义 |
| 维护状态 | 停滞，大量 open issues 无响应 |

**结论：不建议直接用作生产依赖。** Lexical 崩溃 bug 对我们直接相关（博客内容存在空 RichText 字段场景）。

### @jhb.software/payload-content-translator-plugin@0.1.2（替代方案）

| 维度 | 结论 |
|------|------|
| 最新版本 | 0.1.2（2026-02-27 发布，仍在维护） |
| peerDeps | `payload: ^3.76.1`, `next: 15.4.11` |
| 兼容性 | **不兼容我们的 Payload 3.69.0**，需要升级到 3.76.1+ |
| Resolver | 仅 OpenAI 内置，无 Google/Libre |
| 维护状态 | 活跃，payload-enchants 的改进分支 |

**结论：版本不兼容，需升级 Payload。** 引入 Payload 大版本升级不在本需求范围内，风险过高。

## 方案对比

### 方案 A：Fork payload-enchants + 修复 Bug（原设计调整版）

**思路**：安装 payload-enchants/translator 用于文档级翻译（Admin UI + resolver 架构），自建 tripoTranslationPlugin 补齐 REST API、批量翻译、字段级翻译、状态追踪。同时 patch 掉 Lexical 空字段 bug。

| 优点 | 缺点 |
|------|------|
| Lexical 递归翻译已实现 | 需维护 patch，上游不再更新 |
| Resolver 架构成熟 | 引入不活跃依赖有长期风险 |
| 实现速度快 | 需要 fork 或 patch-package |

**工作量**：3-4 天

### 方案 B：完全自建翻译 Plugin

**思路**：不依赖任何第三方翻译插件，参考 payload-enchants 的 resolver 架构和 Lexical traversal 逻辑，完全自建 `src/plugins/translation/`。

| 优点 | 缺点 |
|------|------|
| 完全控制，无外部依赖风险 | 需自实现 Lexical 递归翻译 |
| 可精确适配 Payload 3.69 | 工作量较大 |
| 长期维护成本低 | 初期投入多 |

**工作量**：5-7 天

### 方案 C：升级 Payload + 使用 jhb.software 插件

**思路**：先升级 Payload 到 3.76.1+，再使用 jhb.software 插件，补齐缺失功能。

| 优点 | 缺点 |
|------|------|
| 使用最新维护的插件 | **需 Payload 大版本升级（3.69→3.76+）** |
| 版本对齐准确 | 升级可能引入 breaking changes |
| 维护活跃 | Resolver 生态不如 enchants |

**工作量**：Payload 升级 2-3 天 + 翻译开发 3-4 天 = 5-7 天，但升级风险不可控

## 推荐方案

**推荐方案 B：完全自建翻译 Plugin**

理由：
1. **零外部依赖风险** — 不依赖已停止维护的包，不需要 Payload 大版本升级
2. **完全控制** — Lexical 遍历逻辑可从 payload-enchants 源码学习（MIT 协议），但自己实现，确保与 Payload 3.69 兼容
3. **长期收益** — 自建代码可随 Payload 版本演进灵活调整，不受上游制约
4. **REST API 原生支持** — 原设计中 4 个 REST endpoint 本身就是自建部分
5. **Resolver 架构简单** — 接口定义清晰（`resolve(texts, from, to) → translatedTexts`），自建成本低

### 与原设计文档的差异

| 项目 | 原设计 | 调整后 |
|------|--------|--------|
| 文档级翻译引擎 | @payload-enchants/translator | **自建**，参考其 Lexical traversal 逻辑 |
| Resolver 架构 | 复用 enchants | **自建**，接口一致但独立实现 |
| Admin UI 文档级翻译 | enchants Modal | **自建翻译按钮 + Modal** |
| 其他功能 | 不变 | 不变（REST API、批量、字段级、状态追踪） |

### 自建需要额外实现的模块

| 模块 | 复杂度 | 说明 |
|------|--------|------|
| Lexical JSON 递归遍历 | 中 | 遍历 Lexical 树，提取/替换文本节点。可参考 enchants 的 `traverseRichText.ts` |
| Resolver 接口 + OpenAI 实现 | 低 | 简单的 `resolve(texts, from, to)` 接口 + OpenAI Chat API 调用 |
| 文档级翻译操作 | 中 | 遍历集合 fields → 识别 localized 字段 → 按类型提取文本 → 调 resolver → 写回 |
| Admin UI 翻译按钮 | 低 | `.client.tsx` 组件，调用自建 REST API |

## 详细设计

### 文件结构（沿用原设计，移除 enchants 依赖）

```
src/plugins/translation/
├── index.ts                              # Plugin 入口
├── config.ts                             # Config 类型定义
│
├── resolvers/                            # 翻译 Resolver（新增目录）
│   ├── types.ts                          # TranslationResolver 接口定义
│   ├── openai-resolver.ts                # OpenAI Chat API 实现
│   └── copy-resolver.ts                  # Copy resolver（测试用）
│
├── core/                                 # 核心翻译逻辑（新增目录）
│   ├── translate-operation.ts            # 文档级翻译操作（提取字段→翻译→写回）
│   ├── traverse-fields.ts               # 递归遍历 Payload fields，识别 localized 字段
│   └── traverse-rich-text.ts            # Lexical JSON 递归遍历，提取/替换文本节点
│
├── api/                                  # REST API 层（不变）
│   ├── translate-document.ts
│   ├── translate-field.ts
│   ├── translate-batch.ts
│   └── translation-status.ts
│
├── hooks/
│   └── compute-status.ts                # afterRead → 各 locale 翻译完成度
│
├── ui/                                   # Admin UI（不变）
│   ├── translation-status.client.tsx
│   ├── field-translate-button.client.tsx
│   ├── field-translate-modal.client.tsx
│   ├── batch-translate-button.client.tsx
│   └── batch-translate-modal.client.tsx
│
└── utils/
    ├── resolve-localized-fields.ts
    └── compute-completion.ts
```

### Resolver 接口定义

```typescript
// resolvers/types.ts
export interface TranslationResolver {
  key: string
  resolve: (args: {
    texts: string[]
    from: string
    to: string
  }) => Promise<{
    success: boolean
    translatedTexts: string[]
  }>
}
```

### Lexical 遍历策略

```typescript
// core/traverse-rich-text.ts
// Lexical JSON 是树结构，文本在 leaf 节点的 text 属性中
// 遍历算法：DFS，收集所有 text 节点 → 批量翻译 → 按原序回填
type LexicalNode = { type: string; text?: string; children?: LexicalNode[] }

function extractTexts(node: LexicalNode): string[] { /* DFS 收集 */ }
function replaceTexts(node: LexicalNode, translations: string[]): LexicalNode { /* DFS 回填 */ }
```

### 依赖变化

| 原设计 | 调整后 |
|--------|--------|
| `@payload-enchants/translator` | **移除** |
| `@payload-enchants/translator-resolver-openai` | **移除** |
| `mongodb-memory-server`（devDep） | 保留 |
| `openai`（新增） | OpenAI SDK，用于 resolver |

## 工作量评估

| 模块 | 预估 | 说明 |
|------|------|------|
| Resolver 架构 + OpenAI 实现 | 0.5 天 | 接口简单 |
| 核心翻译逻辑（traverse + operation） | 1.5 天 | Lexical 遍历是最大复杂点 |
| REST API 4 个 endpoint | 1 天 | 标准 CRUD 模式 |
| Admin UI 组件 | 1 天 | 5 个 .client.tsx 组件 |
| 翻译状态 hook + 工具函数 | 0.5 天 | afterRead 计算逻辑 |
| 测试（单元 + 集成） | 1.5 天 | 含 mongodb-memory-server 搭建 |
| **总计** | **6 天** | 预计提测: 2026-04-22 |

## 风险评估

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| Lexical 遍历边界情况（inline blocks、嵌套节点） | 中 | 翻译不完整 | 参考 enchants 源码 + 覆盖测试 |
| OpenAI API 速率限制 | 低 | 批量翻译受限 | chunkSize 控制，指数退避 |
| Payload 内部 API 变化 | 低 | hook/endpoint 注入失效 | 锁定 Payload 版本，集成测试保障 |

## 模块级实现指南（源码分析后更新）

> 基于对 `@payload-enchants/translator@1.3.0` 和 `@jhb.software/payload-content-translator-plugin@0.1.2` 源码的逐文件分析。两者均为 MIT 协议。

### 主要参考蓝本：jhb.software

| 维度 | enchants | jhb | 推荐 |
|------|---------|-----|------|
| Lexical inline block | 不支持，静默跳过 | 支持，双向递归 | **jhb** |
| virtual 字段处理 | 无 | 有（跳过） | **jhb** |
| blockReferences 全局注册表 | 无 | 有 | **jhb** |
| endpoint 认证守卫 | 无 | 有（401） | **jhb** |
| OpenAI prompt 质量 | 弱（裸 JSON 数组，gpt-3.5） | 强（json_object 模式，gpt-4o-mini） | **jhb** |
| 多 resolver 支持 | 有（数组） | 无（单个） | enchants（如需） |
| Slate 兼容 | 有 | 无 | enchants（如需） |

### M1: traverse-rich-text.ts — Lexical 富文本遍历

**实现思路**（参考 jhb）：

```
traverseRichText(args: { dataFrom, dataTranslated, onText }):
  function recurse(nodeFrom, nodeTranslated):
    // 文本节点：收集待翻译
    if nodeFrom.text !== undefined:
      onText({ valueFrom: nodeFrom.text, onTranslate: (t) => nodeTranslated.text = t })
      return

    // Lexical Block 节点：递归进入 block 字段
    if nodeFrom.type === 'block':
      blockConfig = findBlockConfigBySlug(nodeFrom.fields.blockType)
      if blockConfig:
        traverseFields({ fields: blockConfig.fields, dataFrom: nodeFrom.fields, ... })
      return

    // 其他节点：递归 children
    if nodeFrom.children:
      for i in range(nodeFrom.children.length):
        recurse(nodeFrom.children[i], nodeTranslated.children[i])
```

**关键点**：
- Lexical 格式检测：`'root' in richTextData`
- inline block 双向递归：`traverseRichText` → `traverseFields` → `traverseRichText`（需防死循环）
- link URL 不翻译（仅 `text` 子节点被 `nodeFrom.text` 检测命中）
- 空 RichText 字段：先判断 `!dataFrom || !dataFrom.root`，避免 enchants 的 `JSON.parse(undefined)` 崩溃

### M2: traverse-fields.ts — Payload 字段遍历

**实现思路**（参考 jhb，核心伪代码）：

```
traverseFields({ fields, dataFrom, dataTranslated, localizedParent, emptyOnly, valuesToTranslate }):
  for field in fields:
    if field.virtual → skip
    if field.custom?.translatorSkip → skip

    switch field.type:
      'tabs':
        for tab in field.tabs:
          if tab.name → 下钻子对象递归
          else → 同层递归（unnamed tab）

      'group':
        下钻 field.name 子对象递归

      'array':
        if localized || localizedParent:
          // 复制结构（保留 id/blockType），逐 item 递归
          for each item: 递归 field.fields

      'blocks':
        for each item:
          blockConfig = findBlockConfig(item.blockType, field.blocks, field.blockReferences)
          递归 blockConfig.fields

      'collapsible' | 'row':
        同层递归（不下钻子对象）

      'text' | 'textarea':
        if (localized || localizedParent) && !isSystemField(field.name):
          if emptyOnly && dataTranslated[field.name] 非空 → skip
          valuesToTranslate.push({ value: dataFrom[field.name], onTranslate: ... })

      'richText':
        检测 Lexical → 调用 traverseRichText
        (如需 Slate 兼容 → Array.isArray 分支)

      'date' | 'number' | 'relationship' | 'upload' | ...:
        原样复制到 dataTranslated（不翻译）
```

**localized 传播**：字段自身 `field.localized === true` 或父级传入 `localizedParent === true`。

### M3: translate-operation.ts — 翻译操作核心

**流程**（两包完全一致）：

```
1. payload.findByID({ id, locale: localeFrom, depth: 0 })  → dataFrom
2. payload.findByID({ id, locale: localeTo, depth: 0 })    → dataTranslated（若未传 data）
3. valuesToTranslate = []
4. traverseFields({ fields: collection.fields, dataFrom, dataTranslated, valuesToTranslate })
5. texts = valuesToTranslate.map(v => v.value).filter(Boolean)
6. result = resolver.resolve({ texts, from: localeFrom, to: localeTo })
7. result.translatedTexts.forEach((t, i) => {
     decoded = he.decode(t)        // HTML entity 解码
     valuesToTranslate[i].onTranslate(decoded)  // 闭包回写
   })
8. if update → payload.update({ id, data: dataTranslated, locale: localeTo })
9. return { success: true, translatedData }
```

**关键点**：
- `depth: 0` 避免加载关联文档
- `he.decode` 处理 OpenAI 返回的 HTML entities（如 `&amp;` → `&`）
- `onTranslate` 闭包持有节点引用，翻译后原地写入

### M4: openai-resolver.ts — OpenAI 翻译实现

**推荐参考 jhb 版本**（更稳健）：

```
resolve({ texts, localeFrom, localeTo }):
  chunks = chunkArray(texts, chunkLength=100)
  allTranslated = []
  for chunk in chunks:
    response = openai.chat.completions.create({
      model: 'gpt-4o-mini',
      response_format: { type: 'json_object' },
      messages: [
        { role: 'system', content: systemPrompt(localeFrom, localeTo) },
        { role: 'user', content: JSON.stringify(chunk) }
      ]
    })
    parsed = JSON.parse(response.choices[0].message.content)
    allTranslated.push(...parsed.translations)
  return { success: true, translatedTexts: allTranslated }
```

**关键点**：
- `response_format: { type: 'json_object' }` 确保返回可解析 JSON
- prompt 要求返回 `{"translations": ["...", "..."]}` 结构
- 分块处理（chunkLength=100），避免 token 超限
- 需添加：指数退避重试（enchants/jhb 都没有）

### M5: Plugin 注入模式

```
tripoTranslationPlugin(config) → (payloadConfig) => {
  // 1. 注入 endpoint
  payloadConfig.endpoints.push({ path: '/translate/document', method: 'post', handler: ... })
  // ... 4 个 endpoint

  // 2. 存储 resolver 引用
  payloadConfig.custom.translator = { resolvers: config.resolvers }

  // 3. 注入 UI 组件到目标 collections
  payloadConfig.collections = payloadConfig.collections.map(collection => {
    if (!config.collections.includes(collection.slug)) return collection
    return {
      ...collection,
      admin: {
        ...collection.admin,
        components: {
          ...collection.admin?.components,
          edit: {
            // 替换 SaveButton/PublishButton 加上翻译按钮
            SaveButton: CustomButtonWithTranslator,
          }
        }
      },
      hooks: {
        ...collection.hooks,
        afterRead: [...(collection.hooks?.afterRead || []), computeTranslationStatus]
      }
    }
  })

  return payloadConfig
}
```

## 最终决策

**方案 B：完全自建，以 jhb.software 源码为主要参考蓝本。**

用户已确认，不引入外部翻译插件依赖。

## 测试计划（详细版）

### 现有测试基建

| 项目 | 状态 |
|------|------|
| Vitest | ✅ 已配置（`vitest.config.mts`，jsdom 环境） |
| 单元测试约定 | `src/**/__tests__/**/*.spec.ts` |
| 集成测试约定 | `tests/int/**/*.int.spec.ts` |
| E2E 测试 | ✅ Playwright 已配置 |
| mongodb-memory-server | ❌ 未安装，当前集成测试连真实数据库 |

### 测试基建升级

**新增 devDependency**：`mongodb-memory-server`

现有集成测试直接连接真实数据库（`tests/int/api.int.spec.ts`），翻译 Plugin 的集成测试需要隔离环境。方案：

```typescript
// tests/int/helpers/test-payload.ts
import { MongoMemoryServer } from 'mongodb-memory-server'
import { getPayload, Payload } from 'payload'

let mongo: MongoMemoryServer
let payload: Payload

export async function setupTestPayload(): Promise<Payload> {
  mongo = await MongoMemoryServer.create()
  process.env.DATABASE_URI = mongo.getUri()
  const config = await import('@/payload.config')
  payload = await getPayload({ config: await config.default })
  return payload
}

export async function teardownTestPayload() {
  await mongo.stop()
}
```

### 三层测试架构

#### 第 1 层：单元测试（纯逻辑，无 Payload 依赖）

位置：`src/plugins/translation/**/__tests__/*.spec.ts`

**M1: traverse-rich-text.spec.ts**

| 用例 | 输入 | 期望 |
|------|------|------|
| 纯文本段落 | `{ root: { children: [{ type: 'paragraph', children: [{ text: 'Hello' }] }] } }` | 收集 1 个文本，回填后 text 变更 |
| 多段落多文本 | 3 个段落，各含 1-2 个文本节点 | 按 DFS 序收集所有文本 |
| 空 RichText | `null` / `undefined` / `{}` | 不崩溃，返回空数组 |
| 空 root | `{ root: { children: [] } }` | 返回空数组 |
| heading 节点 | `{ type: 'heading', tag: 'h2', children: [{ text: 'Title' }] }` | 正确收集 heading 文本 |
| link 节点 | `{ type: 'link', url: '...', children: [{ text: 'click' }] }` | 收集 'click'，不翻译 URL |
| 嵌套格式 | bold + italic + text 嵌套 | 仅收集 leaf 的 text 属性 |
| inline block | `{ type: 'block', fields: { blockType: 'cta', text: 'Buy' } }` | 递归进入 block fields 收集 |
| 混合内容 | 段落 + heading + link + block 混合 | 按 DFS 序完整收集 |

**M2: traverse-fields.spec.ts**

| 用例 | 输入 | 期望 |
|------|------|------|
| 顶层 localized text | `[{ name: 'title', type: 'text', localized: true }]` | 收集 1 个值 |
| 非 localized text | `[{ name: 'slug', type: 'text', localized: false }]` | 跳过，不收集 |
| 嵌套 group | `[{ type: 'group', name: 'meta', fields: [{ name: 'desc', type: 'text', localized: true }] }]` | 下钻 group 收集 desc |
| array（localized parent） | `[{ type: 'array', name: 'items', localized: true, fields: [...] }]` | 逐 item 递归 |
| blocks | `[{ type: 'blocks', name: 'layout', blocks: [...] }]` | 按 blockType 匹配 config 递归 |
| tabs（named） | named tab → 下钻子对象 | 正确处理 |
| tabs（unnamed） | unnamed tab → 同层递归 | 正确处理 |
| collapsible/row | 同层递归不下钻 | 正确处理 |
| emptyOnly=true 已有值 | 目标语言已有翻译 | 跳过该字段 |
| emptyOnly=true 空值 | 目标语言值为空 | 收集该字段 |
| emptyOnly=false | 目标语言已有翻译 | 仍然收集 |
| translatorSkip 标记 | `field.custom.translatorSkip = true` | 跳过该字段 |
| virtual 字段 | `field.virtual = true` | 跳过 |
| richText 字段 | `{ type: 'richText', localized: true }` | 调用 traverseRichText |
| date/number/upload | 非文本类型字段 | 原样复制，不翻译 |

**M3: compute-completion.spec.ts**

| 用例 | 输入 | 期望 |
|------|------|------|
| 全部 locale 有值 | 7 个 locale 都有 title + content | 各 locale 均 'complete' |
| 部分 locale 缺失 | ja/ko 的 title 为空 | ja/ko 为 'partial'，其余 'complete' |
| 某 locale 全部缺失 | ru 所有字段为空 | ru 为 'missing' |
| 空 richText | content 为 `{ root: { children: [] } }` | 视为 'missing' |
| 仅有源语言 | 只有 en 有值 | 其余 6 个 locale 均 'missing' |

**M4: openai-resolver.spec.ts**（mock OpenAI API）

| 用例 | 输入 | 期望 |
|------|------|------|
| 正常翻译 | 3 个文本 en→zh | 返回 3 个中文翻译 |
| 空文本数组 | `texts: []` | 返回 `{ success: true, translatedTexts: [] }` |
| 分块翻译 | 150 个文本，chunkLength=100 | 分 2 次调用 API |
| API 返回错误 | mock 500 | 返回 `{ success: false }` |
| HTML entity | API 返回 `&amp;` | 解码为 `&` |

**M5: copy-resolver.spec.ts**

| 用例 | 输入 | 期望 |
|------|------|------|
| 复制翻译 | texts=['Hello'] | 返回 ['Hello']（原样复制） |

**M6: plugin-injection.spec.ts**

| 用例 | 输入 | 期望 |
|------|------|------|
| 目标集合注入 hook | 配置 collections: ['posts'] | posts 的 afterRead 包含 computeStatus |
| 非目标集合不注入 | 配置 collections: ['posts']，检查 users | users 无变化 |
| endpoint 注入 | 任意配置 | config.endpoints 包含 4 个翻译路由 |
| resolver 存储 | 配置 resolvers | config.custom.translator.resolvers 有值 |

#### 第 2 层：集成测试（Payload + mongodb-memory-server）

位置：`tests/int/translation/*.int.spec.ts`

使用 `copyResolver`（确定性，零费用），验证端到端数据流。

**translate-document.int.spec.ts**

| 用例 | 操作 | 验证 |
|------|------|------|
| 翻译文档 | 创建 Post（en），POST /translate/document → zh | 返回 translatedData，zh 字段有值 |
| 翻译带 RichText | 创建含 Lexical content 的 Post，翻译 | RichText 文本节点被翻译 |
| emptyOnly=true | 先手动设 zh.title，再翻译 | title 不变，其他空字段被翻译 |
| emptyOnly=false | 先手动设 zh.title，再翻译 | title 也被覆盖 |
| 文档不存在 | POST 不存在的 id | 返回 404 |
| 未认证 | 不带 auth header | 返回 401 |

**translate-field.int.spec.ts**

| 用例 | 操作 | 验证 |
|------|------|------|
| 翻译单字段 | POST fieldPath='title' | 仅 title 被翻译 |
| 嵌套字段路径 | POST fieldPath='meta.description' | 仅 meta.description 被翻译 |
| 不存在的字段路径 | POST fieldPath='xxx' | 返回 400 |

**translate-batch.int.spec.ts**

| 用例 | 操作 | 验证 |
|------|------|------|
| ids 模式 | 3 篇 Post，翻译到 zh | total=3, success=3 |
| filter 模式 | where: { _status: 'published' } | 仅翻译已发布 |
| 多目标语言 | to: ['zh', 'ja'] | 两种语言都翻译 |
| 部分失败 | 1 篇有错误数据 | total=3, success=2, failed=1, errors=[...] |
| 空结果 | filter 匹配 0 篇 | total=0 |

**translation-status.int.spec.ts**

| 用例 | 操作 | 验证 |
|------|------|------|
| 单文档状态 | 创建 Post（en+zh），查询状态 | en='complete', zh='complete', 其余='missing' |
| 集合级统计 | 不传 id | 返回整体统计 |

#### 第 3 层：E2E 测试（Playwright）

位置：`tests/e2e/translation.spec.ts`

使用 `copyResolver`，验证用户操作流程。

| 用例 | 操作 | 验证 |
|------|------|------|
| Sidebar 状态显示 | 进入 Post 编辑页 | sidebar 显示各语言状态徽标 |
| 文档级翻译 | 点击 Translate 按钮 → 选目标语言 → 确认 | 表单字段被填充翻译值 |
| 字段级翻译 | 点击 title 旁翻译图标 → 选语言 | 仅 title 被翻译 |
| 批量翻译 | 列表页勾选 3 篇 → 批量翻译 → 确认 | Toast 显示翻译完成统计 |

### 覆盖率目标

| 层级 | 目标 | 说明 |
|------|------|------|
| 单元测试 | **90%+** | core/ + resolvers/ + utils/ |
| 集成测试 | **80%+** | api/ 4 个 endpoint 全覆盖 |
| E2E | 关键路径 | 4 个用户操作场景 |

### 测试数据 Fixtures

```typescript
// tests/fixtures/translation.ts
export const samplePost = {
  title: 'AI 3D Model Generation',
  content: {
    root: {
      type: 'root',
      children: [
        { type: 'paragraph', children: [{ text: 'Generate 3D models from text.' }] },
        { type: 'heading', tag: 'h2', children: [{ text: 'Features' }] },
      ]
    }
  },
  meta: {
    title: 'AI 3D Generation | Tripo',
    description: 'Create 3D models instantly with AI.',
  }
}

export const samplePostWithInlineBlock = {
  // ... content 含 inline CTA block
}

export const emptyRichText = { root: { type: 'root', children: [] } }
export const nullRichText = null
```
