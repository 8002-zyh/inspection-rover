## T-419 课程报告、分工与最终代码交付（2026-11-02 最新）
- 用户授权完成课程设计报告、独立分工说明及最终代码上传。功能代码已提交并快进推送至 `feat/patrol-prototype`，固定快照 `b637b5cf7ceedc39255dd1dbf32b8b1d60d828a5`；包含此前 T-414 至 T-418。下方历史“未 push”描述已由本项取代；没有强推、没有修改 main。
- 本地交付在工作区根目录 `交付文档/`：`课程设计报告-RTRC4PRO巡检系统.docx`（30页）、`项目分工说明-40-30-30.docx`（5页）。依用户提供的学院、班级、成员和教师信息填封面；教师评分/签字留空。Word含学号，按本次交付策略只在本地提供，不入Git。
- 责任分配：赵宇航40%负责架构/底盘控制/路线/集成；李航乐30%负责硬件核验/相机测距/启动恢复/现场测试；韩亚林30%负责视觉/数据任务/网页/Android。是责任设计与复核分工，不伪造成员历史独立提交或工时，明确使用Codex辅助。
- 公开索引 `docs/项目分工与代码索引.md` 含17个固定快照、文件与行号链接，不包含学号。Word同样含可点击代码位置，并注明对应报告章节、子任务权重和共同验收责任。
- 验证：67项Python测试、Node HTTP客户端与Android生命周期测试通过；两份Word逐页渲染检查，32项目录页码与正文一致，17个代码链接与固定快照核对；原DOC不改，14个模板页眉/页脚/媒体部件字节保留。本轮未发车辆使能、运动或回放命令。
- 事实边界保留：人工监护、指令时间轴录放，不是定位导航；用户反馈户外夜测正常，录像尚未归档审阅；MID360物理链路、三地面对比、动态刹停和底层完全失联停车仍缺完整证据。
- 复现：项目Python环境执行 `python -m unittest discover -s tests -q`、`node tests/test_http_client.cjs`、`node tests/test_android_lifecycle.cjs`。报告生成源与渲染QA只在工作区根 `runtime/course-docs-T419/`，不入Git；密钥、运行库、模型和私人照片继续排除。
- 回滚：此次说明提交不改运行代码。需要撤销说明时使用对应文档提交的 `git revert`，保留后续数据；功能代码基线仍为上述固定快照，勿用旧数据库覆盖新任务。

## T-418 路线/异常回收站与图标 0.1.1（2026-11-02）
- 用户要求删除路线、删除异常及美化APP图标。源码分支feat/R-418-library-cleanup，继承此前未提交工作；未推送。未发送使能、非零指令或路线回放。
- 路线JSON保留样本，新增deleted_at软删除；车端GET /routes/trash，POST /routes/delete、/routes/restore。操作需路线idle、控制未使能且旧回放线程结束；网页提供“删除所选路线”和可恢复回收站，选路后可删。
- 事件新增event_trash表，GET /api/events?deleted=1、POST /api/events/<id>/delete、/restore，保留登录/CSRF/设备令牌保护。图片、关联任务与未上传证据保留；重复上传不复活 tombstone，任务仍可处理；待执行AI作业暂缓、恢复后可继续，已开始作业可能完成。删除不回收磁盘空间。
- 两种删除均使用HTML dialog二次确认（取消/Escape/点遮罩均不删除）；原生confirm在IAB验证时阻塞，已替换且重新部署，仅重启网页服务。页面重载后APP与浏览器共用功能。
- 新增tests/test_delete.py，67项Python测试+Node HTTP客户端/Android生命周期测试通过；覆盖旧DB迁移、重复删/恢复、重启/补传、任务/图片保留、路径校验、鉴权和录放互斥。实际车端API与浏览器删除/取消/恢复通过，仅操作test-delete-T418-zero及app-upload-test-20261102-01软件夹具，原有路线/任务不改；最终测试路线在回收站，测试事件恢复。根runtime/evidence/delete-restore-T418.json及workbench-route-delete-T418.png、workbench-event-trash-T418.png留有证据，不入Git。
- 原生图标改为蓝底白色小车+薄荷绿叶，Android adaptive/monochrome资源；版本0.1.1(2)。官方SDK直构建、v2/v3签名与zipalign通过；USB覆盖安装成功，pm版本及已装base.apk SHA256一致：9df722615b63f11aed6393cedc6e4618afd206e81d9a6eb1abe3f664bb78c2c4。根runtime/delivery-20261102-android/保留0.1.0与0.1.1 APK及报告。仅图标及APP库管理样式变化，未改原生控车/权限。
- 车端备份~/patrol-prototype/backups/T418-before-20261102/，含code-and-routes.tgz及两库在线备份；本轮后端已部署。收尾需保持车静止/路线idle；软删除恢复优先用界面，勿用旧数据库覆盖新增巡检数据。
- 代码回滚：停车且route idle后在车端目录tar -xzf backups/T418-before-20261102/code-and-routes.tgz，再sh start_car_workbench.sh --hardware（会重启两服务，不会自动使能）。归档含路线快照：仅在尚无新路线时整包回滚，否则tar按patrol/文件选择恢复，保留runtime/robot/routes。数据库新增表可保留，旧代码不读取；不需还原数据库。APK降级用原0.1.0调试包adb install -r -d，不卸载。

