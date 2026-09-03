# Changelog

本项目遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。
所有重要变更记录于此；格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## [1.9.0] - 2026-09-03

### 新增（平台化：可分发 × 公共契约 × 单源收敛）
- **包公共 API 面**：`tcms/__init__.py` 顶层导出 `__version__` /
  `load_database` / `load_fault_dictionary` / `make_bus` /
  `scenarios.run_yaml`（此前为空文件，`import tcms` 无任何可用入口）
- **CLI 收编为包内入口** `tcms/cli.py`：run.py 薄壳委托 + console script
  `tcms-test` 指向同一实现（此前指向仓库根 run.py，wheel 分发后必然
  ModuleNotFoundError）；README/CI/安装态命令现为单一真源
- **`tcms-test --doctor` / `python run.py --doctor` 环境自检**：
  依赖版本 / 包版本一致性 / DBC+FMEA 数据资产 / virtual 总线 / HIL 硬件状态
  / 场景目录 → PASS/FAIL 表（复用 python-can 探测；无硬件时显式 FAIL 并
  指引 TCMS_BUS_* 接入——Roadmap HIL 的探测工具就绪化）
- **版本单一真源**：`tcms/_version.py` + pyproject `dynamic version`
  （消除 pyproject/run.py 双写漂移）；`tests/test_metadata.py` 元测试
  钉死版本/打包数据/公共 API 契约
- **DBC 收编入包**：`dbc/tcms.dbc` → `tcms/tcms.dbc`，`protocol.py` 改
  `importlib.resources` 寻址（wheel/zip 安装均可加载，外部 DBC 仍可传路径）
- **分发自检** `scripts/check_dist.py` + CI `dist-smoke` job：wheel 安装于
  干净 venv 后从仓库外实证 `import tcms` + 数据资产 + 入口（堵住历史
  editable-only 盲区）
- **性能基准** `scripts/benchmark.py`：回放吞吐（frames/s）/ WCRT 整集分析
  （200 报文 ms）/ 总线负载滑动窗口（ms）三项机器产物，`--json` 落盘；
  CI demo-smoke 每轮生成 `reports/benchmark.json`（Roadmap"性能可追踪"勾选）
- **架构手册** `docs/ARCHITECTURE.md`：分层依赖方向 / 证据链数据流 /
  扩展点食谱（新报文/故障键/场景/HIL/接入方）/ 契约约定表
- 测试分层新增：`tests/test_cli.py`（13）+ `tests/test_diagnose.py`（13）
  + `tests/test_metadata.py`（8）+ `tests/test_benchmark.py`（4），覆盖 CLI
  各分支、doctor 防御路径与基准脚本可运行性

### 变更
- 用例数 738 → **776**（+38：cli 13 / diagnose 13 / metadata 8 / benchmark 4；
  775 passed + 1 hardware skipped），覆盖率 97.82% → **97.96%**
  （2602 语句 / 53 未覆盖），测试文件 43 → 44
- 覆盖率门禁单源：CI 移除 `--cov-fail-under=97`（只留 pyproject
  `[tool.coverage.report] fail_under=97`，消除阈值双源）
- `requirements.txt` 继续 `-e .[test,viz,lint]`；ruff 全仓干净
- 版本入口统一：`run.py --version` 与 `tcms-test --version` 均输出 1.9.0

## [1.8.0] - 2026-09-02

### 新增
- `scenarios/` 扩充 8 → **13 个场景**：新增 场景9-13（总线噪声+仲裁错误+短帧 /
  VCU 心跳丢失+牵引丢失级联 / 制动卡滞+受电弓拉弧 / 牵引制动冲突 / SOC+温度+门噪声），
  22 条 FMEA 故障键全部被场景消费（注入/恢复/断言三件套覆盖字典全键）
- **Allure 结果 CI 化**：全量回归 `--alluredir` 产物按 Python 版本上传 artifact
  （下载后 `allure serve` 看板化）
