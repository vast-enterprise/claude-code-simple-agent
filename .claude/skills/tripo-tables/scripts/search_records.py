#!/usr/bin/env python3
"""
在飞书多维表格中按关键词搜索记录。

用法:
    python search_records.py <table_name_or_id> <keyword> [--field 字段名]

示例:
    python search_records.py 发车中需求 blog
    python search_records.py tblPlaxVsLBvKMRl blog-import
    python search_records.py 执行中需求 郭凯南 --field 研发Owner
    python search_records.py 产品需求池 blog --field 需求描述

支持的表名简写:
    产品需求池 / 执行中需求 / 发车中需求 / Sprint版本计划 / Hotfix管理 / 需求Bug管理 / 技术需求管理
"""

import json
import subprocess
import sys

# 表名 → (base_token, table_id) 映射
TABLE_MAP = {
    "产品需求池":     ("HMvbbjDHOaHyc6sZny6cMRT8n8b", "tblb9E9PQHP79JHE"),
    "执行中需求":     ("HMvbbjDHOaHyc6sZny6cMRT8n8b", "tblxLMQ8Ih5Gs5oM"),
    "发车中需求":     ("HMvbbjDHOaHyc6sZny6cMRT8n8b", "tblPlaxVsLBvKMRl"),
    "Sprint版本计划": ("HMvbbjDHOaHyc6sZny6cMRT8n8b", "tblm2FGJjiK4frzt"),
    "Hotfix管理":     ("HMvbbjDHOaHyc6sZny6cMRT8n8b", "tblzLyiFJtsYZRsN"),
    "需求Bug管理":    ("HMvbbjDHOaHyc6sZny6cMRT8n8b", "tblkGH8uvmXS80CB"),
    "技术需求管理":   ("OCNcbuwpta7qc7sxAPOcSpngnbg", "tblkb1Saexm0njaE"),
}


def resolve_table(name_or_id: str) -> tuple:
    """表名或 table_id → (base_token, table_id)"""
    if name_or_id in TABLE_MAP:
        return TABLE_MAP[name_or_id]
    # 尝试 table_id 直接匹配
    for _, (bt, tid) in TABLE_MAP.items():
        if tid == name_or_id:
            return bt, tid
    print(f"未知表: {name_or_id}", file=sys.stderr)
    print(f"支持: {', '.join(TABLE_MAP.keys())}", file=sys.stderr)
    sys.exit(1)


def fetch_all(base_token: str, table_id: str) -> list:
    """分页获取全量记录，返回 [{"record_id": str, "fields": {..}}, ...]。

    record-list 返回结构细节（data.data 二维数组、has_more 翻页、WARN 干扰 stdout 等）
    参见 lark-base skill。
    """
    all_records = []
    offset = 0

    while True:
        cmd = [
            "lark-cli", "base", "+record-list",
            "--base-token", base_token,
            "--table-id", table_id,
            "--limit", "200",
            "--offset", str(offset),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"lark-cli 错误: {result.stderr.strip()}", file=sys.stderr)
            break

        try:
            resp = json.loads(result.stdout)
        except json.JSONDecodeError:
            print(f"JSON 解析失败: {result.stdout[:200]}", file=sys.stderr)
            break

        data = resp.get("data", {})
        rows = data.get("data", [])
        fields = data.get("fields", [])
        record_ids = data.get("record_id_list", [])
        has_more = data.get("has_more", False)

        if not rows:
            break

        for i, row in enumerate(rows):
            rid = record_ids[i] if i < len(record_ids) else None
            record = dict(zip(fields, row))
            all_records.append({"record_id": rid, "fields": record})

        if not has_more:
            break
        offset += len(rows)

    return all_records


def match_keyword(value, keyword: str) -> bool:
    """递归检查值中是否包含关键词（不区分大小写）"""
    kw = keyword.lower()
    if value is None:
        return False
    if isinstance(value, str):
        return kw in value.lower()
    if isinstance(value, list):
        return any(match_keyword(item, keyword) for item in value)
    if isinstance(value, dict):
        return any(match_keyword(v, keyword) for v in value.values())
    return kw in str(value).lower()


def format_value(value) -> str:
    """将字段值格式化为可读字符串"""
    if value is None:
        return "—"
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict) and "name" in item:
                parts.append(item["name"])
            elif isinstance(item, dict) and "id" in item:
                parts.append(item["id"])
            elif isinstance(item, str):
                parts.append(item)
            else:
                parts.append(str(item))
        return ", ".join(parts)
    return str(value)


def main():
    # 解析参数
    args = sys.argv[1:]
    if len(args) < 2:
        print(__doc__)
        sys.exit(1)

    table_name = args[0]
    keyword = args[1]
    field_filter = None

    if "--field" in args:
        idx = args.index("--field")
        if idx + 1 < len(args):
            field_filter = args[idx + 1]

    base_token, table_id = resolve_table(table_name)

    print(f"搜索: {table_name} ({table_id}) | 关键词: {keyword}" +
          (f" | 字段: {field_filter}" if field_filter else ""))
    print("=" * 60)

    records = fetch_all(base_token, table_id)
    print(f"总记录数: {len(records)}")

    matches = []
    for rec in records:
        fields = rec["fields"]
        if field_filter:
            # 只搜指定字段
            if field_filter in fields and match_keyword(fields[field_filter], keyword):
                matches.append(rec)
        else:
            # 搜所有字段
            if any(match_keyword(v, keyword) for v in fields.values()):
                matches.append(rec)

    print(f"匹配: {len(matches)} 条\n")

    for rec in matches:
        print(f"record_id: {rec['record_id']}")
        for k, v in rec["fields"].items():
            fv = format_value(v)
            if fv != "—":
                print(f"  {k}: {fv}")
        print()


if __name__ == "__main__":
    main()
