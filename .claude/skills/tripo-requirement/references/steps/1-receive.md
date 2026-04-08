# 步骤 1：接收需求 & 创建目录

## 前置条件

- 用户提供了需求描述、PRD 链接、飞书文档或需求 ID

## 做什么

1. **解析输入来源**：
   - 文字描述
   - 本地文件
   - 飞书 PRD 文档链接
   - 已录入的需求 ID

2. **判断需求状态**：
   - 已录入 → 获取需求详情，记录 ID
   - 未录入 → 使用临时 ID（如 `new-001`）

3. **创建任务跟踪目录**：
   按 `tripo-task-tracking` skill 的目录命名规范和操作流程创建目录并初始化 STATUS.md。

## 如何定义完成

- [ ] 任务目录已创建（符合 `tripo-task-tracking` 命名规范）
- [ ] STATUS.md 已初始化
- [ ] 基本信息已填写（需求描述、Owner 等）
- [ ] 已判断需求是否已录入表格

## 目录命名规范

参见 `tripo-task-tracking` skill 的目录命名规范。示例：

```
tasks/2026-04-02_REQ-recXxx_blog-seo-optimize/
tasks/2026-04-02_REQ-new-001_payment-refactor/
```