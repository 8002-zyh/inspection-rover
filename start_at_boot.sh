#!/bin/sh
# Per-user @reboot entry. Starts the workbench; never arms or replays a route.
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
mkdir -p runtime
attempt=0
while [ "$(date +%Y)" -lt 2024 ]; do
  attempt=$((attempt+1))
  if [ "$attempt" -gt 150 ]; then
    echo 'BOOT_ABORT: invalid system date after 5 minutes; check hotspot/NTP'
    exit 1
  fi
  sleep 2
done
if pgrep -f 'python3 -m patrol\.(robot|server)' >/dev/null; then
  echo 'BOOT_SKIP: existing workbench process; preserving current session'
  exit 0
fi
exec /bin/sh ./start_car_workbench.sh --hardware