## T-417 Android APP 0.1.0（2026-11-02 最新）
- 用户夜测反馈正常，继续安卓APP；随后提供apple-ui-designer与apple-design-skill设计参考，已读取SKILL/相关规范与许可说明，只参考原则，自写代码/CSS，未复制第三方规范文本。
- 新增android/独立Java+WebView工程，包cn.rtrc.patrol，min26/target35/compile36.1；地址设置、Cookie登录、同源访问、原生常驻停止、系统选照片、暂停JS定时器/回前台清控制状态、Android返回及系统主题。只保存地址，不内置设备令牌/密码/APIkey。网页浏览器主题不变。
- 分支feat/R-417-android-app从R-416继承，保留此前未提交的T414/T415/T416工作。本轮未推送或改车端控制程序。
- Gradle本机因Java AF_UNIX回环报Unable to establish loopback connection未通过；采用scripts/build_android_direct.py调用官方SDK工具构建并校验v2/v3签名与zipalign，无修改JDK/宿主网络。纯Java地址JUnit3项通过；Node原生生命周期JS测试通过。
- Vivo V2301A USB安装/启动，用户手动更新修正版后pm base.apk SHA256与最新APK一致（0cd00457cd758eadca18cbad575d4392fa0f75fa1470eca9d2a3eaf596102c68）。曾自动审批拦截“检查状态+覆盖安装”组合命令，工具未给具体理由；改由推送APK到Download后用户手动更新，没有绕过安装限制。
- 实机用户完成APP登录/实时画面/照片选择上传/Home回前台。软件测试事件app-upload-test-20261102-01、任务84a7b131b653463a81ae839c7be40875当前review，说明“APP上传测试”，服务器图片200/685447字节且PIL校验通过。不是夜巡真实异常，不增加真实闭环验收计数。根目录证据runtime/evidence/android-upload-test-20261102.json。
- APK与说明交付在根runtime/delivery-20261102-android/；手机Download/inspection-rover-0.1.0-debug.apk也留有同包。android/.gitignore排除构建产物、local.properties、签名密钥；不要把手机序列号、照片截图与runtime提交Git。
- 最新车端静态核对：未使能/RPM0/transport_ok=true/driver_error空，队列pending0/failed0、DB quick_check ok，仍3条原真实closed任务；用户反馈夜测正常，录像、三地面、定位与动态刹停仍缺证据。APP行驶中切后台实测停止时间未验证，未为测试发运动指令。
- 复现/安装/回滚见docs/安卓APP.md，视觉审查见docs/安卓界面审查.md；卸载APP不影响车端数据。若变更网页DOM需复核APP专用assets样式和生命周期JS的兼容性。

## T-416 工作台 UI 重构（2026-11-01，优先于旧页面说明）
- 用户要求先看工作台改版，再讨论两小时安卓APP；本轮仅实现网页，尚未开发APK。源码分支feat/R-416-workbench-ui，保留先前未提交的T-414/T-415改动，未推送。
- index.html重组为现场巡检/异常记录/处理任务，新增static/workbench.css（墨蓝/薄荷绿、移动端底部导航）。主界面只展示连接、控制、待补传、检查点；诊断JSON、历史停止细节和指南默认折叠；关键连接/相机/补传错误仍在页面可见。固定顶部停止按钮，原心跳、离页停车、路线监护及参数不变。
- 任务按状态筛选，卡片保留前后照片与处理说明，AI结果概要可见，展开查看依据/限制/模型。类别候选含义、人工检查点与时间轴路线边界保留。
- 修正路线列表刷新：占位option的value现在为空，未选路线禁回放；目录不变时不反复重建select，避免2秒状态轮询打断选路。未发送非零运动、录制或真实回放。
- 59项Python+Node脚本通过；实机浏览器登录、刷新会话、390px无横向溢出、1280px布局、折叠诊断、空任务筛选、3条closed任务、200张事件卡片加载/无观察到的破图、控制台无错误均已核验。手机实机触控运动/新上传未复测；相应后台接口未改。
- 已部署，仅重启web server（robot10023保持）；车辆未使能/RPM0/底盘反馈正常，监护放行配置不变。Windows证据runtime/evidence/workbench-ui-T416.json；截图runtime/workbench-ui-desktop.png、workbench-ui-mobile.png、workbench-ui-tasks.png，勿提交私人照片截图。
- 车端备份backups/workbench-ui-before-T416.tgz。回滚：停车且路线idle后，在~/patrol-prototype执行tar -xzf backups/workbench-ui-before-T416.tgz，再重启网页服务；可用sh start_car_workbench.sh --hardware统一恢复（会同时重启控制，切勿行驶中使用）。新增CSS可留作未引用文件，不影响旧页。
- 安卓估时：本机已有Android Studio、Java21、SDK android-36.1/build-tools。建议下一轮约2小时做WebView原型：可修改车IP、登录/网页复用、照片选择上传、前后台生命周期停车、APK真机安装测试。未验证Gradle完整构建链，不保证两小时；不扩大为原生全量重写/离线地图/后台无人监护。

