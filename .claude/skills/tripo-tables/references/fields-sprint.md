# Sprint 版本计划

**Table ID**: `tblm2FGJjiK4frzt`
**Base Token**: `HMvbbjDHOaHyc6sZny6cMRT8n8b`

## 字段结构

| 字段名 | Field ID | 类型 | 说明 |
|--------|----------|------|------|
| 版本计划 | `fldSJQfqQD` | text | 版本描述 |
| 班车状态 | `fldrcs9dZA` | select | 发车状态 |
| 上线类型 | `fldsqiHgP9` | select | 上线类型 |
| 版本Owner | `fld2eddfWB` | user | 版本负责人 |
| 前端发车owner | `fldsZ3XVVM` | user | 前端发车负责人 |
| 后端发车owner | `fld6iV4WQn` | user | 后端发车负责人 |
| 算法发车owner | `fld1E66DVA` | user | 算法发车负责人 |
| 预计发布日期 | `fldrnlaVAx` | datetime | 计划发布日期 |
| 实际发布日期 | `fldCaHckyx` | datetime | 实际发布日期 |
| 涉及项目 | `fld22nLpq1` | text | 涉及的项目 |
| 关联需求 | `fldM9DrUxr` | text | 关联的需求 |

## 状态选项

**班车状态** (`fldrcs9dZA`)

| 选项 | 说明 |
|------|------|
| 未启动 | 发车未开始 |
| 已启动 | 发车进行中 |
| 已完成 | 发车完成 |

**上线类型** (`fldsqiHgP9`)

| 选项 | 说明 |
|------|------|
| 跟车 | 常规发车 |
| hotfix | 紧急修复 |
| sss | SSS级紧急需求 |

## 部署状态字段

| 字段名 | Field ID | 类型 | 说明 |
|--------|----------|------|------|
| 前端部署完毕 | `fldy6ym5PN` | checkbox | 前端部署完成标记 |
| 后端部署完毕 | `fldWGA6C5g` | checkbox | 后端部署完成标记 |
| 算法部署完毕 | `fldDgrQRTd` | checkbox | 算法部署完成标记 |
