# CMS API 踩坑记录

> 只记录 Claude 不读代码容易搞错的非直觉行为。随使用积累更新。

## Payload REST API

- **认证头前缀是 `users`**：`Authorization: users API-Key <key>`，不是 `Bearer`，不是 `API-Key`
- **草稿创建**：`POST /api/{collection}?draft=true` + body 中 `"_status": "draft"`，两者都要
- **发布/取消发布**：改 `_status` 字段（不是 `status`），值为 `"published"` 或 `"draft"`
- **文件上传额外字段**：用 `_payload` JSON 字符串（不是 `data`），`-F '_payload={"alt":"..."}'`
- **`locale=all`**：返回 locale 对象结构（如 `{"en": "title", "zh": "标题"}`），不是扁平字段
- **查询包含草稿**：需认证 + `?draft=true` 参数，否则只返回已发布文档

## Tripo CMS 特有

- **GeoPosts slug 允许 `/`**（如 `explore/topic`），Posts slug 不允许
- **`backfill-logs` 只读**：create/update/delete API 全部返回 `false`，只能通过 execute 端点间接创建
- **Categories 无需认证**：read 权限是 `anyone`，直接 GET 即可
- **`blog-import` 单次上限 50 篇**：超过需分批调用
- **`migrate-post` 不删源文档**：只是 unpublish 为草稿，需要手动删除
- **Media 无本地存储**：`disableLocalStorage: true`，全部上传到阿里云 OSS
- **Media 自动转 WebP**：上传 jpg/png 会被转为 webp，文件名和 URL 会变