## T-415 测距不可用监护放行（2026-11-01 23:06，优先于历史策略）
- 用户明确授权：人工监护录线/回放不再因缺测距锁车。新增 `front_range_failure_policy=allow_supervised`，已写入车端持久配置；状态7、无回波、坏帧、数据超时/缺失/非有限距离均不因测距原因停止。代码未配置该键时仍默认stop。
- 只用新鲜≤0.5秒、帧/状态/强度有效且有限正距离做近障判断；有效距离≤0.25m仍停止并需要重新使能。无效数据继续显示不可用，未伪造有效距离或“前方安全”。控制心跳0.5秒、底盘串口失联停车及原速度限幅保持。
- 修改：config.json、patrol/control.py、patrol/templates/index.html、严格策略测试fixture；新增tests/test_supervised_range.py。59项Python与Node客户端通过；在车端独立Guard（不创建串口驱动）模拟missing/status7/near/stale_near通过。
- 部署前确认未使能/duty0/新鲜RPM0/route idle；备份 `~/patrol-prototype/backups/supervised-range-before-20261101.tgz`。部署后HTTP200、新策略字段/UI生效、transport_ok=true、driver_error空、未使能/RPM0，未发真实使能或运动指令。证据Windows根目录runtime/evidence/supervised-range-before-20261101.json与supervised-range-after-20261101.json。
- 运行策略是人工观察兜底，不提供传感器失效时的自动避撞保障；动态近障制动和用户重新录线效果尚未验收，不称自主避障。旧“状态7仍停车”说明已被本项明确替代。
- 复现：在tmp/ir-push运行 `python -m unittest discover -s tests -q`、`node tests/test_http_client.cjs`。回滚须停车后在车端目录运行 `tar -xzf backups/supervised-range-before-20261101.tgz`，然后 `sh start_car_workbench.sh --hardware`；旧策略会恢复失效锁定，不自动使能。此次未提交/推送。

# 2026-11-01 晚间：T-406云识图、手机闭环与恢复验收

## T-414 重连后使能置灰修复（22:35之后最新）
- 用户确认原本可使能，点击“重连底盘”后置灰。日志22:31:39/42/45连续重连；静态检查hardware_enabled=true但feedback_at/RPM为空、transport_ok=false，UART仅robot占用，无ttyTHS0 getty冲突。
- reconnect_chassis现在在停车/路线idle前置检查后核对新鲜反馈；连接健康时直接返回already_connected=true、started=false，不关闭或重开UART，不清除反馈。按钮请求期间禁重复点击，正常时提示“底盘连接正常，可直接使能”。
- 原robot.py/index.html备份backups/reconnect-noop-before-20261101.tgz；已部署，静态重启服务后恢复新鲜RPM0/transport_ok=true/driver_error空；未发使能或运动。
- 54项Python+Node通过；真实API连续3次正常重连均返回no-op，反馈始终新鲜且RPM0，HTTP首页已包含新按钮处理。Windows证据runtime/evidence/reconnect-noop-20261101.json。新修复暂未提交，基线efd11fe。

## 换热点重新连接（22:20最新）
- 用户拍视频后回来更换热点，当前小车 **10.212.93.243**、Windows10.212.93.66；工作台 **http://10.212.93.243:8765/**。原SSH身份严格校验通过，原凭据不变。
- 服务自启已在，无需重启；首页/相机HTTP200、新鲜轮速0、无driver_error、路线idle、待上传0，3条closed任务保留，数据库quick_check=ok。此次未使能或发送运动。
- 本地源码已提交 **efd11fe**，尚未推送；下方“本轮未提交”属历史。用户拍视频时要求暂停；本次只恢复连接，户外视频与测试结果待接收审核。

