# Bug 调查报告：Lexical 富文本 SSR 渲染空标签

## Bug 现象

CMS 使用 Lexical 富文本编辑器创建的文章，插入 blockquote（引用块）、ul/ol（有序/无序列表）、table（表格）后，发布到线上：

- **CMS 编辑器内**：内容显示正常
- **前端 Nuxt SSR 页面**：上述元素渲染为空标签，内容全部丢失

**报告人**：丁靖（2026-04-14）

## 环境

- **环境**：线上 + staging
- **仓库**：`fe-tripo-homepage`
- **Staging 复现**：https://web-testing.tripo3d.ai/blog/blockquote-test-2026-04-15

## 根因分析

### 1. 缺陷代码位置

富文本转换器 `app/components/rich-text/converter/converters/` 下 3 个文件，合计 6 处：

| 文件 | 行数 | 元素 |
|------|------|------|
| `blockquote.ts` | ~21 | `<blockquote>` |
| `list.ts` | ~64 | `<ul>` / `<ol>` |
| `list.ts` | ~132 | `<li>` |
| `table.ts` | ~55 | `<table>` 外层 |
| `table.ts` | ~93 | `<td>` / `<th>` |
| `table.ts` | ~105 | `<tr>` |

### 2. 根因：`() => children` 函数形式 + 原生 HTML 元素 + SSR

Vue 3 的 `h()` 函数对 children 有两种形式：

```typescript
// 函数形式（slots）
h('blockquote', null, () => children)

// 数组形式（直接子节点）
h('blockquote', null, children)
```

**关键差异**：

| 形式 | shapeFlag | SSR 渲染器处理 |
|------|-----------|--------------|
| `children`（数组） | `ARRAY_CHILDREN (16)` | ✅ 正常渲染 |
| `() => children`（函数） | `SLOTS_CHILDREN (32)` | ✅ Vue 组件正常（处理 default slot） |

**SSR 渲染器的盲区**：Vue 3 的 SSR 渲染器（`vue-server-renderer`）对**原生 HTML 元素**（如 `blockquote`、`ul`、`table`）只处理 `ARRAY_CHILDREN (16)` 和 `TEXT_CHILDREN (8)`。当传入 `() => children` 函数形式时，shapeFlag 变为 `SLOTS_CHILDREN (32)`，SSR 渲染器跳过不处理，导致内容为空。

**客户端为什么不报错**：Vue 3 客户端渲染（CSR）能正确处理函数形式的 children，会调用该函数并渲染返回的子节点。所以 CMS 预览和浏览器端 hydration 之后都"看起来正常"，只有纯 SSR 输出有问题。

### 3. 触发条件

同时满足以下三个条件才会触发：
1. 使用 `h()` 的函数形式 `() => children`
2. 应用在**原生 HTML 元素**（非 Vue 组件）
3. 在 **Nuxt SSR** 环境渲染

## 受影响范围

| 元素 | 文件 | 行 | 触发场景 |
|------|------|----|---------|
| `<blockquote>` | `blockquote.ts` | 21 | 文章含引用块 |
| `<ul>/<ol>` | `list.ts` | 64 | 文章含有序/无序列表 |
| `<li>` | `list.ts` | 132 | 所有列表项 |
| `<table>/<tbody>` | `table.ts` | 55 | 文章含表格 |
| `<td>/<th>` | `table.ts` | 93 | 表格单元格 |
| `<tr>` | `table.ts` | 105 | 表格行 |

**不受影响**：`contentType=slate` 类型文章，以及其他 Lexical 节点（heading、paragraph、link 等）的 converter。

## 修复方案

将所有 6 处 `() => children` 改为 `children`，使 shapeFlag 从 `SLOTS_CHILDREN (32)` 变为 `ARRAY_CHILDREN (16)`，SSR 渲染器能正常处理。

```typescript
// 修复前（bug）
return h('blockquote', null, () => children);

// 修复后（正确）
return h('blockquote', null, children);
```

修复分支：`fix/ssr-empty-render`（commit `3be11ae`）

## 关联信息

- **引入时机**：converter 初始实现时误用了 Vue 组件 slot 的写法
- **所属仓库**：`fe-tripo-homepage`
- **Bug 表记录**：recvgPTEr2SYZL (Bug #275)
