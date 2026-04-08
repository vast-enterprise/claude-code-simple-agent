# 需求 Bug 管理

**Table ID**: `tblkGH8uvmXS80CB`
**Base Token**: `HMvbbjDHOaHyc6sZny6cMRT8n8b`

## 字段结构

| 字段名 | Field ID | 类型 | 说明 |
|--------|----------|------|------|
| bugID | `fldeY0sN5p` | auto_number | 自动编号 |
| taskID/traceID | `fldEm1JpCR` | text | 任务/追踪ID |
| bug 描述 | `fld4JONHiA` | text | Bug描述 |
| 复现步骤 | `fld1A4hos0` | text | 复现步骤 |
| 进度 | `fldXOSCtZt` | select | Bug处理进度 |
| 优先级 | `fldkViwpfm` | select | 优先级 |
| 类型 | `fldvhQ0Hob` | select | Bug类型 |
| 发现阶段 | `fldb7fTV6H` | select | 发现阶段 |
| 指派人 | `fldVS07aUP` | user | 指派人员 |
| 创建人 | `fld1mMy65N` | created_by | 系统字段 |
| 创建日期 | `fldOKDPLYr` | created_at | 系统字段 |
| 关联需求 | `fldFVCn91G` | link | 关联需求 |
| 备注 | `fldemHmVhH` | text | 备注 |
| 附件 | `fldoROWfIe` | attachment | 附件 |

## 状态选项

**进度** (`fldXOSCtZt`)

| 选项 | 说明 |
|------|------|
| Open | 待处理 |
| In progress | 处理中 |
| Resolved | 已解决 |
| Closed | 已关闭 |
| Not bug | 非Bug |
| Delay | 延期处理 |
| Crash | 崩溃问题 |
| Reopened | 重新打开 |

**优先级** (`fldkViwpfm`)

| 选项 | 说明 |
|------|------|
| P0 | 最高优先级 |
| P1 | 高优先级 |
| P2 | 普通优先级 |