## 21:30 手机独立操作（最新）
- 用户明确：室外只有小车和Android有热点信号，电脑将离线，要求手机独立操作。两服务原本就在车上；现已补全手机自助恢复与操作卡，operator仍使用原账号，不新增root权限。
- T-412：路线增加独立监护token及`POST /routes/watch`，前端100ms续监护；车端超过原heartbeat_timeout=.5s未收到监护则中止，不再仅靠内部续Guard心跳继续。切后台/离页主动停止。令牌不暴露在status，不入证据日志。CLI旧回放客户端必须续watch；verify_short_playback.py已适配。
- 车端零动力自检：无监护约.584秒观测到中止，持续监护2.107秒正常结束，所有duty/RPM为0；不是运动刹停或实际热点断网试验。实际工作台按钮回放同一零动力路线也正常结束，页面显示路线回放结束。证据runtime/evidence/phone-mode-20261101.json。
- 手机新增“重连底盘”：只在未使能、duty0、路线idle时允许；控制/回放与重连共用互斥锁。旧串口线程不退出则拒绝第二实例。不改变模式或自动使能。一次真实Write timeout后请求重连未恢复RX，整车重上电恢复；因此该按钮不是所有串口故障的保证修复，失败需整车重启。
- 已用orin自己的crontab安装单个@reboot块，保留原任务，备份放.local-access。入口start_at_boot.sh等待日期有效后运行start_car_workbench.sh --hardware；不会自动使能或恢复路线。安装/移除：python3 scripts/install_boot_start.py [--remove]。
- 用户真实整车重上电，boot_id从77412655-49ee-4b2b-aae0-dd4c9d2a28d7变为f9167898-d805-47cb-8902-9f424698e885，uptime不足1分钟时工作台已由cron启动，robot2984/server3625（PID会变）；随后零动力API和实际网页自检均通过。首次换电池启动曾回1970，NTP自动恢复，启动脚本现有无效年份检查。
- 任务A/B/C现均closed；C手机断电前没提交成功，重启后重新接单/上传，状态review后核对照片纸箱已移走，再由Codex复核关闭。说明实际保存为“OK”；B实际为“完成”。不伪造为建议的长说明，不将B正常保温杯核查计作垃圾识别成功。全部是室内晚间白光测试，户外待用户现场测试。
- 53项Python+Node客户端测试通过。页面顶部“手机独立测试操作卡”可展开，包含自启、重连、控车、录放、检查点、AI、任务；用户现场自行操作，不再需要Codex远程逐次授权。电脑离线无影响；手机掉线仍需停车。
- T-409已部署：obstacle_event_distance_m=.8，仅用于留证；stop_distance_m=.25不变。纸箱.329m有效测距自动产生C点obstacle事件并上传；距离以传感器为参考。补非有限/失效/过期过滤，控制Guard未改。API明确autonomous_available=false、route_type=command_timeline。
- T-411离线验收包导出脚本scripts/export_evidence.py（只读库、任务照片哈希、HTML转义、不复制私密配置）；已导出runtime/delivery-20261101-indoor，3条closed、6张前后照片、9份测试报告，图片哈希与密钥扫描通过，中文HTML真实浏览器渲染已核验。完整户外夜巡、三种地面、10–20m路径/定位精度、运动中断线刹停、最终录像仍未完成。目标保持active。
- 21:46只读检查仍未发现新增户外事件或任务；用户答复将进行室外测试并使用手机录屏。保持现场由用户操作，后续只读拉取结果，不远程重启、停止或使能打断测试。

## 20:13 T-403室内地面短脉冲录放
- 用户更正：实际仍在室内（不是户外），确认至少1m净空、车旁监护；新录route-f7dfff72cf，前进0.07/0.35秒、停、倒车-0.08/0.35秒、停，约2秒直线时间轴，无转向，无定位纠偏。
- 显式单次回放同一新路线，观测duty -0.08/0/0.07与RPM -19/-7/0/5/17，route_error空，终点reason=路线回放结束、enabled=false、duty0、新鲜RPM0。用户回答“两轮动作都正常，结束已停车”。不是长路线精度或三次重复验收。
- 证据runtime/evidence/short-route-record-20261101-201139.json、short-route-play-20261101-201305.json；测试脚本scripts/verify_short_route.py、verify_short_playback.py只用于当次确认的净空/监护场景，不得无人盲跑。
- 用户已摆好杯子，接下来停车采样、AI和第二条手机任务。户外夜巡仍未验。

