#!/bin/sh
# Run workbench + robot on the car; --hardware permits writes but never arms motion.
set -eu
case "${1:-}" in
  '') export PATROL_START_HARDWARE=0 ;;
  --hardware) export PATROL_START_HARDWARE=1 ;;
  *) echo 'Usage: sh start_car_workbench.sh [--hardware]'; exit 2 ;;
esac
[ "$#" -le 1 ] || { echo 'Too many arguments'; exit 2; }
cd "$HOME/patrol-prototype"
mkdir -p runtime
python3 - <<'P'
import json, os, time
from datetime import datetime, timezone
from pathlib import Path
# A battery change can leave this Jetson at 1970 until timesyncd acquires NTP.
# Refuse silently wrong evidence dates; never change the system clock ourselves.
deadline=time.monotonic()+30
while datetime.now(timezone.utc).year < 2024 and time.monotonic()<deadline:
    print('Waiting for system date synchronization...',flush=True)
    time.sleep(1)
if datetime.now(timezone.utc).year < 2024:
    raise SystemExit('ABORT: system date is invalid; restore hotspot time synchronization and retry')
p=Path('config.json')
c=json.loads(p.read_text(encoding='utf-8'))
c['robot_url']='http://127.0.0.1:8766'
c['server_url']='http://127.0.0.1:8765'
c['robot_bind_host']='0.0.0.0'
c['server_bind_host']='0.0.0.0'
c['hardware_enabled']=os.environ['PATROL_START_HARDWARE']=='1'
c.setdefault('max_duty',0.03)
p.write_text(json.dumps(c,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('config colocated: server:8765 robot:8766 bind 0.0.0.0',
      'hardware_enabled=',c['hardware_enabled'],'max_duty=',c['max_duty'],
      'stop_distance_m=',c.get('stop_distance_m'))
P
# stop old instances
pkill -f 'python3 -m patrol.robot' 2>/dev/null || true
pkill -f 'python3 -m patrol.server' 2>/dev/null || true
for attempt in $(seq 1 150); do
  pgrep -f 'python3 -m patrol\.(robot|server)' >/dev/null || break
  sleep 0.1
done
if pgrep -f 'python3 -m patrol\.(robot|server)' >/dev/null; then
  echo 'ABORT: old patrol still running'; pgrep -af 'python3 -m patrol'; exit 1
fi
if [ "$PATROL_START_HARDWARE" = 1 ]; then
  export PATROL_CONFIG_JSON='{"hardware_enabled":true,"serial_monitor_only":false}'
else
  export PATROL_CONFIG_JSON='{"hardware_enabled":false,"serial_monitor_only":true}'
fi
nohup python3 -m patrol.robot > runtime/robot.log 2>&1 < /dev/null &
sleep 2
nohup python3 -m patrol.server > runtime/server.log 2>&1 < /dev/null &
sleep 2
pgrep -af 'python3 -m patrol' || { echo FAIL; exit 1; }
echo "Workbench: http://$(hostname -I | awk '{print $1}'):8765  account in .local-access/登录信息.txt"
