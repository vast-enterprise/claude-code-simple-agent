# lark-cli 多维表格踩坑指南

## record-list 返回结构（最常踩的坑）

`record-list` 返回的 **不是** `data.items[]`。正确结构：

```
data.data[]            二维数组，每行一条记录，列顺序与 fields 对应
data.fields[]          字段名列表
data.record_id_list[]  record ID 列表，与 data 行一一对应
data.has_more          是否有下一页（用 --offset 翻页）
```

正确解析（一行转字典）：

```python
record = dict(zip(fields, row))  # {字段名: 值}
```

错误写法（会静默返回空列表）：

```python
items = data.get("items", [])  # ← 永远是 []，这个字段不存在
```

## record-get 返回结构（与 record-list 不同）

```
data.record.{字段名}   平铺，直接按字段名取值
```

## 中文字段名

- jq 不支持中文字段名裸写，会报 `unexpected token`
- 用 python 解析，或 jq 的 `.["中文字段名"]` 语法

## 分页

- `--limit N --offset M`，默认 limit=100
- `has_more=true` 时必须翻页，否则数据不全
- 推荐 limit=200，循环直到 `has_more=false`

## 常见错误

| 症状 | 原因 | 修复 |
|------|------|------|
| 记录数为 0 但表里有数据 | 用了 `data.items` 而非 `data.data` | 改用正确结构 |
| JSON 解析失败 | lark-cli WARN 信息混入 stdout | 用 `2>/dev/null` 或写文件再解析 |
| record ID 格式错误 | 飞书短链 ID ≠ record ID | record ID 必须 `rec` 开头 |
| 代理环境 WARN 干扰 | `proxy detected` 警告写入 stdout | 重定向 stderr 或写临时文件 |
