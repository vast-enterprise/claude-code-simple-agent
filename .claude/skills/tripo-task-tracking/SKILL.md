---
name: tripo-task-tracking
description: |
  任务进度跟踪与生命周期管理。管理 tasks/ 目录下的任务状态：创建任务目录、初始化和更新 STATUS.md、归档已完成任务到 tasks-finished/。
  被 tripo-requirement 等流程 skill 显式调用，也可独立使用。

  触发条件：
  - 其他 skill（tripo-requirement、未来的 bugfix 流程）显式调用
  - "创建任务目录"、"更新任务状态"、"归档任务"、"任务跟踪"
  - "查看任务进度"、"任务列表"、"哪些任务在进行中"
---

# 任务进度跟踪

管理 `tasks/` → `tasks-finished/` 的完整生命周期。

## 目录结构

```
tasks/
├── 2026-04-02_REQ-recXxx_用户画像分析优化/
│   ├── STATUS.md                    # 状态追踪记录（实时更新）
│   ├── review.md                    # 需求评审文档
│   ├── technical-solution.md        # 技术方案文档
│   └── notes/                       # 其他笔记（可选）
│       └── meeting-2026-04-03.md
│
├── 2026-04-05_REQ-recYyy_支付流程重构/
│   └── ...
│
├── 2026-04-10_BUG-recZzz_首页加载问题修复/
│   └── ...
│
tasks-finished/                      # 已归档（完成/关闭的任务）
├── 2026-04-02_REQ-recAaa_已完成需求/
│   └── ...
```

## 目录命名规范

**格式**: `{日期}_{类型}-{ID}_{简述}`

| 部分 | 说明 | 示例 |
|------|------|------|
| 日期 | 需求启动日期 | `2026-04-02` |
| 类型 | REQ（需求）/ BUG（Bug修复） | `REQ` |
| ID | 表格 record-id 或编号 | `recXxx` |
| 简述 | ASCII 友好的简要描述（不超过20字） | `blog-seo-optimize` |

**示例**:
- `2026-04-02_REQ-recAbc123_blog-seo-optimize`
- `2026-04-05_BUG-recDef456_homepage-blank-fix`

## STATUS.md 模板

模板文件：[assets/STATUS.template.md](assets/STATUS.template.md)

创建任务时，复制模板并替换占位符（recXxx、日期、人员等）。模板包含完整的多阶段状态历史示例，展示了从需求录入到功能测试的典型生命周期记录方式。

## 状态标记

| 标记 | 含义 |
|------|------|
| ⏳ | 未启动 |
| 🔄 | 进行中 |
| ✅ | 已完成 |
| ⚠️ | 有风险 |
| ❌ | 已暂停/关闭 |

## 更新规则

### 必须更新 STATUS.md 的时机

1. **阶段状态变更时**
   - 开始某阶段：更新为 🔄
   - 完成某阶段：更新为 ✅
   - 遇到风险：更新为 ⚠️
   - 暂停开发：更新为 ❌

2. **PR 提交时**
   - 记录 PR 编号
   - 更新阶段状态

3. **需求变更时**
   - 在备注中记录变更内容
   - 更新预期交付时间（如有变化）

## 操作

### 创建任务

```bash
mkdir -p tasks/{日期}_{类型}-{ID}_{简述}/notes
```

然后初始化 STATUS.md：填写基本信息，添加第一条状态历史记录。

### 归档任务

任务完成（上线/关闭）后，所有阶段均为 ✅ 或 ❌ 时：

```bash
mv tasks/{目录名} tasks-finished/
```
