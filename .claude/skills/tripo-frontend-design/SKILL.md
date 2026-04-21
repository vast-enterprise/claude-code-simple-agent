---
name: tripo-frontend-design
description: |
  Tripo 视觉原型方法论：指导 designer agent 把技术方案翻译成可演示高保真 HTML 原型。
  定义原型产物规范、归档位置、aesthetic 方向选型流程、与 Tripo 产品线视觉语言对齐规则、
  交接清单。美学层实现指导引用 @anthropic/frontend-design。

  触发条件（任一命中即触发）：
  - 已有 review.md + technical-solution.md，需要输出 prototype/index.html
  - 用户说"做个原型"、"页面长啥样"、"视觉怎么做"
  - tripo-requirement step 5 涉及 UI 的子任务
  - 原型评审反馈调整

  不触发场景：
  - 需求还没澄清完 → tripo-planning
  - 方案没定 → tripo-architecture
  - 方案已确定、要写生产代码 → tripo-dev
  - 纯后端 / 纯数据 / 无 UI 变更的需求（跳过 designer）

  美学层实现指导（字体 / 颜色 / 动效 / 避免 AI slop）引用 `@anthropic/frontend-design`
  （通过插件市场加载），本 skill 不重复讲美学方法论。
---

# Tripo 视觉原型方法论

## 总则：原型是用来对齐的，不是用来好看的

视觉原型不是设计师的艺术作品，是**整条需求链在"视觉落地"这一关的唯一验收凭据**。用户看到原型拍板"就这样"，developer 照着原型实现，tester 照着原型验收——原型含糊一次，下游所有人拿着各自脑补的图景做事，最后在验收阶段对账。

所以 Tripo 对原型的第一要求不是美，是**可对齐**：
1. **可演示**：浏览器里双击打开就能看
2. **可验收**：review.md 验收标准每一条都能在原型里指出来
3. **可追溯**：aesthetic 方向和产品线视觉语言的对齐关系写在 README.md 里

美学层（`@anthropic/frontend-design`）解决"怎么不做成 AI slop"；本 skill 解决"在 Tripo 体系里这份原型放哪、怎么组织、怎么和方案对接、怎么交给 developer"。

## 原型产物规范

### 目录结构（固定）

```
tasks/<task-dir>/prototype/
├── index.html            # 主原型入口
├── README.md             # 启动方式 + 验收点映射 + 版本痕迹
├── css/                  # 样式
├── js/                   # 交互逻辑（纯 mock，不调真实 API）
├── assets/               # 图片 / 字体 / icon
├── data/                 # mock 数据（sample.json 等）
└── components/           # （可选）单独打磨的组件，带独立 demo
    └── <component>/
        ├── demo.html
        └── ...
```

### 产物硬要求

- **`index.html` 必须能 `open` 或本地 server 直接打开跑通**——打不开的不算交付
- **所有数据必须 mock**——不调 live API、不连 CMS、不接埋点
- **响应式必须覆盖**——至少 桌面 / 平板 / 手机 三个断点
- **README.md 必须包含三段**：启动方式 / 验收点映射 / 版本痕迹

### README.md 模板

```markdown
# <需求名> 原型

## 启动方式
- 直接打开：`open prototype/index.html`
- （如需服务）本地起 server：`python3 -m http.server 8080` → <http://localhost:8080>

## Aesthetic 方向
- 选定：<editorial / brutalist / refined minimal / ... >
- 理由：<一句话——通常是和产品线视觉语言的关系>

## 验收点映射（来自 review.md）
| 验收标准 | 原型覆盖 | 演示路径 |
|---|---|---|
| 列表页可按时间排序 | ✅ | 首页 → 点击排序按钮 |
| 详情页显示相关推荐 | ✅ | 列表 → 点击任一项 → 滚到底部 |
| 统计数据自动刷新 | ❌ 后端逻辑 | 原型不覆盖 |

## 版本痕迹
- v1（2026-04-XX）：初版产出
- v2（2026-04-YY）：按评审反馈调整配色 + 首屏留白
```

## Aesthetic 方向选型

### 先判断：是延续还是新立？