- 本段优先于下方历史。工作目录tmp/ir-push，分支feat/T-WX-LOGIN，基线dbdc0dd；本轮改动尚未提交/推送。
- 官方DeepSeek deepseek-flash视觉已接入：`patrol/analysis.py`、server API、事件/任务页面。人工选图，异步持久化，依据/建议/限制可见；不控制车辆。私密配置`.local-access/vision-api.json`，不在仓库。
- 现场19:33:59检查点A任务`f658df61d9a54bf29eb13e1063f35d65`，Android用户上传处理后照片、说明“解决了”，数据库与页面均closed；是室内白光夜间受控样张，不代表户外林地识别精度。AI正确给出uncertain。
- T-407后台停止300.3秒：20张样本持久保存，robot重启后队列保留，后台恢复全部补传，无缺图、无重复ID，重复上传created=false。证据`runtime/evidence/backend-outage-20261101.json`。不是实际热点中断。
- T-406 AI恢复：独立诊断库中网络拒绝3次保留任务，每次由新进程重试；首次恢复云调用返回无效JSON，人工再次重试成功、图片哈希相同。生产任务没被改写。脚本`scripts/verify_ai_recovery.py`。
- T-408定位前置失败：MID360配置host192.168.1.50/lidar192.168.1.137；eth0 carrier0/NO-CARRIER、无host地址，传感器驱动短探测bind failed/SDK init failed，无点云。FAST-LIO与Livox编译产物存在、合并ROS overlay后无缺失库；不要启动含旧坐标/直接动力的厂家巡航脚本。未建图，无定位纠偏。
- 45项Python测试与Node客户端测试通过。前进0.15、倒车0.08、转向±300、前方25cm、无回波监护策略不变；动态停车距离仍未验收。
- 新操作卡`docs/演示操作卡.md`、识图说明`docs/云端识图.md`、总验收状态`docs/今晚验收记录.md`。启动脚本新增显式`--hardware`，默认仍只读；不覆盖当前速度/阈值，不自动使能/恢复路线。已部署并验证硬件模式服务重启：零duty/新鲜RPM0/未使能，预览200、待上传0、关闭任务和AI结果保留；不是整车断电冷启动。备份backups/start-workbench-before-20261101.sh。
- 用户已表示今晚可去室外平整路面、有白光且可车旁监护。待确认车已在起点，再录新场地短路线与采集真实户外夜间样张。三种地面、实际热点断开、定位路线、最终录像/冷启动仍未完成。

# 2026-11-01 用户要求AEB阈值25cm

## 停车原因与当前测距分离（2026-11-01）
- 用户见车遇障减速但显示测距失效。静态检查0号连续有效.410–.411m、状态0/强度38，控制仍保留历史reason=前方测距失效；旧版没有触发时帧，不能追溯当时具体原因。代码是归零停车，无渐进减速控制。
- Guard增加last_stop：启用到停车时快照时间/原因/前方ID/阈值/当时距离、状态码、强度、数据年龄。恢复读数或后续操作员stop不覆盖证据；UI分开展示“上次停止原因”和当前测距，未改保护条件。
- 39项Python+Node客户端测试通过，已部署；备份backups/stop-evidence-before-20261101.tar.gz。不自动发车；下次发生时读last_stop即可判断过期/坏帧/异常状态。

## 无回波监护策略补充
- 用户手机持续报“连接失效”，实测并非网络断开：0号frame_ok=true、status0/strength0连续出现，原255-only策略仍会触发测距失效。
- 按用户先前明确要求无回波放行，allow_supervised扩展为：fresh<.5s+frame_ok+(status255或status0/strength0)。这些仍valid=false、distance=null、state=no_target/no_echo，不能宣称前方安全。status7/坏帧/过期及有效近障仍停车。
- 心跳成功响应若enabled=false，页面立即显示reason并清除本地lease；后续会话错误携带实际停车原因，不再把保护锁定泛称网络断开。
- 37项Python+Node测试通过，已部署；车端连续确认串口正常、state=no_echo、策略allow_supervised。未自动发送非零运动，待用户手机复验。
- 备份backups/no-echo-before-20261101.tar.gz。当前是用户选择的监护模式，非fail-safe AEB，应在后续场地/产品验收报告明确此限制。

## 同日用户要求无回波允许行驶
- 用户要求“无回波视作前方安全”。实际实现更精确的front_no_target_policy=allow_supervised：仅校验正常、对应ID、新鲜<.5秒且dis_status=255（厂家定义未检测到目标）可监护放行，不把无回波标作有效距离或安全保证。
- dis_status=7为相位不匹配，其他故障/strength0且status0、超时、坏帧依旧停车；近于25cm依旧停车。参考厂家 https://support.nooploop.com/cn/tofsense/FAQ-for-tOfsense/ 。
- 增加range字段frame_ok/sensor_status/state；无效距离设null，不显示残留7m值；页面提示当前策略。35项Python+Node测试通过，已部署。
- 部署备份backups/no-target-before-20261101.tar.gz。重启一度复现底盘Write timeout，正在静态恢复；未发送运动。不要声称所有no echo均可放行（status0弱信号或7仍故障）。

- 静态近障通过后用户报告手机“前方测距失效”。停止状态抽样发现0号valid频繁false、距离约2.36/7.0m跳动。
- 已在停止车端后独立采30条原始0号帧：30条header/ID/checksum均正常；strength多次0、status多次255，偶有status7/strength1；开头偶有status0/strength1。厂家示例明确strength0为超出检测范围的无效值；不能把7m残值当作通路。
- 诊断脚本finally重新启动robot，PID14066（会变），配置仍前方0/25cm，硬件true但未使能；未发运动指令。此问题是有效测距缺失，不能简单延长过期阈值/把无回波视为远处来放行。
- 下一步要求用户静态放纸板约50cm，再观测有效回波是否恢复；若恢复，评估无遮挡/远目标时探测覆盖与量程约束，尚不可称AEB实用验收完成。

