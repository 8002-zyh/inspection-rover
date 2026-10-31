#!/usr/bin/env bash
# Read-only inspection: does not start ROS, publish commands, install or change permissions.
# Creates one timestamped report in the current directory.
set -u
report="vehicle-info-$(date +%Y%m%d-%H%M%S).txt"
exec > >(tee "$report") 2>&1
section() { printf '\n===== %s =====\n' "$1"; }
section 'OS / board / time'
date -Is
uname -a
cat /etc/os-release
if [ -r /proc/device-tree/model ]; then tr -d '\0' < /proc/device-tree/model; printf '\n'; fi
if [ -r /etc/nv_tegra_release ]; then cat /etc/nv_tegra_release; fi
free -h
df -h "$HOME"
section 'ROS installed / current shell'
ls -ld /opt/ros/* 2>/dev/null
env | grep -E '^(ROS|CMAKE_PREFIX_PATH|PYTHONPATH)=' || true
env | grep -E '^ROS_' || true
command -v python python2 python3 rosversion rostopic rosnode || true
if command -v rosversion >/dev/null; then rosversion -d; fi
section 'Network / SSH'
ip -br address
ip route
systemctl is-active ssh 2>/dev/null || true
section 'USB / serial / permissions'
lsusb
lsusb -t
ls -l /dev/serial/by-id/ /dev/ttyACM* /dev/ttyUSB* 2>/dev/null
id
section 'Installed vendor packages'
dpkg-query -W 'nvidia-l4t-core' 'nvidia-jetpack' 'librealsense*' 'ros-*-realsense*' 2>/dev/null
section 'Workspace candidates'
find "$HOME" -maxdepth 5 -type d -name 4pro -print 2>/dev/null
for root in "$HOME/Desktop/4pro" "$HOME/桌面/4pro"; do
  [ -d "$root" ] || continue
  section "$root source files"
  find "$root" -type f \( -name package.xml -o -name '*.launch' -o -name '*Keyboard*' -o -name '*chasis*' -o -name '*Cruise*' -o -name '*PID*' -o -name '*.csv' \) -not -path '*/build/*' -not -path '*/devel/*' -print
done
section 'Existing ROS processes (no start)'
ps -eo pid,comm | grep -E 'ros|rviz|python' || true
if command -v rosnode >/dev/null; then
  timeout 8s rosnode list
  timeout 8s rostopic list -v
fi
section 'Done'
printf 'Report: %s/%s\n' "$PWD" "$report"
printf 'No motion commands were sent. Review IP addresses/usernames before public sharing.\n'