- 场景头部注释 F-TCMS 编号与 `tcms/faults.yaml` 逐条对齐（消除引用错位）

### 变更
- 用例数 728 → **738**（+10：场景注册表 5 新 YAML × 2 参数化；737 passed + 1 skipped）
- 场景注册表测试 18 → 28 用例（13 YAML × 2 参数化 + 2 守卫）
- Roadmap 勾选：场景库扩充 / Allure CI / Python 3.13 / JUnit 趋势接入 Pages
  （前述 CI/Pages 能力在 v1.7.0 已落地，本版补全收尾）
- **RTM 追溯补齐 SR-16~18**：`tests/rtm.csv` + `tests/test_rtm.py` 原只覆盖 SR-01~15，
  与 `docs/safety_case.md` 定义的 18 条对齐（补 6 行：FMEA 字典/追溯自证/失败导出与分层）
- **README 精简**：504 → 148 行（详情迁至新 `docs/features.md` + `docs/test_cases.md`，
  消除"后续规划"与 Roadmap 重叠；ASCII 图改英文短标签防错位；数字同步 738/13 场景/SR-01~18）

## [1.7.0] - 2026-09-02

### 新增
- **FMEA 字典 → 场景引擎闭环**：`ScenarioRunner` 处置动作回退到统一故障字典
  （`faultdb`），`tcms/faults.yaml` 全部 22 条故障键现可被场景 YAML 消费
  （此前仅 faultlevel 10 键可用，扩展键注入即抛错）
- `scenarios/` 扩充至 **8 个场景**：新增 CRC 错误风暴 / 总线短路-断路级联 /
  节点重启风暴 / 传感器卡死+漂移叠加 / 滚动计数跳变（覆盖字典扩展故障键）
- **README 徽章自证**：`scripts/gen_badges.py` 从 JUnit + coverage.json 机器产物
  生成 tests/coverage 徽章并就地改写 README（保留元数据徽章；消除手抄漂移）；
  CI main 分支自动刷新并 bot 提交（`[skip ci]` 防递归）
- **Pages 实时报告**：`docs/reports/` 随 CI 生成 `latest.json`（tests/coverage/
  python 版本）+ TREND.md + report.html，文档站统计数字由 JSON 动态驱动
- CI test 矩阵扩至 **Python 3.10/3.11/3.12/3.13**；GitHub Actions 版本全家桶
  升级（checkout@v7 / setup-python@v7 / upload-artifact@v7 / configure-pages@v6 /
  action-gh-release@v3），dependabot 待开 PR 全部消除
- `tests/test_badges.py`（8 用例）+ 场景库规模守卫（≥5）

### 变更
- 用例数 707 → **726**（+19：badges 8、场景注册表 +11、守卫），测试文件 37 → 40
- 覆盖率 97.81% → **97.73%**（2426 语句 / 55 未覆盖，门禁 97% 达成）
- smoke 层 67 → 68 用例（实测收集）
- JUnit 产物版本化命名（`reports/junit-py<ver>.xml`），支持多版本趋势聚合

## [1.6.0] - 2026-09-02

### 新增（测试工程师工作流完整化）
- `tcms/faultdb.py` + `tcms/faults.yaml`：**统一故障字典（FMEA）**——22 条 F-TCMS
  条目（fid/key/子系统/层级/级别/处置/SIL/检测/注入/恢复/描述），查询 API 与
  faultlevel 分级模型**对齐校验**（防双源漂移）
- `tests/rtm.csv` + `tests/test_rtm.py`：**需求追溯矩阵**（SR-01~18 → 模块 →
  测试文件双向追溯，元测试锁定完整性）；`docs/test_plan.md` 测试计划
- 测试分层：`smoke`（67 用例 ~1s）/`safety`（70）marker + `run.py --level` +
  CI `pr-smoke` 快速门禁 job
