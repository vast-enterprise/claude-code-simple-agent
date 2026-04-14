# Tripo Avatar — LLM 文档索引

> 本目录为 LLM Agent 优化的项目文档。人类开发者请直接阅读源码。

## 阅读顺序

1. 先读 `overview/` 了解项目全貌
2. 按需读 `architecture/` 理解系统设计
3. 操作时参考 `guides/` 和 `reference/`

## 目录

### overview/
| 文档 | 说明 |
|------|------|
| [project-overview.md](overview/project-overview.md) | 项目定位、技术栈、模块结构 |

### architecture/
| 文档 | 说明 |
|------|------|
| [event-pipeline.md](architecture/event-pipeline.md) | 事件驱动管道、query/response 解耦模型（send_message + session_reader）、富消息预处理、per-session FIFO 队列、reader task 生命周期、/interrupt 指令、session resume |
| [observability.md](architecture/observability.md) | 可观测性体系：异常通知、session 持久化、历史归档、指标收集、HTTP API、Dashboard、Session 详情页、历史记录页、Conversation API、名字解析 |
| [lark-interaction.md](architecture/lark-interaction.md) | 飞书交互层：消息回复、表情反馈、事件订阅、富消息解析（merge_forward/image/file/audio/video/sticker/media） |
| [permission-model.md](architecture/permission-model.md) | 双层权限模型：代码强制 + prompt 约束 |
| [persona-system.md](architecture/persona-system.md) | 人格注入机制、边界规则、OKR |
| [skill-integration.md](architecture/skill-integration.md) | Skill 加载、路由、与 Agent 系统的配合 |

### guides/
| 文档 | 说明 |
|------|------|
| [configuration.md](guides/configuration.md) | 配置、环境变量、飞书前置配置、启动方式 |
| [testing.md](guides/testing.md) | 测试策略、Mock 方式、运行方式、覆盖范围 |

### reference/
| 文档 | 说明 |
|------|------|
| [coding-conventions.md](reference/coding-conventions.md) | 编码规范：模块组织、命名、异步模式、lark-cli 铁律 |
| [git-conventions.md](reference/git-conventions.md) | Git 约定：commit 格式、分支策略 |
