#!/usr/bin/env python3
"""
Tripo 用户需求查询脚本

用法:
    python query_user_requirements.py <user_name_or_id>

示例:
    python query_user_requirements.py 郭凯南
    python query_user_requirements.py ou_8adc8aca7ad728142eb6669e5b13fb52
"""

import json
import subprocess
import sys
from typing import Optional

# 三表配置
TABLES = [
    {"name": "产品需求池", "base_token": "HMvbbjDHOaHyc6sZny6cMRT8n8b", "table_id": "tblb9E9PQHP79JHE", "view_id": "vewMnpNgGD"},
    {"name": "执行中需求", "base_token": "HMvbbjDHOaHyc6sZny6cMRT8n8b", "table_id": "tblxLMQ8Ih5Gs5oM", "view_id": None},
    {"name": "技术需求一览表", "base_token": "OCNcbuwpta7qc7sxAPOcSpngnbg", "table_id": "tblkb1Saexm0njaE", "view_id": None},
]

# 用户相关字段
USER_FIELD_NAMES = ['创建人', '研发Owner', '需求Owner', 'Member', '开发人员']
DESC_FIELD_NAMES = ['需求描述', '一句话描述需求']
STATUS_FIELD_NAMES = ['需求状态', '状态']


def run_lark_cli(base_token: str, table_id: str, offset: int = 0, limit: int = 200, view_id: str = None) -> dict:
    """执行 lark-cli 命令获取数据"""
    cmd = [
        'lark-cli', 'base', '+record-list',
        '--base-token', base_token,
        '--table-id', table_id,
        '--limit', str(limit),
        '--offset', str(offset)
    ]
    if view_id:
        cmd.extend(['--view-id', view_id])
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"lark-cli 错误: {result.stderr.strip()}", file=sys.stderr)
        return {"data": {"data": [], "fields": []}}
    return json.loads(result.stdout)


def get_all_records(base_token: str, table_id: str, view_id: str = None) -> list:
    """分页获取全量数据，返回 [(record, fields, record_id), ...]"""
    all_data = []
    offset = 0

    while True:
        result = run_lark_cli(base_token, table_id, offset, view_id=view_id)
        records = result.get('data', {}).get('data', [])
        fields = result.get('data', {}).get('fields', [])
        record_ids = result.get('data', {}).get('record_id_list', [])

        if not records:
            break

        for i, record in enumerate(records):
            rid = record_ids[i] if i < len(record_ids) else None
            all_data.append((record, fields, rid))

        if not result.get('data', {}).get('has_more', False):
            break
        offset += 200

    return all_data


def find_field_indices(fields: list) -> dict:
    """根据 fields 数组找到关键字段的索引"""
    indices = {}

    # 用户字段
    indices['user'] = {f: fields.index(f) for f in USER_FIELD_NAMES if f in fields}

    # 描述字段
    for f in DESC_FIELD_NAMES:
        if f in fields:
            indices['desc'] = fields.index(f)
            break

    # 状态字段
    for f in STATUS_FIELD_NAMES:
        if f in fields:
            indices['status'] = fields.index(f)
            break

    # 优先级
    if '绝对优先级' in fields:
        indices['priority'] = fields.index('绝对优先级')

    # 需求池
    if '需求池' in fields:
        indices['pool'] = fields.index('需求池')

    return indices


def extract_value(record: list, idx: Optional[int]) -> str:
    """安全提取字段值"""
    if idx is None or idx >= len(record):
        return '未知'
    val = record[idx]
    if val is None:
        return '未知'
    if isinstance(val, list) and len(val) > 0:
        first = val[0]
        if isinstance(first, dict):
            # 用户类型字段 [{'id': 'ou_xxx', 'name': '张三'}]
            return first.get('name', '未知')
        elif isinstance(first, str):
            # 多选字段 ['L1', 'L2']
            return first
        return '未知'
    if isinstance(val, str):
        return val
    return '未知'


def extract_status(record: list, idx: Optional[int]) -> str:
    """专门提取状态字段，过滤掉非状态值"""
    valid_statuses = [
        '开发/交付中', '进行中', '评审中', '未启动', '验收/提测中',
        '已完成', '完成', '暂停', '风险', '研发中', '测试中'
    ]
    val = extract_value(record, idx)
    if val in valid_statuses:
        return val
    # 尝试从列表中找有效状态
    if idx is not None and idx < len(record) and isinstance(record[idx], list):
        for item in record[idx]:
            if isinstance(item, str) and item in valid_statuses:
                return item
    return '未知'


