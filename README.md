# RTRC 4PRO 巡检原型

先读 [HANDOFF.md](HANDOFF.md) 和 [继续开发交接.md](继续开发交接.md)。PROJECT.md保留早期设计背景，当前已缩为两天限定原型，不依赖虚拟机。

## 已有功能
- Windows Flask/Waitress管理端：登录、画面预览、异常图库、任务创建、处理照片提交、复核关闭；Android浏览器访问同一网页。
- Jetson：RealSense彩色采集、YOLOv8n瓶/杯疑似垃圾、HSV绿化候选、人工A/B/C检查点、SQLite事件缓存、失败重试上传。
- 独立底盘适配器：限幅、租约、心跳超时、前向测距拦截。默认hardware_enabled=false。

## 当前阻断
底盘出现 `SerialTimeoutException: Write timeout`，500Hz降到100Hz仍重现，尚未根治。实车障碍停车未通过；自动路线、实际断网补传、夜间与三种地面验收未完成。不得视为可无人值守运行的产品。

## Windows后台复现（PowerShell，项目根目录）
```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts/init_secrets.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m patrol.server
```
访问 http://127.0.0.1:8765 。账号operator，生成的密码在.local-access/登录信息.txt。已有凭据不会覆盖。已有配对部署应继续使用原凭据，不能单端重新生成。

config.json中的server_url改为Windows热点IPv4:8765，robot_url改为小车IPv4:8766；Android访问Windows地址。避免重复启动后台。

## 车端复现
保留厂家Ubuntu20.04.6、ROS Noetic、JetPack、系统Python，不升级推理栈。现有依赖包括pyrealsense2、numpy、cv2、pyserial、torch/torchvision、ultralytics、Flask、requests、Pillow。requirements.txt用于Windows后台，不是Jetson GPU环境重建清单。

部署patrol/、config.json到独立目录；通过私密渠道单独放入相同的.local-access/patrol-secrets.json并设权限600。SSH私钥、令牌和密码不在Git仓库。

模型放models/yolov8n.pt，原下载来源：https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.pt 。权重未上传，遵守上游许可。模型缺失会缓存待识别帧，Windows自动补识别尚未实现。

普通静态启动（项目根目录）：
```sh
python3 -m patrol.robot
```
只读底盘监测，不发送控制指令：
```sh
PATROL_CONFIG_JSON='{"hardware_enabled":false,"serial_monitor_only":true}' python3 -m patrol.robot
```
Ctrl+C或SIGTERM停止。确认旧进程退出、相机和串口释放后再启动；runtime/robot.lock阻止重复实例。勿同时启动厂家相机或串口节点抢设备。只有现场人员确认架空与断电手段后才可开启硬件写入；本README不提供一键运动操作。

## 结构和接口
- patrol/control.py：串口与安全控制；robot.py：采集、测距和上传；vision.py：识别；store.py：SQLite和图片；server.py/templates：后台与网页。
- runtime/server、runtime/robot：各自的数据库及图片，均不上传Git。车端queue.pending才代表待传事件数。
- POST /api/login，GET /api/session：登录与CSRF；POST /api/events：设备令牌+multipart metadata JSON/image，event_id幂等；GET /api/events与/images/{name}：查询。
- POST /api/tasks、GET /api/tasks；POST /api/tasks/{id}/{claim,submit,return,close}。submit需要note和photo。
- /api/robot/*代理status、preview、checkpoint、capture、sampling、control接口。写请求需登录与CSRF。
- 任务pending→working→review→closed；退回working。位置是人工检查点，不是GPS。绿化是颜色规则，不是树种或病虫害识别。

## 测试与回滚
8项自动测试使用临时数据库，不驱动车辆。现场边界见HANDOFF。厂家原文件未修改；回滚时停止原型、保留runtime证据和私密配置，再恢复厂家流程。控制进程死亡后的底层停车未验证，不能在可能运动时强杀进程。

vendor_review保留厂家示例及版权声明，不代表对厂家代码重新授权；完整厂家资料、现场证据、模型和凭据由原负责人另行交接。
