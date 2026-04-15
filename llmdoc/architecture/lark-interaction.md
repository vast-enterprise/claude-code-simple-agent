# 飞书交互层架构

## 1. Identity

- **What it is:** 基于 `lark-cli` 子进程封装的飞书 API 交互层，提供消息回复、表情反馈、事件订阅、富消息解析、图片下载五大能力。
- **Purpose:** 将所有飞书通信统一收敛到 `subprocess.run` + `lark-cli` 的调用模式，避免直接 HTTP 调用，简化认证和错误处理。

## 2. Core Components

- `src/lark.py` (`add_reaction`, `remove_reaction`, `reply_message`, `_reply_plain_text`, `_convert_md_tables`, `_md_table_to_text`, `_MD_TABLE_PATTERN`, `resolve_user_name`, `resolve_chat_name`, `resolve_rich_content`, `download_message_image`, `_get_message_image_key`, `_resolve_inline_images`, `_fetch_merge_forward_content`, `_extract_post_text`, `_extract_message_text`): 飞书 API 交互 + 富消息解析 + 图片下载的唯一出口。API 交互全部为同步阻塞调用。消息回复使用 markdown 富文本格式（`lark-cli im +messages-reply --markdown`），发送前自动将 markdown 表格转为代码块包裹的纯文本对齐格式（飞书 md tag 不支持表格语法），失败时自动降级为纯文本（`_reply_plain_text`）。富消息解析模块将 merge_forward/image/file/audio/video/sticker/media 等非纯文本消息转换为可读文本，图片类消息会自动下载到本地并返回文件路径引用。
- `src/main.py` (`start_event_listener`): 启动 `lark-cli event +subscribe` 长驻子进程，以 NDJSON 格式输出事件流。
- `src/handler.py` (`send_message`, `session_reader`, `_ensure_display_names`): 消费端，在消息处理流程中调用 `lark.py` 的函数完成富消息解析、表情反馈、消息回复和名字解析。`send_message` 在构建 prompt 之前调用 `resolve_rich_content()` 预处理非纯文本消息。

## 3. Execution Flow (LLM Retrieval Map)

### 3.1 lark-cli 调用模式

所有飞书 API 调用均通过 `subprocess.run` 同步执行 `lark-cli` 命令，铁律：**必须带 `--as bot`**。

三种调用姿势：

- **封装子命令**: `lark-cli im reactions create --params {...} --data {...} --as bot` — 用于表情操作。见 `src/lark.py:16-26`、`src/lark.py:36-47`。
- **高级子命令**: `lark-cli im +messages-reply --message-id {id} --markdown {text} --as bot` — 用于 markdown 消息回复。见 `src/lark.py:386-394`。
- **原始 API 调用**: `lark-cli api POST /open-apis/im/v1/messages/{id}/reply --data {...} --as bot --format data` — 用于纯文本降级回复。见 `src/lark.py:404-411`。

错误处理策略：失败时通过 `log_error()` 记录日志，不抛异常（静默降级）。

### 3.2 消息回复机制

