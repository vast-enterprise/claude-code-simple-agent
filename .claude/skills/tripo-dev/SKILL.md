---
name: tripo-dev
description: |
  编码方法论：指导 agent 高质量完成编码工作。
  定义编码前的准备工作、编码过程的纪律、以及什么算"完成"。
  从 tripo-requirement step 6 中独立出来，可在任何编码场景中使用。

  触发条件（任一命中即触发）：
  - tripo-requirement 步骤 6 显式调用
  - 用户说"写代码"、"开始开发"、"编码"、"实现功能"
  - hotfix、重构、技术预研中涉及编码
  - 任何需要修改代码仓库的场景
---

# 编码方法论

## 一、开始编码前

> 🔴 **先了解，再动手**

### 1.1 进入仓库三步

```
进入代码仓库
│
├── 1. 读 llmdoc（铁律，不可跳过）
│   └── llmdoc/index.md + llmdoc/overview/ 全部读完
│
├── 2. 确认代码位置
│   ├── PR 未合入 → 从 worktree 工作
│   ├── PR 已合入 → 从主工作区工作
│   └── 新功能 → 创建 worktree（→ tripo-worktree）
│
└── 3. 装依赖
    └── pnpm install → 装完再跑 typecheck/lint
        （worktree 无 node_modules 时的 TS 诊断不可信）
```

### 1.2 先看 3 个同类

> 🔴 **添加新概念前，先找 3 个现有同类实现**

适用场景：添加新的环境变量、组件、endpoint、hook、collection、field、配置项……

```
要加什么新东西？
│
├── 1. grep 项目中已有的同类实现（至少 3 个）
│   └── 例：加 env var → grep 已有 env var 怎么管理
│   └── 例：加组件 → 看已有组件的文件结构和注册方式
│   └── 例：加 endpoint → 看已有 endpoint 的路由和响应格式
│
├── 2. 理解已有模式
│   └── 命名规范、文件位置、注册/配置方式、管理工具（如 Zod schema）
│
└── 3. 对齐后再写
    └── 沿用已有模式，不自创新路径
```

**为什么这很重要**：项目中往往有既定的抽象层（env 用 Zod schema、组件用特定注册方式）。绕过这些直接用原始 API（如 `process.env.XXX`）会导致：
- 新增内容与项目整体不一致
- 遗漏配套更新（.env.example、logEnv、importMap）
- 给后续维护埋坑

---

## 二、编码过程

### 2.1 TDD：先测试后实现

→ 加载 `superpowers:test-driven-development` skill 获取完整 TDD 方法论。

核心循环：RED（写失败测试）→ GREEN（最小实现）→ IMPROVE（重构）

### 2.2 UI 组件的集成闭环

对于 UI 组件（不限于 React/Vue/Payload admin），写完代码只是第一步：

```
代码写完
│
├── 1. 注册/配置
│   └── 框架要求的注册步骤（如 Payload: admin.components 配置）
│
├── 2. 构建产物更新
│   └── 需要重新生成的文件（如 Payload: payload generate:importmap）
│
├── 3. 路径格式确认
│   └── 对照已有组件的路径格式（先看 3 个同类）
│
└── 4. 运行时验证（见下方"什么算完成"）
```

### 2.3 启动服务

→ 查 `tripo-repos` skill 各仓库的 **Dev 启动注意事项**（含分支检查、依赖安装、环境变量、启动参数）。

---

## 三、什么算"完成"

### 3.1 完成的两个层次

| 层次 | 含义 | 证据 |
|------|------|------|
| **代码态完成** | 文件存在、编译通过 | lint + typecheck 通过 |
| **运行时完成** | 功能在浏览器/终端中可用 | 截图 / curl 响应 / 测试输出 |

> 🔴 **只有运行时完成才算真正完成**

- 写了 API endpoint → curl 证明返回正确响应
- 写了 UI 组件 → 启动服务 → 截图证明渲染在页面上
- 写了数据处理逻辑 → 运行测试 → 贴测试输出

"代码存在于文件系统" ≠ "功能在运行时工作"

### 3.2 完成 Checklist

```
- [ ] lint 通过
- [ ] typecheck 通过
- [ ] 测试已编写且通过
- [ ] 运行时验证已执行（证据标准 → tripo-test §3.2）
- [ ] 新增概念已对齐 3 个同类（命名、位置、注册方式）
- [ ] 配套文件已更新（.env.example、logEnv、importMap 等）
- [ ] llmdoc 同步（如涉及架构/模式/API 变更 → 使用 tr:recorder agent）
```
