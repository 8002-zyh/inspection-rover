import json
import os
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()


def configuration():
    root = Path(__file__).resolve().parent.parent
    cfg = json.loads((root / 'config.json').read_text(encoding='utf-8'))
    cfg.update(json.loads(os.environ.get('PATROL_CONFIG_JSON', '{}')))
    return cfg


def credentials():
    path = Path(os.environ.get('PATROL_SECRETS', '.local-access/patrol-secrets.json'))
    return json.loads(path.read_text(encoding='utf-8'))