- **失败现场自动导出**：conftest `crash_site` fixture + hook →
  `reports/failures/<用例>/`（summary + recorder JSON/CSV）
- `tcms/reporting.py` + `scripts/report_history.py`：**JUnit 趋势报表**
  （Markdown/ASCII，CI 每轮落盘）
- `examples/`：`demo_trip.asc`（146 帧真实格式日志）+ `replay_demo.py`
  （5 步剧情断言）+ `make_demo_asc.py` + README；`demo.py` 全场景 **25 项自证断言**
- CI 重构：`pr-smoke`（smoke 先行）→ `lint`（含 ruff format）→ `test` 矩阵
  （3.10/3.11/3.12，JUnit + HTML artifact）→ `demo-smoke`（demo/示例/趋势）
- `.github/dependabot.yml`（pip + GitHub Actions 每周）

### 变更
- **版本口径统一**：pyproject 1.4.0 → **1.6.0**（此前 CHANGELOG 超前于 pyproject）
- 用例数 658 → **707**（+49：faultdb 20、RTM 6、场景注册表 7、reporting 11、
  examples 2、失败导出 2、补充），覆盖率 97.98% → **97.81%**
  （2417 语句 / 53 未覆盖，门禁 97% 达成），测试文件 33 → 37
- 术语统一：文档中"行覆盖率"→"语句覆盖率"（pytest-cov 实测口径）
- `run.py --replay` 改用完整回放链（`tcms.replay.ReplayChain`）替代简化判定
- CONTRIBUTING 引用本地化（移除仓库外 QA 文档链接）
- requirements.txt 单源化（`-e .[test,viz,lint]`）

## [1.5.1] - 2026-02

### 变更
- `tcms/network.py` 网关模型**现实化**：同步透传 → 异步缓冲转发（`send` 只投递到
  网关接收缓冲，时钟推进 + `step()` 泵出到期帧；转发时延 `latency`、缓冲容量
  `capacity`、溢出丢弃新帧、足迹 `trace` 防环、级联逐网关扩散——全部可观测、
  可审计），`BusNetwork` 接受 `clock` 参数（默认 `timebase.global_clock()`）
- `test_network.py` 24 → **30** 用例（新增：异步不可见直至 step、溢出丢弃计数、
  缓冲占用、级联双拍时延、足迹防环双向网关、负时延/零容量拒绝），`network.py`
  保持 100% 行覆盖

## [1.5.0] - 2026-02

### 新增
- `tcms/scenarios.py`：场景 YAML 外部化（`scenarios/*.yaml` 声明式故障场景，场景与代码分离）
- `tcms/network.py`：多网段拓扑（`BusNetwork` 命名网段 + `Gateway` 异步缓冲网关——接收 FIFO/转发时延/溢出丢弃/ID 过滤/足迹防环 + 级联扩散 + 转发统计/审计日志）
- `docs/tutorial.md`：从零到一完整教学教程（协议→总线→仿真→安全逻辑→网络→证据链）
- 依赖：`pyyaml>=6.0`（scenarios YAML 解析）

### 变更
- 用例数 612 → 652（+40：scenarios 17、network 24、测试文件 31 → 33），覆盖率 97.76% → **97.94%**（2186 语句 / 45 未覆盖，CI 门禁 `--cov-fail-under=97` 达成）
- `tcms/network.py` 为 100% 行覆盖（24 用例含防御分支：防环/发送失败容错/阻塞轮询）

## [1.4.0] - 2026-02

