# 安卓巡检 APP 0.1.1

这是原生 Android 外壳 + 车端工作台的可安装原型，Android 8.0 及以上可安装。不是离线导航系统。

## 使用

1. 手机、小车连接同一热点，打开“巡检工作台”APP。
2. 输入当前小车 IP，例如 `10.212.93.243:8765`，点“连接工作台”。支持修改热点后的新地址，不把某个网段写死为连接目标。
3. 使用原网页操作员账号登录。APP只保存地址；会话由应用私有 WebView Cookie 保存，不在源码内置密码、设备令牌或云API密钥。
4. 在现场巡检页看画面、确认检查点、控车和录放。顶部原生红色“停止”在各页面保留；软件停止不是实体急停。
5. 处理任务：接单 → 系统照片选择器选择 JPEG/PNG/WebP 普通照片（单张≤10MB，后端也会校验）→ 填说明 → 提交 → 待复核。第一版不接管手机实时相机，先用系统相机拍摄后选择照片。
6. 修改地址或退出登录：点原生顶部“地址”。退出仅清除本APP的登录Cookie，不删除车端事件和任务。

APP切后台、选照片或离开页面会请求停止；后台暂停 WebView 定时器，车端原心跳保护仍在。返回前先清空旧控制会话，不自动使能或恢复路线。界面异常时重新连接。此行为已验证停车状态下的回前台流程，行驶中实测制动时间仍待现场验证。

当前使用热点 HTTP，不做公网部署；只允许用户输入的局域网IPv4同源网页/资源，不打开第三方页面，不提供JavaScript-to-Java桥，不跳过HTTPS证书错误。不修改ROS、底盘协议或运动限幅。

## 0.1.1 更新

路线选择后可“删除所选路线”，在“路线回收站”恢复；管理路线前先停止控制与录放。异常卡片支持删除，在“回收站”恢复，关联任务与图片保留。删除有二次确认，不物理清空证据。图标为蓝底小车与绿叶，支持自适应与主题图标。

## APK 与安装

交付文件放 Windows 项目根目录的 `runtime/delivery-20261102-android/`，含APK、SHA256和构建报告。源码不跟踪APK/签名密钥。手机USB已安装并验证过；最新包与手机已安装包SHA256一致。

若手工更新：在手机文件管理打开 `Download/inspection-rover-0.1.1-debug.apk`，按系统提示更新。使用本机标准Android调试签名；这是测试版，不是应用商店发行版。

卸载：手机应用设置 → 巡检工作台 → 卸载。只删除APP本地地址和会话，车端数据保留。

## Windows 构建

操作位置：仓库根目录 `tmp/ir-push`。

已固定 AGP 9.2.1、Gradle 9.4.1、compileSdk 36.1、targetSdk 35、minSdk 26，JDK 17及以上。Android Studio可打开 `android/` 项目；当前Codex宿主中Gradle启动报 `Unable to establish loopback connection`，没有把Gradle/Lint标为通过。

当前已验证的替代构建，使用官方SDK的aapt2、javac、d8、zipalign、apksigner：

```powershell
& 'C:\Users\Administrator\Documents\ChatGPT\巡检小车\.venv\Scripts\python.exe' scripts/build_android_direct.py
node tests/test_android_lifecycle.cjs
```

预期：APK签名v2/v3验证与zipalign通过，输出 `android/app/build/direct/inspection-rover-0.1.0-debug.apk` 和 `build-report.json`。

构建脚本要求已安装JDK、SDK平台 `android-36.1`、build-tools `36.0.0` 和本机 `.android/debug.keystore`；不下载或修改JDK。Windows SDK对中文路径不稳定，因此仅把本APP源码暂存到 `%LOCALAPPDATA%/InspectionRover/build-cache/` 的唯一目录。缓存不包含设备凭据，不改宿主机网络设置。

Java地址测试在本机缓存的JUnit4.13.2/Hamcrest1.3下执行，3项通过；正常Gradle环境可运行 `gradle -p android testDebugUnitTest`。设备连接可用 `adb devices -l` 检查。不要在车辆使能或路线执行期间覆盖安装APP。

## 验证记录（2026-11-02）

- Vivo V2301A USB安装、启动与登录通过，实时画面和原生地址栏显示正确。
- `OriginPolicyTest` 3项通过：地址规范化，拒绝公网/凭据/错误端口，同源资源与blob画面限制。
- 原生注入生命周期JS测试通过：清除人工/路线会话，未登录不发停车请求，异常页面状态返回false供原生重新加载。
- 用户完成“APP 上传测试（软件测试）”：接单、系统选图、说明“APP上传测试”、提交到review；服务器图片HTTP200，685447字节，图像格式验证通过。Home返回APP正常。
- 软件测试事件 `app-upload-test-20261102-01`、任务 `84a7b131b653463a81ae839c7be40875`，仍待复核；不计入真实夜巡异常成果。
- 用户反馈夜间现场测试正常；尚未接收并审阅录像，三种地面/定位和动态刹停验收不能据此补成通过。
- 根目录私密证据：`runtime/evidence/android-upload-test-20261102.json`、APP截图。不要提交私人照片/截图、设备序列号与密钥。
- 未验证：低版本安卓、超大字号/横屏、行驶中切后台实测停止时间、长时间掉网及完整Gradle/Lint。

## 视觉规则来源

采用 [apple-ui-designer](https://github.com/heyman333/atelier-ui/blob/main/skills/apple-ui-designer/SKILL.md) 做视觉参考，用 [apple-design-skill](https://github.com/dickwu/apple-design-skill/blob/main/SKILL.md) 的可访问性/布局/颜色/字号/按钮/导航原则审查。字体为Android系统字体；APP专用CSS和原生代码自行编写，网页本身保留上一轮主题。

Atelier README标注MIT，未找到独立LICENSE文件；apple-design-skill README说明规范文字归Apple、其余按现状提供。没有把第三方SKILL或HIG全文复制进仓库。
