# 飞书知识库同步

任务文档必须同步到飞书知识库，让其他用户（产品、测试等）可查看。

## Wiki 配置

| 配置项 | 值 |
|--------|-----|
| 根节点 | `DkKUwmCnXicsnjkmyrocVFpanrf`（"CMS 相关文档"） |
| Space ID | `7578727610281118948` |
| URL | https://a9ihi0un9c.feishu.cn/wiki/DkKUwmCnXicsnjkmyrocVFpanrf |

## Wiki 目录结构

```
CMS 相关文档（根节点）
├── REQ-recXxx CMS 系统权限规整/        ← 需求子目录（docx 节点）
│   ├── 需求评审                         ← review.md
│   ├── 技术方案                         ← technical-solution.md
│   ├── 代码审查报告                     ← code-review-*.md
│   ├── 集成测试计划                     ← integration-test-plan.md
│   └── 集成测试报告                     ← integration-test-report.md
├── REQ-recYyy Blog SEO 优化/
│   └── ...
```

## 同步时机

**铁律：在 `tasks/` 目录下写入任何 `.md` 文件（STATUS.md 除外）后，必须查映射表决定是否同步到 wiki。不确定时同步，不要跳过。**

必须同步的文件（穷举）：

| 本地文件 | 产生阶段 | Wiki 标题 |
|----------|---------|-----------|
| review.md | requirement 步骤 3 需求评审 | 需求评审 |
| technical-solution.md | requirement 步骤 5 技术评审 | 技术方案 |
| bug-investigation.md | bugfix 步骤 3 调查 | Bug 定位报告 |
| code-review-*.md | requirement 步骤 8.1 / bugfix 步骤 6.1 Code Review | 代码审查报告 |
| integration-test-plan.md | requirement 步骤 8.2 / bugfix 步骤 6.2 测试计划 | 集成测试计划 |
| integration-test-report.md | requirement 步骤 8.4 / bugfix 步骤 6.4 验证报告 | 集成测试报告 |

不同步的文件：
- STATUS.md（频繁变更，仅本地跟踪）
- notes/ 下的临时笔记

## 同步流程

所有飞书 API 调用 → 委托 **lark-wiki** / **lark-doc** skill。本 skill 仅负责给出业务参数。

### 步骤 1：检查/创建需求子目录节点（→ lark-wiki）

首次为该需求同步时，在根节点下创建子目录节点。

| 业务参数 | 值 |
|---|---|
| space_id | `7578727610281118948` |
| parent_node_token | `DkKUwmCnXicsnjkmyrocVFpanrf` |
| obj_type | `docx` |
| title | `{类型}-{ID} {需求简述}` |

返回的 `node_token` 记入 STATUS.md 的关联资源区，后续文档挂在此节点下。

### 步骤 2：创建文档节点（→ lark-wiki）

在需求子目录下创建文档节点。

| 业务参数 | 值 |
|---|---|
| space_id | `7578727610281118948` |
| parent_node_token | 步骤 1 返回的 `node_token` |
| obj_type | `docx` |
| title | 见上方「同步时机」表格映射 |

### 步骤 3：写入内容（→ lark-doc）

将任务目录下的 markdown 文件内容写入对应 wiki 文档。

| 业务参数 | 值 |
|---|---|
| doc（obj_token） | 步骤 2 返回 |
| mode | `overwrite` |
| markdown 源 | 任务目录下的 md 文件（如 `review.md`） |

注意：markdown 文件路径若用 `@file` 传入，必须用相对路径，需先 `cd` 到任务目录。

## STATUS.md 关联资源更新

同步后在 STATUS.md 的"关联资源"区记录 wiki 信息：

```markdown
## 关联资源

- Wiki 子目录: <node_token>（<wiki URL>）
- Wiki 文档:
  - 需求评审: <obj_token>
  - 技术方案: <obj_token>
```

## 通知引用规范

**凡飞书通知涉及已同步到 wiki 的文档，消息体必须包含完整 wiki URL，让非本地用户可直接点击查看。**

- Wiki URL 格式：`https://vastai3d.feishu.cn/wiki/<node_token>`
- 适用范围：不限于 tripo-requirement 的 4 个通知节点，任何飞书消息引用 wiki 文档时都必须附带链接
- 多个文档时逐行列出所有链接
- `node_token` 从步骤 1 创建子目录节点时的返回值（→ lark-wiki skill）或 STATUS.md 关联资源区获取

## 下游消费契约

wiki 同步产出的 `node_token` 是下游通知的输入：

```
wiki 同步（产出 node_token）→ 记入 STATUS.md → 通知模板引用（tripo-notify 占位符 <Wiki 文档链接>）
```

确保 node_token 在同步完成后立即记入 STATUS.md，通知发送时从 STATUS.md 读取并拼接为完整 URL。
