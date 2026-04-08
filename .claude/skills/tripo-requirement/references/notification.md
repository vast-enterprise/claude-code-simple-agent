# 飞书通知机制

## 概述

在需求开发流程的 **4 个关键决策节点**，agent 通过飞书私聊通知用户，然后**暂停等待确认**后继续。

## 用户配置

| 配置项 | 值 |
|--------|-----|
| 通知对象 | 郭凯南 |
| open_id | `ou_8adc8aca7ad728142eb6669e5b13fb52` |
| 通知方式 | 飞书私聊（bot → user） |

## 通知协议

```
1. 执行步骤工作（输出文档/创建 PR/准备上线）
2. 发送飞书通知（通知命令见下方）
3. 暂停，等待用户确认
4. 用户确认后继续下一步
```

## 通知命令

```bash
lark-cli im +messages-send \
  --as bot \
  --user-id ou_8adc8aca7ad728142eb6669e5b13fb52 \
  --text "<消息内容>"
```

> - 必须使用 `--as bot`（应用身份），不要用默认的 user 身份（需要额外 OAuth 授权）
> - 使用 `$'...'` 语法保留多行格式。

## 4 个通知节点

### 节点 1：需求评审确认（步骤 3）

**触发时机**: review.md 输出完成，提议状态变更为"定容确认"之后

```bash
lark-cli im +messages-send \
  --as bot \
  --user-id ou_8adc8aca7ad728142eb6669e5b13fb52 \
  --text $'[需求评审完成]\n需求: <需求名称>\n状态: 已输出评审文档，提议变更为"定容确认"\n操作: 请在 Claude Code 中确认容量，或提出修改意见'
```

### 节点 2：技术评审确认（步骤 5）

**触发时机**: technical-solution.md 输出完成，提议"技术评审"="完成"之后

```bash
lark-cli im +messages-send \
  --as bot \
  --user-id ou_8adc8aca7ad728142eb6669e5b13fb52 \
  --text $'[技术方案完成]\n需求: <需求名称>\n状态: 已输出技术方案文档\n操作: 请在 Claude Code 中确认方案，或提出修改意见'
```

### 节点 3：自动化闭环完成（步骤 8）

**触发时机**: Code Review + 集成测试全部通过之后

```bash
lark-cli im +messages-send \
  --as bot \
  --user-id ou_8adc8aca7ad728142eb6669e5b13fb52 \
  --text $'[PR 已完成验证]\n需求: <需求名称>\nPR: <PR 链接>\n\n✅ Code Review: 通过\n✅ 集成测试: 通过\n\n报告: tasks/$TASK_ID/integration-test-report.md\n\n操作: 请 review 并合并'
```

### 节点 4：上线前确认（步骤 10）

**触发时机**: 用户验收通过，准备发布上线之前

```bash
lark-cli im +messages-send \
  --as bot \
  --user-id ou_8adc8aca7ad728142eb6669e5b13fb52 \
  --text $'[准备上线]\n需求: <需求名称>\n状态: 用户验收已通过\n操作: 请确认是否发布上线'
```

## 消息模板中的占位符

| 占位符 | 替换为 |
|--------|--------|
| `<需求名称>` | 当前需求的简短描述 |
| `<PR 链接>` | 创建的 PR URL |

## 注意事项

- 发送前用 `--dry-run` 预览消息内容，确认无误后去掉 `--dry-run` 实际发送
- 通知后**必须暂停**，不可自动继续下一步
- 如果通知发送失败，在终端提示用户，不阻塞流程