- **入口**: `src/lark.py:378-398` (`reply_message`)
- **命令**: `lark-cli im +messages-reply --message-id {id} --markdown {text} --as bot`
- **消息格式**: Markdown 富文本。Claude 输出的粗体、代码块、列表、链接等在飞书中渲染为富文本。
- **截断策略**: 文本超 15000 字符时，截断至 14950 字符并追加 `"\n\n...(回复过长，已截断)"`。见 `src/lark.py:380-381`。15000 是安全网，实际场景因分段发送每条消息很少超长。
- **Markdown 表格预处理**: 飞书 post 消息的 md tag 不支持 markdown 表格语法（`| a | b |` 格式会被丢弃）。`reply_message()` 在发送前调用 `_convert_md_tables(text)` 将所有 markdown 表格转为代码块包裹的纯文本对齐格式。见 `src/lark.py:384`。
  - **正则匹配**: `_MD_TABLE_PATTERN`（`src/lark.py:324-330`）匹配完整的 markdown 表格结构（表头行 + 分隔行 + 数据行）。
  - **转换逻辑**: `_md_table_to_text()`（`src/lark.py:333-370`）去掉外侧 `|`，按列对齐（中文字符算 2 宽度），用 ``` 代码块包裹确保飞书原样展示。
  - **入口函数**: `_convert_md_tables()`（`src/lark.py:373-375`）用正则替换文本中所有匹配的表格。
- **降级机制**: Markdown 回复失败时自动调用 `_reply_plain_text()` 降级为纯文本回复（`POST /open-apis/im/v1/messages/{id}/reply`，`msg_type: "text"`）。见 `src/lark.py:395-398`、`src/lark.py:401-413`。

### 3.3 表情反馈机制

表情用作"正在处理"的视觉状态指示器，生命周期与单次消息处理绑定：

1. **添加时机**: `handle_message` 异步迭代 SDK 响应流，首条 `AssistantMessage` 到达时调用 `add_reaction(message_id)`，默认 emoji 为 `"OnIt"`。见 `src/handler.py:72-73`。
2. **返回值**: `add_reaction` 返回 `reaction_id: str | None`，供后续删除使用。见 `src/lark.py:9-26`。
3. **移除时机**: 响应流消费完毕（收到 `ResultMessage`）后，立即调用 `remove_reaction(message_id, reaction_id)` 清理。见 `src/handler.py:84-85`。
4. **容错**: `reaction_id` 为 `None` 时跳过移除；移除失败仅打印日志。

### 3.4 事件订阅配置

- **入口**: `src/main.py:22-31` (`start_event_listener`)
- **命令**: `lark-cli event +subscribe --event-types im.message.receive_v1 --compact --quiet --as bot`
- **关键 flag**:
  - `--event-types im.message.receive_v1`: 仅订阅消息接收事件
  - `--compact`: 精简输出格式（NDJSON，每行一个事件）
  - `--quiet`: 抑制 lark-cli 自身日志输出
  - `--as bot`: 以 bot 身份建立 WebSocket 长连接
- **进程隔离**: `start_new_session=True`，独立进程组，便于信号清理时 `os.killpg` 整组终止。
- **stdout**: `asyncio.subprocess.PIPE`，主循环逐行读取。
- **stderr**: `asyncio.subprocess.DEVNULL`，丢弃。

### 3.5 富消息解析

将非纯文本飞书消息（merge_forward、image、file、audio、video、sticker、media）转换为 Claude 可理解的文本描述。图片类消息会自动下载到本地，返回文件路径引用供 Claude 直接读取。

- **入口:** `src/lark.py:275-321` (`resolve_rich_content`) — 检测 `event.message_type`，纯文本/post/interactive 返回 `None`（不需要额外解析），其他类型返回可读文本。末尾有兜底检查：任何消息内容中匹配到 `[Image: img_xxx]` 模式时调用 `_resolve_inline_images` 下载替换（覆盖 compact 格式 post 消息等场景）。见 `src/lark.py:313-318`。
- **调用时机:** `src/handler.py:92-95` — `send_message` 在构建 prompt 之前调用，若返回非 None 则替换原始 content。
- **合并转发 (merge_forward):** `src/lark.py:281-289` — 通过 `message_type == "merge_forward"` 或内容标记（`_MERGE_FORWARD_MARKERS`）检测。调用 `_fetch_merge_forward_content()` 获取展开内容。
- **合并转发展开:** `src/lark.py:237-272` (`_fetch_merge_forward_content`) — 执行 `lark-cli im +messages-mget --message-ids {id} --as bot --format json`，lark-cli 内置 merge_forward 展开，返回可读文本。展开后调用 `_resolve_inline_images()` 下载文本中的内联图片。
- **单张图片消息:** `src/lark.py:292-301` — 调用 `_get_message_image_key()` 获取 image_key，再调用 `download_message_image()` 下载，返回 `[图片消息，已下载到: /full/path.png]`。
- **Post 富文本提取:** `src/lark.py:144-180` (`_extract_post_text`) — 解析飞书 post 结构（多语言包 → paragraphs → elements），支持 text/a/at/emotion/code_block/img/media 标签。
- **单条消息文本提取:** `src/lark.py:183-211` (`_extract_message_text`) — 按 `msg_type` 分发：text 取 `.text`，post 调用 `_extract_post_text`，image/file/audio/video/sticker/interactive 返回描述性标签。
- **简单媒体类型:** `src/lark.py:302-311` — file/audio/video/sticker/media 直接返回 `[类型消息]` 占位符。

### 3.6 图片下载与解析

将飞书图片消息下载到本地 `data/images/` 目录，使 Claude 能够通过 Read 工具直接查看图片内容。

- **通用下载函数:** `src/lark.py:88-117` (`download_message_image(message_id, image_key)`) — 使用 `lark-cli im +messages-resources-download` 下载图片。文件名基于 image_key 安全字符替换 + `.png`。已下载的文件不重复请求（缓存机制）。返回相对路径 `data/images/xxx.png`。
- **API 获取 image_key:** `src/lark.py:120-141` (`_get_message_image_key(message_id)`) — 调用 `GET /open-apis/im/v1/messages/{message_id}` 获取 image 消息的 image_key。用于单张图片消息场景（event 中不直接携带 image_key）。
- **内联图片解析:** `src/lark.py:214-234` (`_resolve_inline_images(message_id, text)`) — 用正则 `\[Image: (img_[^\]]+)\]` 匹配 lark-cli mget 输出中的图片占位符，逐个下载并替换为 `[图片已下载: /full/path.png]`。用于合并转发消息场景。
- **存储路径:** 常量 `_IMAGES_DIR = ROOT / "data" / "images"`（`src/lark.py:13`）。
- **关键发现:** 合并转发中的图片必须用**父 merge_forward 消息 ID** 下载，子消息 ID 会报 "File not in msg" 错误。因此 `_resolve_inline_images` 接收的是父消息 ID。

### 3.7 名字解析

通过 lark-cli 将飞书 ID 解析为可读名字，用于 Dashboard 显示：

- **用户名解析:** `src/lark.py:43-55` — `resolve_user_name(open_id)` 调用 `lark-cli contact +get-user --user-id {open_id} --user-id-type open_id -q .data.user.name`，返回用户名或 None。
- **群名解析:** `src/lark.py:58-70` — `resolve_chat_name(chat_id)` 调用 `lark-cli im chats get --params {"chat_id": chat_id} -q .data.name`，返回群名或 None。
- **触发时机:** `src/handler.py:49-72` — `_ensure_display_names()` 检查 store 中是否已有 `sender_name`，没有则解析并存入。仅首次触发，后续复用 store 数据。

## 4. Design Rationale

- **为什么用 lark-cli 而非直接 HTTP**: 认证、token 刷新、WebSocket 长连接管理全部由 lark-cli 处理，应用层只需关注业务逻辑。
- **为什么同步调用**: lark-cli 调用耗时极短（毫秒级），同步 `subprocess.run` 足够且更简单。在多 session 并发架构下，每个 worker 的短暂阻塞影响有限。
- **为什么静默降级**: 表情和回复失败不应阻断主流程，避免因飞书 API 抖动导致整个消息处理链中断。回复机制有双层降级：markdown 失败 → 纯文本；纯文本失败 → 仅记录日志。
- **15000 字符截断**: 截断阈值从 4000 提升到 15000，因为分段发送后单条消息不太会超长，15000 是安全网。
- **为什么预处理 markdown 表格**: 飞书 post 消息的 md tag 会静默丢弃 markdown 表格语法，导致用户看不到表格内容。转为代码块包裹的对齐纯文本后，飞书原样展示，保留可读性。中文字符按 2 宽度计算确保对齐准确。
- **名字解析惰性执行**: 仅首次遇到 session 时调用 lark-cli 解析用户名和群名，结果持久化到 SessionStore，避免每条消息都触发 API 调用。