def query_user(user_id: str) -> list:
    """查询用户相关的所有需求"""
    results = []

    for table in TABLES:
        all_data = get_all_records(
            table['base_token'],
            table['table_id'],
            view_id=table.get('view_id'),
        )

        for record, fields, record_id in all_data:
            indices = find_field_indices(fields)
            roles = []

            # 检查用户字段
            for field_name, idx in indices.get('user', {}).items():
                if idx < len(record) and isinstance(record[idx], list):
                    for item in record[idx]:
                        if isinstance(item, dict) and item.get('id') == user_id:
                            roles.append(field_name)
                            break

            if roles:
                results.append({
                    'table': table['name'],
                    'base_token': table['base_token'],
                    'table_id': table['table_id'],
                    'view_id': table.get('view_id'),
                    'record_id': record_id,
                    'desc': extract_value(record, indices.get('desc')),
                    'status': extract_status(record, indices.get('status')),
                    'priority': extract_value(record, indices.get('priority')),
                    'pool': extract_value(record, indices.get('pool')),
                    'roles': roles
                })

    return results


def print_results(results: list):
    """格式化输出结果"""
    # 按状态分组，定义顺序和图标
    status_order = [
        ('开发/交付中', '🔴'),
        ('进行中', '🔴'),
        ('评审中', '🟠'),
        ('未启动', '🟡'),
        ('验收/提测中', '🟠'),
        ('已完成', '✅'),
        ('完成', '✅'),
        ('暂停', '⏸️'),
        ('风险', '⚠️'),
    ]
    def print_item(item):
        desc_short = item['desc'][:50] if len(str(item['desc'])) > 50 else item['desc']
        print(f"  [{item['priority']}] {desc_short}")
        rid = item.get('record_id') or '未知'
        vid = item.get('view_id') or '-'
        print(f"    来源: {item['table']} | 角色: {', '.join(item['roles'])}")
        print(f"    record_id: {rid} | view_id: {vid} | base: {item.get('base_token', '')} | table: {item.get('table_id', '')}")

    # 先输出已定义顺序的状态
    for status, icon in status_order:
        items = [r for r in results if r['status'] == status]
        if items:
            print(f"\n{icon} {status} ({len(items)}个)")
            print("-" * 40)
            for item in items:
                print_item(item)

    # 其他状态
    other_statuses = set(r['status'] for r in results) - set(s[0] for s in status_order)
    for status in sorted(other_statuses):
        items = [r for r in results if r['status'] == status]
        if items:
            print(f"\n⚪ {status} ({len(items)}个)")
            print("-" * 40)
            for item in items:
                print_item(item)

    print(f"\n总计: {len(results)} 条")


def get_current_user() -> tuple:
    """获取当前登录用户的 open_id 和名称"""
    cmd = ['lark-cli', 'contact', '+get-me']
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return None, None
    try:
        data = json.loads(result.stdout)
        user = data.get('data', {})
        return user.get('open_id'), user.get('name', '我')
    except json.JSONDecodeError:
        return None, None


def search_user(user_name: str) -> Optional[str]:
    """通过用户名查找 open_id"""
    cmd = ['lark-cli', 'contact', '+search-user', '--query', user_name]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    try:
        data = json.loads(result.stdout)
        users = data.get('data', {}).get('users', [])
        if users:
            return users[0].get('open_id')
    except json.JSONDecodeError:
        pass
    return None


SELF_KEYWORDS = {'我', 'me', 'self', '我的', '自己'}


def main():
    if len(sys.argv) < 2:
        print("用法: python query_user_requirements.py <user_name_or_id|我>")
        sys.exit(1)

    user_input = sys.argv[1]

    if user_input.lower() in SELF_KEYWORDS:
        user_id, user_name = get_current_user()
        if not user_id:
            print("无法获取当前登录用户，请先执行 lark-cli auth login", file=sys.stderr)
            sys.exit(1)
    elif user_input.startswith('ou_'):
        user_id = user_input
        user_name = "用户"
    else:
        user_id = search_user(user_input)
        if not user_id:
            print(f"未找到用户: {user_input}", file=sys.stderr)
            sys.exit(1)
        user_name = user_input

    print(f"查询用户需求: {user_name} ({user_id})")
    print("=" * 60)

    results = query_user(user_id)
    print_results(results)


if __name__ == '__main__':
    main()