| 场景 | 做法 |
|---|---|
| 需求落在已有产品线（Studio / 官网 / 后台） | **延续既有视觉语言**——读 `tripo-repos` 查该产品线已有原型 / 线上页面，提取字体 / 配色 / spacing 系统，在原型里做一致性延伸 |
| 需求是独立页 / 新产品线 | **自主选方向**——按需求调性（面向谁、解决什么问题、情绪是什么）选一个明确方向 |
| 不确定 | AskUserQuestion 问调用方："这个页面要和 Studio 风格对齐，还是走独立视觉？" |

### 选方向的候选集

参考 `@anthropic/frontend-design` 的方向清单，Tripo 场景里常见适配：

| 方向 | 适配场景 |
|---|---|
| Editorial / 杂志派 | 内容型页面（blog 详情、长文、专栏） |
| Refined minimal | 后台管理、工具型界面 |
| Bold brutalist | 营销活动页、品牌宣言页 |
| Playful / toy-like | 面向 C 端年轻用户的轻量交互 |
| Industrial / utilitarian | 数据密度大的仪表盘、运营后台 |

**选定后执行到底**——不在同一原型里跨风格。评审觉得不对，就在下一版统一换风格，不做局部风格叠加。

### 避开 AI slop 的 Tripo 红线

引用 `@anthropic/frontend-design` 的通用红线，补充 Tripo 场景强化：

- ❌ Inter / Roboto / Arial / system-ui 作主字体
- ❌ 紫色渐变 + 白底的"AI 官网套餐"
- ❌ 居中单栏 + 顶部 Nav + 底部 Footer 的默认三段式
- ❌ Space Grotesk（已经烂大街，避开）
- ❌ 只写静态页没交互——Tripo 的原型必须能动（hover / click / scroll reveal）

## 与 Tripo 流程的对接

### 前置依赖

| 前置产物 | 来源 agent | 作用 |
|---|---|---|
| `review.md` | planner | 告诉我做给谁、验收标准 |
| `technical-solution.md` | architect | 告诉我技术约束、数据形态、跨仓库边界 |

**两份产物任一缺失 → 停下来打回**，不自己脑补需求 / 方案。

### 后置交接

| 下游 | 交付物 | 交接要求 |
|---|---|---|
| scrum-master | `prototype/index.html` 的任务目录链接 | R2 通知消息模板附此链接 + `technical-solution.md` 链接 |
| developer | `prototype/` 整个目录 | A 分支前置产物清单包含"视觉原型"——缺则 developer 拒绝开工 |
| tester | `prototype/README.md` 验收点映射 | 集成测试计划参照映射表定验收路径 |

## 完成判定 checklist

原型交付前必过：

- [ ] `prototype/index.html` 可 `open` / 本地 server 打开
- [ ] 主要路径（进入 → 主操作 → 看到结果）能跑通
- [ ] 响应式断点（桌面 / 平板 / 手机）各切一次无破版
- [ ] hover / click / focus 状态有可见反馈
- [ ] 字体 / 配色 / 动效避开 AI slop 红线
- [ ] `prototype/README.md` 三段（启动方式 / 验收点映射 / 版本痕迹）齐全
- [ ] `review.md` 验收标准逐条映射，未覆盖的显式标注原因
- [ ] 所有数据 mock，没接 live API / CMS
- [ ] 产物全部在 `tasks/<task-dir>/prototype/`，未污染仓库代码

## 输出格式

designer 向调用方汇报时输出 4 段（详见 designer.md「我的输出习惯」）：

1. 原型摘要（路径 / aesthetic 方向 / 覆盖清单）
2. 验收点映射（review.md 逐条 → 原型演示路径）
3. 浏览器验证证据（启动方式 + 截图 + 路径记录）
4. 下一步建议（交 scrum-master R2 / 交 developer / 待调整点）

## 相关 skill

- `tripo-requirement` —— 流程编排层，step 5 技术评审阶段会派 designer
- `tripo-architecture` —— architect 方法论，我的上游
- `tripo-dev` —— developer 方法论，我的下游
- `tripo-notify` —— R2 节点通知模板（附原型 + 方案链接）
- `tripo-tables` / `tripo-task-dirs` —— scrum-master 使用，管表格和任务目录
- `tripo-repos` —— 查产品线路径 / 技术栈，用于延续既有视觉语言
- `@anthropic/frontend-design` —— 美学层（字体 / 颜色 / 动效 / 布局创意）