- 25cm静态拦截随后实测通过：第一次距离漂到.251–.252m，脚本按前提条件拒绝发送；用户再次移近并确认后，bench_obstacle25.py确认配置ID0/阈值.25、距离有效且小于阈值，再请求duty=.03；响应立即duty=0/enabled=false/reason=前方障碍停车，随后新鲜轮速0，无driver_error，最后显式停止。
- 该证据仅为静止状态拒绝前进，不等于动态刹停测试通过；仍需实际低速接近障碍的制动距离、移除障碍不自动恢复、测距失效实测。

- 用户明确要求将50cm缩为25cm；车端与工作仓库config.json已改stop_distance_m=.25，前向ID保持0。备份backups/config-before-aeb25-*.json。
- 控制进程重启，未发运动，默认会话锁定。此前44cm/50cm静态拦截证据不适用于证明25cm动态停车安全；需重新做近阈值静态和低速实际刹停验证。

# 2026-11-01 T-404 AEB静态拦截已测

- 用户车头纸板约40cm，0号5次读数0.441–0.442m有效，全程未使能/零duty。
- 备份车端配置后，将front_sensor_id=null改0，stop_distance_m=.25改.5（保守静态试验阈值，非制动距离标定），硬件写入保持true；配置备份backups/config-before-aeb-*.json。
- bench_obstacle.py校验前方有效距离<.5和保护已配置，再请求duty=.03；同一command锁内拦截，响应duty=0/enabled=false/reason=前方障碍停车，随后新鲜轮速反馈0，无串口错误。末尾显式停止。
- 当前AEB已接入0号、阈值.5m，用户重新使能后操作。未做动态接近障碍刹停、全宽覆盖或断测实测，禁止标T-404全部完成。
- 下一步移开纸板观察距离回升，再验证解除障碍不会自动恢复行驶；空间/停车距离未标定之前不做朝纸板自动冲近测试。

# 2026-11-01 新路线现场回放后检查

- 用户重新录制并回放route-eec947a236（现场录制），54.689秒/474样本，其中136条负duty，最小-0.08，最后指令0。
- 用户回复“没问题下一步”；检查车端mode=idle、reason=路线回放结束、enabled=false、duty=0、新鲜feedback_rpm=0、driver_error为空。支持本次回放结束停车记录，不代表路径重复精度或AEB通过。
- 下一步前向AEB：车端obstacle_protection=false，现有配置front_sensor_id=null、stop_distance_m=0.25。先静态纸板重新核对当前前方读数，再决定接入；不直接用未标定距离开展动态障碍测试。

# 2026-11-01 R-009 倒车路线修复（本地未推送）

- 用户现场回放报告倒车丢失，明确要求录放支持倒车。定位到RouteController.note_command将负duty裁为0、validate_route拒绝负duty。
- 现保存负duty，复用HARD_MAX_REVERSE_DUTY=0.08限制；回放已有Guard限幅不变。补非有限数值检查。
- 本地32项Python+Node请求/脚本测试通过；车端9项路线测试通过（均不连接串口驱动车辆）。新增保存/重载/Guard回放负向指令回归测试。
- patrol/route.py备份车端backups/route-before-reverse-20261101.py，已部署修复，重启保留hardware_enabled=true配置，由用户手机重新使能。未自行执行实车倒车回放。
- 用户此前录制route-57018d5990总44.588秒/403样本，倒车已被旧版裁为0，不能补推测数据。必须重新录制后验收前进/倒车/转向及终点停止。
- 此前双闪UI按钮和相关空节点引用已删除，大灯保留。旧交接“路线禁负duty”已被此项取代。

# 2026-11-01 Codex T-WX-LOGIN修复（本地未推送）

- 基于GitHub tip dbdc0dd，工作分支feat/T-WX-LOGIN。旧交接的“多数提交未push”已由用户确认的推送取代；旧hash按提交标题对应。
- 在原tip页面上用Node解析复现 `SyntaxError: Unexpected token ')'`：updateStatus的灯光textContent赋值多了一个右括号，导致整个inline script不执行，登录无法提交。现已修正。
- 增加patrol/static/http.js：超时涵盖fetch和响应正文，即便没有AbortController仍可返回超时错误；显式same-origin Cookie；登录后验证/api/session，按钮finally恢复；初始会话请求不覆盖新登录；状态和预览单飞避免请求堆积；HTML/API/脚本no-store。
- 本地30项Python测试通过，`node tests/test_http_client.cjs`通过（真实inline语法、无AbortController、正文卡住、错误和恢复）。尚未替代Android各浏览器现场验收。
- 车端原server.py/index.html已备份到backups/login-before-20261101.tar.gz，新文件已部署。以现有start_car_workbench.sh启动，hardware_enabled=false；未发送运动或灯光命令。
- 最新车IP10.71.225.243，工作台http://10.71.225.243:8765/。真实GET首页/脚本/会话/状态/预览均200，预览有图片；使用签名会话做只读链路检查，真实用户登录尚待现场复验。
- 回滚：静态停止工作台服务后恢复上述备份的两个文件，新static/http.js可保留，不改凭据。下一步用户浏览器强刷并登录，确认可进和错误密码可重试，再进入T-403；运动需现场确认。

