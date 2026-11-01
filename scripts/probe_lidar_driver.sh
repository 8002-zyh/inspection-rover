#!/bin/bash
# A 20-second sensor-only probe; no motor/servo publishers are launched.
source /opt/ros/noetic/setup.bash
source "$HOME/Desktop/4pro/Sensor_perception/devel/setup.bash"
if pgrep -f '/livox_ros_driver2_node|fastlio_mapping|/rosmaster' >/dev/null; then
  echo 'ABORT: existing ROS localization/sensor process; do not start a duplicate probe'
  exit 2
fi
export ROS_MASTER_URI=http://127.0.0.1:11311
export ROS_IP=127.0.0.1
export ROS_LOG_DIR="$HOME/patrol-prototype/runtime/evidence/lidar-probe-$(date +%Y%m%d-%H%M%S)-$$"
mkdir -p "$ROS_LOG_DIR"
cleanup() {
  # roslaunch children use their own process groups. Limit cleanup to this probe's
  # unique log marker; never kill unrelated robot, ROS or localization processes.
  pkill -INT -f "__log:=$ROS_LOG_DIR/" 2>/dev/null || true
  sleep 1
  pkill -KILL -f "__log:=$ROS_LOG_DIR/" 2>/dev/null || true
}
trap cleanup EXIT
timeout --signal=INT --kill-after=5s 20s roslaunch livox_ros_driver2 msg_MID360.launch \
  > "$ROS_LOG_DIR/probe.log" 2>&1
result=$?
echo "Probe log: $ROS_LOG_DIR/probe.log"
tail -n 35 "$ROS_LOG_DIR/probe.log"
exit "$result"
