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
