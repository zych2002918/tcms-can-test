# Changelog

本项目遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。
所有重要变更记录于此；格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

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
