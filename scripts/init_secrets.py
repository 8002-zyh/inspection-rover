"""Generate local credentials once; never overwrite an existing deployment."""
import json
import secrets
from pathlib import Path
from werkzeug.security import generate_password_hash

root = Path(__file__).resolve().parents[1] / '.local-access'
root.mkdir(exist_ok=True)
path = root / 'patrol-secrets.json'
if path.exists():
    raise SystemExit('Credentials already exist; nothing changed.')
password = secrets.token_urlsafe(18)
payload = dict(device_token=secrets.token_urlsafe(32), session_key=secrets.token_urlsafe(32),
               password_hash=generate_password_hash(password))
with path.open('x', encoding='utf-8') as f:
    json.dump(payload, f, indent=2)
path.chmod(0o600)
(root / '登录信息.txt').write_text('账号：operator\n密码：'+password+'\n', encoding='utf-8')
print('Created credentials in .local-access. Never commit them.')
