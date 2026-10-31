#!/bin/sh
# Run workbench + robot on the car. Hardware stays disabled unless you override.
set -eu
cd "$HOME/patrol-prototype"
mkdir -p runtime
python3 - <<'P'
import json
from pathlib import Path
p=Path('config.json')
c=json.loads(p.read_text(encoding='utf-8'))
c['robot_url']='http://127.0.0.1:8766'
c['server_url']='http://127.0.0.1:8765'
c['robot_bind_host']='0.0.0.0'
c['server_bind_host']='0.0.0.0'
c['hardware_enabled']=False
c.setdefault('max_duty',0.03)
p.write_text(json.dumps(c,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('config colocated: server:8765 robot:8766 bind 0.0.0.0 hardware_enabled=false')
P
# stop old instances
pkill -f 'python3 -m patrol.robot' 2>/dev/null || true
pkill -f 'python3 -m patrol.server' 2>/dev/null || true
sleep 2
if pgrep -f 'python3 -m patrol\.(robot|server)' >/dev/null; then
  echo 'ABORT: old patrol still running'; pgrep -af 'python3 -m patrol'; exit 1
fi
export PATROL_CONFIG_JSON='{"hardware_enabled":false,"serial_monitor_only":true}'
nohup python3 -m patrol.robot > runtime/robot.log 2>&1 < /dev/null &
sleep 2
nohup python3 -m patrol.server > runtime/server.log 2>&1 < /dev/null &
sleep 2
pgrep -af 'python3 -m patrol' || { echo FAIL; exit 1; }
echo "Workbench: http://$(hostname -I | awk '{print $1}'):8765  account in .local-access/登录信息.txt"
