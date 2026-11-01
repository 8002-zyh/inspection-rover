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