### 新增
- `tcms/bypass.py`：隔离/旁路开关状态机（旁路安全前提 + 审计日志 + 隔离组降级兜底）
- `tcms/canlog.py`：CAN 日志解析与回放（Vector .asc 格式，真实数据驱动验证）
- `run.py --replay`：真实 CAN 日志回放入口
- `tcms/voting.py`：2oo3→2oo2 容错降级路径（单通道故障自动降级 + 降级事件计数）
- `tcms/recorder.py`：事故冻结窗口（EB 触发前后快照，黑匣子语义）
- `tcms/nmt.py`：NMT 主站命令（CiA 301：Start/Stop/Pre-op/Reset）
- `tests/test_fault_chain.py`：端到端故障链（高负载→WCRT 超限→丢帧→看门狗→EB）
- `tcms/replay.py`：完整回放链（.asc → 虚拟时钟 → 联锁/ATP/看门狗/EBM → 告警断言）
- `tcms/timebase.py`：虚拟时间基（`VirtualClock`，确定性推进，全局统一时间源）
- `tcms/faultlife.py`：故障生命周期台账（注入→传播→告警→恢复→归档）+ 场景 DSL
- `docs/safety_case.md`：EN 50128 思路安全论证映射表（SR → 实现 → 测试证据）
- 可视化扩展：`state_door.png`（门控状态机）、`state_overspeed.png`（超速防护状态机）
- 开源成熟度：`SECURITY.md`、`CODEOWNERS`
- 工程化：`pyproject.toml` 标准化、开源三件套（ISSUE/PR 模板、CONTRIBUTING、CHANGELOG）

### 变更
- 用例数 562 → 612，覆盖率保持 97.66%（CI 门禁 `--cov-fail-under=97` 达成）

## [1.3.0] - 2026-01

### 新增
- `tcms/busfault.py`：总线级故障注入（短路/断路→集体 Bus-Off→恢复）
- `tcms/jitter.py`：周期抖动/漂移统计（ppm）
- `tcms/seqcheck.py`：报文序列/时序违规检测（丢帧/重复帧/乱序帧/迟到）
- `tcms/faultlevel.py`：故障分级模型（四级映射处置）+ 故障注入编排器
- `tcms/atp.py`：超速监督分层 + 动态 EBI 曲线（Warning/SBI/EBI）
- `tcms/nmt.py`：CANopen NMT 心跳层（CiA 301）
- `tcms/voting.py`：2oo3 速度表决
- `tcms/interlocks.py`：牵引-制动互锁 / 方向-速度联动 / 车门-站台联动

### 变更
- 用例数 366 → 507，覆盖率 97.49% → 98.10%
- CI 增加 lint（ruff）与 demo-smoke job

## [1.2.0] - 2025-12

### 新增
- `tcms/ebr.py`：EBR 硬线回路（得电缓解/失电制动 fail-safe + 断点诊断）
- `tcms/exec_feedback.py`：EB 执行反馈闭环（压力+回执+牵引切除三重证据）
- `tcms/busload.py`：总线负载率统计与压测（位级帧模型）
- `tcms/schedulability.py`：WCRT 可调度性分析（Tindell 迭代）+ ID 分配审计
- `tcms/bus.py`：硬件接口抽象层（TCMS_BUS_INTERFACE 环境变量）
- EBM 司机缓解操作序列（手柄回零 + 缓解按钮保持）

## [1.1.0] - 2025-11

### 新增
- `tcms/errstate.py`：CAN 错误状态机（ISO 11898-1：TEC/REC、Error-Active/Passive/Bus-Off）
- `tcms/recorder.py`：事件时序记录器（环形缓冲 + 过滤查询 + JSON/CSV 导出）
- `scripts/plot_timeline.py`：时序甘特图可视化
- hypothesis 属性测试套件

## [1.0.0] - 2025-10

### 新增
- `tcms/ebm.py`：紧急制动管理（模式×原因矩阵 + 缓解/复位闭环 + SIL2/SIL4 双通道表决）
- `tcms/interlocks.py`：安全联锁
- `tcms/watchdogs.py`：节点心跳看门狗
- 多节点 CAN 仿真器 + DBC 报文编解码 + CRC 校验
- demo.py 演示入口

### 首个里程碑
- 179 用例 / 97% 覆盖率，CI 全绿
