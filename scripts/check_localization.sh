#!/bin/bash
# Static diagnostics only; no ROS launch, motion, IP changes, or package install.
source /opt/ros/noetic/setup.bash
source "$HOME/Desktop/4pro/Perceived_applications/devel/setup.bash"
source "$HOME/Desktop/4pro/Sensor_perception/devel/setup.bash"
set -u
# Both workspaces were built against /opt/ros independently; source alone loses the other overlay.
export ROS_PACKAGE_PATH="$HOME/Desktop/4pro/Perceived_applications/src:$ROS_PACKAGE_PATH"
echo '=== Package paths ==='
rospack find livox_ros_driver2
rospack find fast_lio
echo '=== Physical link ==='
ip -br link show eth0
carrier=$(cat /sys/class/net/eth0/carrier 2>/dev/null || echo unknown)
echo "carrier=$carrier"
echo '=== Host address ==='
ip -br -4 addr show eth0
echo '=== Built binaries: unresolved libraries ==='
ldd "$HOME/Desktop/4pro/Perceived_applications/devel/lib/fast_lio/fastlio_mapping" | grep 'not found' || true
ldd "$HOME/Desktop/4pro/Sensor_perception/devel/lib/livox_ros_driver2/livox_ros_driver2_node" | grep 'not found' || true
if [ "$carrier" != 1 ]; then
  echo 'GATE_FAILED: Ethernet physical carrier absent. No usable LiDAR connection proven.'
  exit 3
fi
echo 'GATE_LINK_PRESENT: next check configured host IP and real /livox/lidar + /livox/imu messages.'
