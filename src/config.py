"""配置加载与校验"""

import json
import sys
from pathlib import Path

# 项目根目录（tripo-work-center/）
ROOT = Path(__file__).resolve().parent.parent

_config_path = ROOT / "config.json"
if not _config_path.exists():
    print("错误：请先复制 config.example.json 为 config.json 并填写配置", file=sys.stderr)
    sys.exit(1)

CONFIG = json.loads(_config_path.read_text())
PERSONA = (ROOT / "persona.md").read_text()
OWNER_ID: str = CONFIG["owner_open_id"]
BOT_NAME: str = CONFIG.get("bot_name", "AI Bot")

# headless 模式运行约束，拼接到 system prompt，不污染 persona
HEADLESS_RULES = """
## 运行环境约束

你运行在 headless 模式（无交互式终端），通过飞书消息与用户沟通。

- 禁止调用 AskUserQuestion、ExitPlanMode、EnterPlanMode 等交互式工具，它们在当前环境不可用
- 需要用户确认的事情，直接在回复文本中说明，等待下一条消息
- 所有输出通过飞书消息返回，保持简洁
"""