# 当前交接：2026-11-01 17:21 CST — Codex 接手（软件控车已通）

- 分支：`feat/patrol-prototype`；本地 tip 见下方 commits。**多数提交未 push**；勿擅自 push/merge/开 PR。
- 交接原因：巡检小车 manager 会话收尾；用户改由 Codex 继续。工作台部分客户端登录后卡住（PC PowerShell 测 `/api/login`、`/api/status`、preview 曾返回 200，前端仍可能卡死）→ **优先稳定登录 UX**。
- 阅读顺序：本段 → `TASKS.md` → `docs/车端工作台.md` → `patrol/control.py` / `patrol/robot.py` / `patrol/templates/index.html`。

## 已证实

- **软件控车（R-003 核心）**：部署 ~500Hz 非阻塞 RX 环（`56640d5`，`CHASSIS_LOOP_HZ=500`）后，直连脉冲 duty `0.07` 反馈轮速最高约 **94 rpm**；用户确认轮子在转。此前 100Hz/`a8a05c5` 阶段常 `feedback_rpm=0`。
- **手动参数（本地已提交并曾部署车端）**：前进硬上限 `HARD_MAX_DUTY=0.15`、转向 `steering_limit=±300`（`d8a9198`）；临时倒车 `HARD_MAX_REVERSE_DUTY=0.08`（`4d7d852`，无后向测距，须现场盯急停）；路线录制/校验仍禁止负 duty。
- **灯光**：大灯经 UART TX `Headlight` 字节可控（`9ad1a60`，工作台 `/control/lights`）；**双闪/转向灯 TX 无字节**，UI 禁用。
- **工作台架构**：车端同时跑工作台 `8765` + robot `8766`（`~/patrol-prototype`）；密钥 `.local-access/`（勿提交）。浏览器须 **`http://<车IP>:8765/`**（不是 https）。手机/PC/车须同一 Wi‑Fi 热点；热点切换后车 IP 会变（曾见 `10.155.221.243` → `10.212.93.243` → `10.71.225.243`）。心跳是 **浏览器 ↔ 车端 8766 控制租约**，与笔记本是否在线无关。
- **登录超时兼容**：`7f25c26` 修 `AbortSignal.timeout` 在部分手机浏览器不可用；本 tip 另含登录 UX（「登录中…」/「已进入工作台」）与 `SESSION_COOKIE_SAMESITE=Lax`。
- **单测历史**：改动过程中 `python -m unittest discover -s tests -v` 曾 **25–26 passed**；本交接机缺 Flask/werkzeug，未能当场重跑。

## 未验证 / 勿宣称 Done

- 地面短路线录制+复走（T-403）：提速/倒车/大灯改动后**未再实地验收**。
- 前方 AEB 正式实车障碍停车：监护测车阶段曾关防撞；仓库 `config.json` 现为 `"front_sensor_id": 0`，上车须核对实际值，**勿默认已关或已验收**。
- 工作台登录在所有手机/浏览器上稳定可进（仍有卡住报告）。
- 双闪串口可控、夜间补光闭环、三种地面、断网补传、Android 现场过程。

## 阻塞

- 电池：早前两块 LiPo 在格氏 IMARS mini 上「左两格闪」拒充（欠压/压差/供电告警一类）；用户已换新电池。车上低压报警器平衡头：**黑线贴 ⊖，依次 1S–3S，4S+ 空**（此件是监测不是充电器均衡）。
- 用户明确：**推送/合并/CI、真实运动指令**须批准；部署可备份后进行。
- 垃圾策略：只上报不停车。

## Codex 接下来优先（1–3）

1. **稳定工作台登录**（复现登录后卡死；核对 cookie SameSite、强制刷新、http 非 https、同热点）；必要时最小前端/会话修复，保留 `.local-access` 口令不动。
2. **T-403 地面短路线**：命名录一条 + 回放走完；发现垃圾只上报；遥控关、急停旁、低速。
3. **谨慎加回前方 AEB**：合适阈值纸板近距能停、误锁不明显；不稳则保持关闭并写证据。

## 本地 commits（新→旧，相对本交接）

- 本 tip：docs Codex 交接 + 登录 UX / SameSite Lax（见 `git log -1`）
- `7f25c26` 移动端 AbortSignal.timeout 兼容
- `9ad1a60` 大灯 UART；双闪不支持
- `4d7d852` 临时倒车 0.08
- `d8a9198` 前进 0.15、转向 ±300
- `56640d5` T-401 ~500Hz 非阻塞 RX
- `a8a05c5` 曾恢复稳定 100Hz（其后被 500Hz 方案取代作运动验证基线）

