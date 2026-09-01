# TCMS-CAN-Test 安全论证映射表（Safety Case）

> 对标 EN 50128（铁路应用——通信、信号和处理系统的软件）的**软件安全论证**思路，
> 把"安全需求 → 设计实现 → 测试证据 → 覆盖率"串成一条可追溯的证据链。
> 本文件解决面试中"你的 SIL 是怎么来的"——不是拍脑袋写的 SIL 等级，
> 而是从**需求 → 实现 → 证据**全链路映射出来的。

---

## 0. 一句话定位

| 项 | 内容 |
|---|---|
| 项目 | TCMS-CAN-Test：列车控制与管理系统 CAN 总线仿真与安全逻辑验证 |
| 证据基线 | 652 用例（pytest collect）· 97.94% 行覆盖率（2186 stmts / 45 miss）· CI 全绿 |
| 论证方法 | 软件功能安全（EN 50128 / IEC 61508 思想）的需求-实现-证据三层映射 |
| 覆盖范围 | 紧急制动、联锁、超速防护（ATP）、看门狗、错误状态机、可调度性、回放链 |

> 说明：本项目是**教学/演示级**安全逻辑仿真，SIL 等级用于**论证方法演示**，
> 不代表真实车载系统已通过第三方认证。真实认证需 SIL 完整开发流程
> （需求管理/独立验证/工具鉴定等），本表映射的是其**可复现的技术内核**。

---

## 1. 安全需求目录（SR——Safety Requirement）

| ID | 安全需求 | 来源/对标 | SIL 关联 |
|---|---|---|---|
| SR-01 | 任一 SIL4 紧急制动原因触发时必须制动（故障安全：宁可错杀） | EBM 模式×原因矩阵 | SIL4 |
| SR-02 | SIL2 紧急制动原因必须双通道一致才制动（防误报） | EBM 通道表决 | SIL2 |
| SR-03 | 紧急制动后必须满足"零速 + 原因消失 + 有效速度信号"才可缓解 | EBM 缓解闭环 | SIL4 |
| SR-04 | 列车移动时车门打开/故障即违规（故障门按未关处理） | 门-车联锁 | SIL4 |
| SR-05 | 超速达到 EBI 阈值必须触发紧急制动干预 | ATP 三级监督 | SIL4 |
| SR-06 | 超速达到 SBI 阈值必须触发常用制动干预（先于 EBI） | ATP 三级监督 | SIL3 |
| SR-07 | 节点心跳丢失超过 N 周期必须判为离线/故障 | 看门狗/心跳监督 | SIL3 |
| SR-08 | CAN 总线错误计数超限必须进入 Bus-Off 并退避 | ISO 11898-1 错误状态机 | SIL2 |
| SR-09 | 周期报文必须满足可调度性（WCRT ≤ 截止期） | Tindell WCRT 分析 | SIL2 |
| SR-10 | 紧急制动事件必须被记录并可冻结窗口（黑匣子） | 事件记录器 | SIL2 |
| SR-11 | 故障必须经历"注入→传播→告警→恢复→归档"全生命周期留痕 | 故障生命周期台账 | SIL2 |
| SR-12 | 真实 CAN 日志回放必须驱动业务逻辑产生一致的响应 | 完整回放链 | SIL3 |
| SR-13 | 运行中禁止自动解除紧急制动（自愈限 1 次，超限转 FAULT） | EBM 自愈策略 | SIL4 |
| SR-14 | 牵引与制动不得同时施加（互锁） | 牵引-制动联锁 | SIL4 |
| SR-15 | 时间一致性：全部模块共享统一时间源（虚拟时间基） | 仿真基础设施 | SIL2 |

---

## 2. 需求 → 实现映射（SR → 模块 → 关键设计）

| SR | 实现模块 | 关键设计点（面试讲） |
|---|---|---|
| SR-01/03/13 | `tcms/ebm.py` | 模式×原因矩阵；SIL4 任一触发即制动；缓解需零速+有效速度；自愈限 1 次 |
| SR-02 | `tcms/ebm.py` | `channel_vote()`：SIL2 双通道一致才制动，不一致累计 `vote_mismatches` |
| SR-04 | `tcms/interlocks.py` | `door_motion_conflict()`：移动+开门/门故障 → 违规，显式返回原因 |
| SR-05/06 | `tcms/atp.py` | Warning < SBI < EBI 三级阈值；`DynamicEbiCurve` 目标点限速模型 |
| SR-07 | `tcms/watchdogs.py` / `tcms/nmt.py` | 连续 N 周期丢失判 Fault，恢复需连续 M 次心跳；CANopen 心跳带状态语义 |
| SR-08 | `tcms/errstate.py` | TEC/REC 计数、Bus-Off 退避（ISO 11898-1） |
| SR-09 | `tcms/schedulability.py` / `tcms/busload.py` | Tindell WCRT 分析 + 位级帧模型负载率 |
| SR-10 | `tcms/recorder.py` | 环形缓冲 + 保护事件驻留 + `freeze_snapshot()` 事故冻结窗口 |
| SR-11 | `tcms/faultlife.py` | `FaultLedger` 五阶段台账（注入→传播→告警→恢复→归档），与 recorder 打通 |
| SR-12 | `tcms/replay.py` | `ReplayChain`：.asc → 虚拟时钟 → 联锁/ATP/看门狗/EBM → 告警断言 |
| SR-14 | `tcms/interlocks.py` | `traction_brake_conflict()`：牵引请求 + 制动请求 → 冲突 |
| SR-15 | `tcms/timebase.py` | `VirtualClock` 统一时间源，`advance()/set()` 确定性推进 |

---

## 3. 实现 → 测试证据映射（模块 → 测试文件 → 用例数）

