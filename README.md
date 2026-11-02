# RTRC 4PRO 巡检原型

先读 [HANDOFF.md](HANDOFF.md)、[今晚验收记录](docs/今晚验收记录.md) 和 [演示操作卡](docs/演示操作卡.md)。当前为两天方案持续开发的限定原型，不依赖虚拟机；下方描述以2026-11-02交付核对为准。

课程交付：见[项目分工与固定代码索引](docs/项目分工与代码索引.md)，职责按40%/30%/30%划分。课程报告与独立分工Word含学号，由本地 `交付文档/` 单独提供，不纳入Git；功能代码固定快照为 `b637b5cf7ceedc39255dd1dbf32b8b1d60d828a5`。

## 已有功能
- Flask/Waitress管理端与采集控制均运行在小车：登录、画面预览、异常图库、任务创建、处理照片提交、复核关闭；Android浏览器访问车IP:8765，Windows用于SSH与浏览器开发。
- Jetson：RealSense彩色采集、YOLOv8n瓶/杯疑似垃圾、HSV绿化候选、人工A/B/C检查点、SQLite事件缓存、失败重试上传。
- 独立底盘适配器：前进硬上限0.15、监护倒车上限0.08、转向±300、租约与0.5秒心跳超时、前向25cm拦截、连续3帧底盘反馈校验；无后向测距，默认hardware_enabled=false。
- 指令时间轴路线支持前进/停车/倒车；新室内短路线录制与单次回放已有人现场确认，无定位纠偏。
- 人工触发DeepSeek视觉复核，持久作业、错误重试和人工确认。正常生活用品不会仅因瓶杯类别自动成为真实垃圾，模型输出与本地候选分类分别保留。
- 前向测距80cm内保存近距目标事件，25cm停车阈值独立；距离参考点是传感器，不是车体保险杠；不是完整可通行区域判断。

## Android 与记录管理
- Android 0.1.1：Java + WebView、可修改车IP、原生停止、照片上传和前后台状态清理，源码在android/，构建见docs/安卓APP.md。
- 路线与异常支持回收站删除/恢复；路线需未使能且录放idle；任务与图片保留，删除不释放证据空间。

## 当前阻断
MID360网口无物理链路，尚无点云/FAST-LIO定位。当前约500Hz非阻塞串口已能控车，但历史偶发`SerialTimeoutException: Write timeout`仍需观察。25cm静态拦截通过，动态刹停距离未验；无回波监护放行不能证明通路安全。后台停止5分钟后20张重启补传、AI失败恢复、室内晚间任务闭环和服务重启已测；真实换电后的工作台自启已测；实际热点断网、三种地面与动态刹停仍缺完整证据；用户已反馈户外夜测正常，但录像尚未归档审阅。不是无人值守产品。

手机独立测试：顶部“手机独立测试操作卡”；电脑可离线。用户cron自启入口`start_at_boot.sh`，只启服务、不使能或恢复路线；路线需手机持续监护。串口异常可停车后“重连底盘”，仍失败则整车重启。

## Windows开发测试（PowerShell，项目根目录）
```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts/init_secrets.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m patrol.server
```
访问 http://127.0.0.1:8765 。账号operator，生成的密码在.local-access/登录信息.txt。已有凭据不会覆盖。已有配对部署应继续使用原凭据，不能单端重新生成。正式演示后台已在车端，不需同时启动Windows后台。

当前config.json中两服务互连均为127.0.0.1，对外绑定0.0.0.0，由登录/CSRF及设备令牌鉴权；只在受控热点局域网使用，不部署公网。Android访问`http://<车IP>:8765/`。delete_uploaded_images默认false，不自动删除未上传证据。独立Windows联调属于可选开发方式，需另行设置robot_url；不要改动现场生产配置来回切换。

## 车端复现
保留厂家Ubuntu20.04.6、ROS Noetic、JetPack、系统Python，不升级推理栈。现有依赖包括pyrealsense2、numpy、cv2、pyserial、torch/torchvision、ultralytics、Flask、requests、Pillow。requirements.txt用于Windows后台，不是Jetson GPU环境重建清单。

部署patrol/、config.json到独立目录；通过私密渠道单独放入相同的.local-access/patrol-secrets.json并设权限600。SSH私钥、令牌和密码不在Git仓库。

模型放models/yolov8n.pt，原下载来源：https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.pt 。权重未上传，遵守上游许可。模型缺失会缓存待识别帧，Windows自动补识别尚未实现。

静态启动（车端项目根目录，不允许硬件写入）：
```sh
sh start_car_workbench.sh
```
现场监护准备驾驶时，启用硬件写入（仍不自动使能或恢复路线）：
```sh
sh start_car_workbench.sh --hardware
```
启动脚本等待旧进程退出，runtime/robot.lock阻止重复实例。勿同时启动厂家相机或串口节点抢设备。停车用网页“停止并锁定”，随后可由SSH向已核验的服务PID发SIGTERM；软件停车不是实体急停。旧start_hw_ground.sh会覆盖当前阈值，不再使用。

## 结构和接口
- patrol/control.py：串口与安全控制；robot.py：采集、测距和上传；vision.py：识别；store.py：SQLite和图片；server.py/templates：后台与网页。
- runtime/server、runtime/robot：各自的数据库及图片，均不上传Git。车端queue.pending才代表待传事件数。
- POST /api/login，GET /api/session：登录与CSRF；POST /api/events：设备令牌+multipart metadata JSON/image，event_id幂等；GET /api/events与/images/{name}：查询。
- POST /api/tasks、GET /api/tasks；POST /api/tasks/{id}/{claim,submit,return,close}。submit需要note和photo。
- POST /api/events/{event_id}/analysis、GET /api/analysis/status：人工触发视觉复核/队列状态；结果随事件和任务返回。私密API配置见[云端识图](docs/云端识图.md)。
- /api/robot/*代理status、preview、checkpoint、capture、sampling、control接口。写请求需登录与CSRF。
- 任务pending→working→review→closed；退回working。位置是人工检查点，不是GPS。绿化是颜色规则，不是树种或病虫害识别。

## 测试与回滚
67项Python自动测试与Node客户端测试通过，使用临时库/模拟控制，不驱动实车。scripts中的现场验收脚本与自动测试不同，凡标注attended的运动脚本必须有当次现场确认，不能自动批量运行。现场边界见HANDOFF。厂家原文件未修改；回滚时停止原型、保留runtime证据和私密配置，再恢复备份。控制进程死亡或串口写失败时，最后的停车帧可能送不到（driver_error记录“停车帧未送达”）；控制板自身失帧停车仍未验证，不能在可能运动时强杀进程。

vendor_review保留厂家示例及版权声明，不代表对厂家代码重新授权；完整厂家资料、现场证据、模型和凭据由原负责人另行交接。

现场脚本start_bench.sh、start_monitor.sh、bench_deadman.py、bench_obstacle.py只在车端部署目录，未入库；交接文档中的引用仅为历史记录。