## 安全红线（不变）

低速、急停旁、人工看护；禁止擅自提高动力硬上限或关闭急停；厂家示例与许可证保留。

# 当前交接：2026-11-01 — 临时倒车（监护）

- 分支：feat/patrol-prototype；**仅本地提交，未 push**。
- 用户批准：临时允许倒车；`HARD_MAX_REVERSE_DUTY=0.08`，前进仍 `HARD_MAX_DUTY=0.15`；无后向测距，须现场盯急停。
- 工作台「按住后退」发 duty=-0.08；路线校验仍禁止负 duty（录制/回放不变）。
- 测试：`python -m unittest discover -s tests -v` 须全绿。
- 下一项：部署到车后监护试倒车；再录短路线（T-403）。

# 当前交接：2026-10-31 21:48 CST — T-401 串口环 ~500Hz（待电池）

- 分支：feat/patrol-prototype；**仅本地提交，未 push**。
- T-401：`SerialDriver` 目标 **~500Hz**（`CHASSIS_LOOP_HZ=500`），保持 **timeout=0 非阻塞读** + `write_timeout=0.5` + `exclusive=True`；未再采用会卡写超时的 write-then-blocking-read。
- 安全未改：`HARD_MAX_DUTY=0.07`、禁止倒车、心跳/停车帧逻辑不变。
- 测试：`python -m unittest discover -s tests -v` → **25 passed**（含 mock 串口非阻塞写读与 monitor-only 不写）。
- **真车运动仍未验证**：电池充电/更换中；有电且遥控关闭后做 T-402 低速脉冲（急停旁、你在场）。
- 风险：500Hz 非阻塞在实车上是否再现 Write timeout / rpm=0，只能上车再证；若写超时，勿无限拉长 write_timeout，先抓串口日志再定。

# 当前交接：2026-10-31 工作台路线录制/回放接入

- 分支：feat/patrol-prototype；本地提交（勿 push，除非用户批准）。
- 已实现：路线 dry-run（无硬件可进状态机）、回放样本间隙心跳保持、工作台前进+转向同按、`/routes/record/note`、命名保存。
- 测试：`python -m unittest discover -s tests -v`（须全绿）。
- 今日补齐：`config.json` 的 max_duty 与测试断言已对齐 HARD_MAX_DUTY=0.07（此前仍卡 0.03）。
- 未做：真车运动、推送、架空实测；硬件默认仍关闭。
- 车端验证（只读/无运动）：同步代码后 `sh start_car_workbench.sh`，登录 → 路线面板 dry-run 录/放。
- 下一项：用户在场批准后架空录第一条短路线并回放。

# 当前交接：2026-10-31 原型源码导入

- 分支：feat/patrol-prototype；任务R-008，导入源码、测试与交接；不改main，不自动合并。
- 阅读顺序：README.md → 继续开发交接.md → vendor_review/审阅结论.md → 实际源码。下方原交接模板为历史记录。
- 已验证：车端Ubuntu20.04.6/Noetic/ARM64、D435i、瓶/杯推理、真实事件上传；28条事件上传时队列清空；1条closed任务，Android现场过程仍需原负责人确认。
- 已验证：架空低占空比脉冲及用户反馈；缺控制心跳约0.54秒观察到归零锁定，不等同机械制动时间或程序崩溃停车。
- 已验证：0号前向测距40→20→40厘米纸板响应；实车障碍停车未完成，串口超时阻止使能。
- 阻断：SerialTimeoutException: Write timeout，降100Hz仍失败；不能提高动力或无限写超时绕过。最近车端切回只读，当前实时状态需接手人重新检查。
- 已修：图片路径404、相机重试、退出等待、单实例锁、异常日志与反馈新鲜度。
- 下一项R-003：定位底盘写超时，先静态诊断；任何运动要重新确认现场条件。
- 未完成：连续驾驶/组合转向、全套失联停车、测距异常帧/量程校验、自动路线、5分钟断网补传、三种地面、真实夜间验收及Windows补推理。
- 路线策略：人工固定路线兜底；自主定位/录制/回放限时1.5h，未通过就明确未完成，不以定时动作代替导航。
- 自动测试：python -m unittest discover -s tests -v；依赖/运行/回滚见README。
- 厂家原文件未改；证据、模型、凭据未上传，原负责人私下交接。禁止在GitHub issue中粘贴令牌。

## 原交接模板（已被上方状态取代）

- 更新时间：待填写
- 当前分支及 commit：待填写
- 已验证完成：暂无（尚未检查仓库）
- 已实现但未验证：待填写
- 阻塞/未知：硬件 SDK、ROS 版本、夜间成像方案、网络与 Android 现状
- 下一项任务：R-001
- 测试命令与输出：待填写
- 人工验收结论：待填写