> 用例数为 `pytest --collect-only` 实测（2026-02 基线，652 用例）。

| 模块 | 测试文件 | 用例数 | 覆盖的关键安全行为 |
|---|---|---|---|
| ebm.py | test_ebm.py | 37 | 模式×原因矩阵、缓解/复位闭环、司机缓解序列、通道表决 |
| recorder.py | test_recorder.py | 42 | 环形缓冲、保护事件、冻结窗口、导出、EBM 快照 |
| interlocks.py | test_interlocks.py | 12 | 门-车联锁、超速判定、牵引制动互锁、方向-速度联动 |
| atp.py | test_atp.py | 11 | 三级监督、动态 EBI 曲线、制动点计算 |
| errstate.py | test_errstate.py | 27 | TEC/REC 迁移、Bus-Off 退避 |
| watchdogs.py | test_watchdogs.py | 11 | 心跳丢失判 Fault、恢复阈值、与仿真器集成 |
| nmt.py | test_nmt.py | 21 | 心跳生产者/消费者、NMT 主站命令、状态迁移 |
| voting.py | test_voting.py | 16 | 2oo3→2oo2 降级、单通道故障诊断 |
| bypass.py | test_bypass.py | 18 | 隔离开关、强制 RM、审计日志 |
| ebr.py | test_ebr.py | 19 | 硬线回路失电制动、断线诊断 |
| exec_feedback.py | test_exec_feedback.py | 22 | 压力+回执+牵引切除三重证据 |
| faultlevel.py | test_faultlevel.py | 9 | 四级分级、处置映射、注入编排 |
| **faultlife.py** | **test_faultlife.py** | **20** | **五阶段台账、多故障审计、场景 DSL 断言** |
| **scenarios.py** | **test_scenarios.py** | **17** | **YAML 场景加载/执行、显式/事件式语法、错误处理** |
| **network.py** | **test_network.py** | **24** | **多网段拓扑、网关 ID 过滤、级联转发防环、审计日志** |
| **replay.py** | **test_replay.py** | **12** | **回放链、超速/开门触发 EBM、看门狗离线告警** |
| **timebase.py** | **test_timebase.py** | **17** | **虚拟时钟推进/跳变、全局替换** |
| schedulability.py | test_schedulability.py | 17 | WCRT 分析、ID 审计 |
| busload.py | test_busload.py | 19 | 位级帧模型负载率 |
| seqcheck.py | test_seqcheck.py | 12 | 丢/重/乱/迟检测 |
| jitter.py | test_jitter.py | 12 | ppm 漂移 |
| busfault.py | test_busfault.py | 11 | 短路断路集体 Bus-Off |
| multinode.py | test_multinode.py | 6 | 多节点失活恢复 |
| simulator.py | test_simulator.py | 15 | DBC 周期发送、状态注入 |
| protocol.py | test_protocol.py | 13 | 报文常量、编码 |
| parser.py | test_fault_injection.py | 15 | 采集/统计/丢报、错误注入 |
| faults.py | test_faults.py | 11 | CRC-8、位翻转 |
| canlog.py | test_canlog.py | 11 | .asc 解析、回放、统计 |
| lifecycle.py | test_lifecycle.py | 7 | 生命周期 |
| properties.py | test_properties.py | 31 | 属性测试（不变量） |
| fuzz.py | test_fuzz.py | 5 | 模糊测试 |
| bus.py | test_bus.py | 8 | 硬件接口抽象（1 hardware skip） |
| fault_chain | test_fault_chain.py | 6 | 端到端故障链（burst → WCRT → 看门狗 → EBM） |

---

## 4. 覆盖率证据（pytest-cov 实测）

| 指标 | 值 |
|---|---|
| TOTAL 语句 | 2186 |
| 未覆盖 | 45 |
| 行覆盖率 | **97.94%** |
| CI 门禁 | `--cov-fail-under=97`（覆盖率低于 97% CI 即失败） |
| 全绿基线 | 652 用例 · CI run 全绿（5 job） |

---

## 5. 证据链闭环示意（面试一页讲法）

```
安全需求 (SR-01~SR-15)
    │  需求驱动
    ▼
设计实现 (ebm/atp/interlocks/watchdogs/recorder/faultlife/replay/timebase)
    │  每模块配专项测试
    ▼
测试证据 (33 测试文件 / 652 用例)
    │  pytest-cov 度量
    ▼
覆盖率门禁 (97.94% > 97% 门槛)
    │  CI 三 job（test 3.10/3.11/3.12 + lint + demo-smoke）
    ▼
可追溯报告 (本表 + 事件记录器导出 + 回放链报告 + 故障台账)
```

**面试叙事**："我的 SIL 不是标上去的，是映射出来的——每条安全需求（SR）
都有实现模块、有专项测试、有覆盖率证据，最后 CI 门禁保证任何一次
回归都过不了 97% 的门槛。这就是 EN 50128 证据链的技术内核。"

---

## 6. 局限与说明（诚实性加分项）

1. **SIL 等级为论证演示**：真实 SIL 认证需要完整生命周期（独立安全评审、
   工具鉴定、需求变更管理等），本项目聚焦**可复现的技术内核**。
2. **覆盖率为行覆盖**：行覆盖 ≠ 分支/MC/DC 覆盖（EN 50128 对 SIL3/4 要求
   更强的结构覆盖）。本项目以行覆盖 + 属性测试 + 模糊测试补充。
3. **硬件层留白**：真实 CAN 硬件联调（PCAN/周立功）为 `@pytest.mark.hardware`
   标记用例，CI 跳过——接入硬件后证据链补上物理层环节。
4. **时间基**：虚拟时间基解决仿真确定性，但真实时钟的漂移/抖动行为
   需要硬件在环才能完整验证。
