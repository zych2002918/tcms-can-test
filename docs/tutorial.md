# TCMS-CAN-Test 从零到一：完整学习教程

> 本教程是项目的**唯一主线**：按"协议 → 总线 → 仿真 → 安全逻辑 → 网络 → 证据链"的
> 顺序，把项目从零讲透。读完本教程 + 跑通示例，即具备独立讲解整个项目的能力。
> 配套：`README.md`（项目总览）、`docs/safety_case.md`（安全论证映射）、`docs/` 状态机图。

---

## 第 0 章 项目地图：先看全局

```
┌─────────────────────────────────────────────────────────────────────┐
│                       TCMS-CAN-Test 全景                              │
│                                                                     │
│  协议层      dbc/tcms.dbc（8 个报文 + 信号 + 周期 + 枚举）              │
│     │        tcms/protocol.py（编码/解码封装）                         │
│     ▼                                                                 │
│  总线层      python-can 虚拟总线 ←→ 真实 CAN（环境变量切换）             │
│     │        tcms/bus.py、tcms/canlog.py、tcms/network.py（多网段）    │
│     ▼                                                                 │
│  仿真层      被测对象 DUT：单节点/多节点仿真器 + 故障注入                │
│     │        tcms/simulator.py、tcms/multinode.py                      │
│     ▼                                                                 │
│  安全逻辑层  联锁 → 紧急制动 → EBR 硬线 → 执行反馈 → 状态机             │
│     │        tcms/interlocks.py、ebm.py、ebr.py、exec_feedback.py、    │
│     │        errstate.py、atp.py、watchdogs.py、faultlevel.py          │
│     ▼                                                                 │
│  网络与时间  多网段拓扑、虚拟时间基、故障生命周期、回放链               │
│     │        tcms/network.py、timebase.py、faultlife.py、replay.py     │
│     ▼                                                                 │
│  验证层      pytest 套件（652 用例）+ hypothesis 属性测试              │
│             覆盖率门禁 97% + CI（GitHub Actions）                       │
└─────────────────────────────────────────────────────────────────────┘
```

**核心心智模型**：这不是"一个测试工具"，而是一条**从协议定义到安全证据的完整链路**——
每个模块都在链路上占据一个位置，面试时按这条链路讲，逻辑自洽。

---

## 第 1 章 协议层：列车在"说什么"（dbc + protocol）

### 1.1 DBC 是什么

DBC（CAN Database）是 CAN 报文的"字典"：定义每个报文（帧）的 ID、周期、数据字节里
每个信号的位布局、取值范围、枚举含义。真实列车的控制逻辑就建立在这本字典上。

本项目 `dbc/tcms.dbc` 定义 8 个核心报文（模拟设计，非真实车型协议）：

| 报文 | ID | 周期 | 关键信号 |
|------|-----|------|---------|
| 心跳 TCMS_HEARTBEAT | 0x100 | 100ms | 节点存活标志 |
| 车速 VEHICLE_SPEED | 0x200 | 100ms | SpeedKmh(0.1km/h)、SpeedValid |
| 牵引制动手柄 TRACTION_BRAKE_HANDLE | 0x300 | 50ms | 手柄位置 |
| 车门控制 DOOR_CONTROL | 0x400 | 100ms | Door1~4State(各2bit) |
| 报警事件 ALARM_EVENT | 0x500 | 事件型 | AlarmCode、各报警标志 |
| 受电弓状态 PANTOGRAPH_STATUS | 0x600 | 500ms | 升降状态 |
| 制动系统 BRAKE_SYSTEM | 0x700 | 100ms | BrakeCylinderPressure |
| 能源状态 ENERGY_STATUS | 0x780 | 500ms | SOC |

### 1.2 信号怎么编码（读位布局）

DBC 信号定义形如 `SpeedKmh 0|16@1+ (0.1,0) [0|200] "km/h"`：

- `0|16@1+`：起始位 0、长度 16 位、`@1`=小端、`+`=无符号；
- `(0.1,0)`：缩放因子 0.1、偏移 0 → 原始值 1000 表示 100.0 km/h；
- `[0|200]`：物理值域 0~200 km/h。

`tcms/protocol.py` 用 cantools 封装：`encode("VehicleSpeed", SpeedKmh=100.0)` 自动完成
"物理值 → 位级编码"。

### 1.3 动手：读一个报文

```python
from tcms import protocol
frame = protocol.encode("VehicleSpeed", SpeedKmh=100.0, SpeedValid=1)
print(hex(frame.arbitration_id), frame.data.hex())   # 0x200 ...
```

### 1.4 测试视角（test_protocol.py）

验证 DBC 结构完整性、ID 唯一、周期属性、信号值域、枚举表——协议层是"需求文档"，
测试就是需求验收。

---

## 第 2 章 总线层：报文怎么"跑"（bus + canlog）

### 2.1 虚拟总线 vs 真实总线

python-can 提供 `interface="virtual"` 的环回总线，收发报文的接口与真实 CAN 卡
（PCAN/Vector/socketcan）完全一致。`tcms/bus.py` 把"用什么接口"抽象成环境变量：

```python
from tcms.bus import make_bus
bus = make_bus()                    # 默认 virtual
# 换真实硬件：设环境变量 TCMS_BUS_INTERFACE=socketcan 等，代码零改动
```

**同一套用例、两种执行环境**——这是 HIL（硬件在环）测试的基础设施设计。

### 2.2 CAN 日志（canlog）：真实数据入口

Vector .asc 格式日志 → `parse_asc()` 解析为帧列表 → `AscReplayer` 按时间戳回放。
真实列车日志（脱敏）可以直接喂给回放链做回归。

### 2.3 多网段拓扑（network）：列车不止一条总线

真实列车有牵引/制动/门控等多条总线，经**网关**按报文 ID 过滤互联：

```python
from can import Bus
from tcms.network import BusNetwork

net = BusNetwork({"propulsion": Bus(interface="virtual", channel="p"),
                  "brake": Bus(interface="virtual", channel="b")})
net.add_gateway("gw1", src="propulsion", dst="brake",
                allow_ids=[0x100])        # 只转发心跳
net.send("propulsion", msg)               # 自动按规则转发/丢弃
net.gateway_stats()                       # 转发/丢弃统计（可观测性）
```

**面试点**：网关 = 拓扑上的"门"（按 ID 过滤），不是协议转换器；转发路径可统计、
可审计——对标真实测试台的网络级监控。

---

## 第 3 章 仿真层：被测对象 DUT（simulator + multinode）

### 3.1 单节点仿真器

`TCMSNodeSimulator` 按 DBC 周期自动往总线发报文，可设置车速/手柄/车门状态、
注入丢报、发报警事件。它就是"被测的列车控制单元"。

### 3.2 多节点：一条总线上的多个 ECU

`MultiNodeSimulator` 模拟 VCU（主控）/BCU（制动）/BMS（能源）三个独立节点，
每个节点按自己的报文周期工作；`disable_node()` 模拟断电/通信中断——
**节点失活 → 其报文消失**，这是后续看门狗/丢报检测的故障源。

```python
from tcms.multinode import MultiNodeSimulator
sim = MultiNodeSimulator(bus)
sim.start()
sim.disable_node("bms")          # BMS 失活：能源报文消失
sim.enable_node("bms")           # 恢复
sim.stop()
```

### 3.3 故障注入（faults + fault_injection）

`compute_crc8/flip_bit/corrupt_byte/corrupt_frame` 提供位级篡改能力，
`FaultInjector` 提供结构化注入编排——这是"测故障"的弹药库。

---

## 第 4 章 安全逻辑层：列车怎么"保命"（核心）

这一层是项目的灵魂，也是面试的深水区。按"**检测 → 决策 → 执行 → 反馈**"闭环理解：

### 4.1 联锁（interlocks）：不合法就不动

- 门-车联锁：开门/门故障时移动 = 违规（超速/移动阈值 0.5 km/h）；
- 超速-制动联锁：>160 km/h 触发紧急制动决策；
- 牵引-制动互锁、方向-速度联动、车门-站台联动等。

```python
from tcms.interlocks import door_motion_conflict
bad, reason = door_motion_conflict(door_states, speed_kmh=30.0, speed_valid=True)
```

### 4.2 紧急制动管理（ebm）：决策大脑

对标真实 TCMS"紧急制动原因表"：**模式 × 原因处置矩阵**，SIL2/SIL4 双通道表决。

| 设计点 | 内容 |
|--------|------|
| 8 原因 × 3 模式（FAM/CM/RM） | 超速全模式制动；车门在 RM 豁免（司机人工确认） |
| SIL4（超速/ATP故障/门开） | 双通道**任一触发即制动**（故障安全：宁可错杀） |
| SIL2（ATO故障/火灾） | 双通道**一致才制动**（防误报） |
| 缓解闭环 | 零速(≤0.5km/h)+原因消失 → 手柄回零 → 按钮保持≥3s → IDLE |
| 自愈 | 限 1 次，超限转 FAULT 需人工/远程复位 |

### 4.3 EBR 硬线回路（ebr）：独立于网络的保命线

**得电=缓解、失电=制动**，串联常闭触点（手柄/ATP/紧急按钮）。为什么要有它？
因为 CAN 网络本身可能故障（Bus-Off、断线）——SIL4 执行路径必须独立于通信介质。
双回路 2oo2：任一失电即制动，单断线只预警不损失制动能力。

### 4.4 EB 执行反馈（exec_feedback）：决策 ≠ 执行

EBM 发请求只是决策，必须三重证据确认执行：制动缸压力 ≥300kPa + EB 激活回执 +
牵引切除联锁。任一缺失（2s 超时）判执行层故障；**APPLIED 期间牵引恢复 = 立即故障**
（边制动边牵引是最危险失效）。

### 4.5 CAN 错误状态机（errstate）：物理层健康

对标 ISO 11898-1：TEC/REC 错误计数 → Error-Active/Passive/Bus-Off 三态。
Bus-Off 后 128 次总线空闲恢复、恢复后 8 位发送退避。**接收错误不触发 Bus-Off**——
这条细节能区分"背过标准"和"读过标准"。

### 4.6 ATP 超速监督（atp）：三级干预

警告/SBI/EBI 三级阈值 + 动态 EBI 曲线（对标 ETCS 速度监督）：
距离目标点越近，允许速度线性收窄。

### 4.7 看门狗（watchdogs）：节点"还活着吗"

周期喂狗，连续 3 次丢失判离线，恢复需连续 2 次喂狗——防抖设计。

---

## 第 5 章 网络与时间：让链路"可复现、可追溯"

### 5.1 虚拟时间基（timebase）：确定性

`VirtualClock`：virtual 模式下 `advance()/set()` 确定性推进，替代真实 `time.monotonic`。
**为什么重要**：测试要可复现，可复现要确定性时间。回放链/故障场景/看门狗全部
注入虚拟时钟——这是 HIL 平台的时间一致性基础设施。

### 5.2 故障生命周期台账（faultlife）：故障的"病历"

五阶段闭环：**注入 → 传播 → 告警 → 恢复 → 归档**。

```python
ledger = FaultLedger(clock, recorder)
ledger.open("overspeed", level="major", source="atp", detail="超速 170km/h")
ledger.alert("derate")
ledger.recover(); ledger.close()
ledger.report()    # total/open/closed/by_level
```

每个故障全程写入事件记录器（黑匣子）——**故障从发生到消失全程可审计**。

### 5.3 场景 DSL（faultlife + scenarios）：声明式测试

```python
scenario = FaultScenario("超速降级")
scenario.when("vcu", "overspeed", at=10.0, level="major", impact="速度超限", expect="derate")
scenario.expect_clear("overspeed", at=20.0)
report = ScenarioRunner(ledger, scenario, clock).run()
```

同样场景可以写成 YAML（scenarios/overspeed_derate.yaml），测试/演示人员无需改代码：

```yaml
name: 超速降级
steps:
  - at: 10.0
    inject: {node: vcu, fault: overspeed, level: major, impact: 速度超限, expect: derate}
  - at: 20.0
    recover: overspeed
```

### 5.4 完整回放链（replay）：真实数据驱动回归

`.asc` 日志 → 虚拟时钟 → 联锁/ATP/看门狗/EBM 全链路驱动 → 告警断言。
黑匣子语义闭环：**真实数据回放 + 安全逻辑裁决 = 事故复盘工具**。

---

## 第 6 章 验证层：测试怎么设计（652 用例）

### 6.1 测试金字塔在此项目的形态

| 层次 | 手段 | 例子 |
|------|------|------|
| 单元测试 | 逐模块行为断言 | test_ebm.py（8 原因×3 模式穷举） |
| 集成测试 | 模块协作 | test_replay.py（全链路） |
| 属性测试 | hypothesis 不变量 | 错误计数账目恒等、状态机合法性 |
| 故障测试 | 注入 + 断言 | 短路→全体 Bus-Off→恢复 |

### 6.2 覆盖率哲学

97.94% 是 `pytest-cov` 实测值，CI `--cov-fail-under=97` 门禁。未覆盖的 2.06% 是
刻意保留的防御性分支（QA 文档有逐行说明）。**诚实交代比硬凑 100% 更有说服力**。

### 6.3 跑测试

```bash
pip install -r requirements.txt
python run.py                    # 全量测试 + report.html
pytest tests/ --cov=tcms --cov-report=term-missing
```

---

## 第 7 章 安全论证：从"测试"到"证据"（safety_case.md）

`docs/safety_case.md` 用 EN 50128 思路做安全论证映射：安全需求 SR-01~15 →
实现模块 → 测试证据 → 覆盖率证据。

**核心叙事**：SIL 不是"标上去的"，是**映射出来的**——每条安全需求都有实现、
每个实现都有测试、每个测试都有结果，形成证据链闭环。诚实声明：这是演示级论证，
非真实认证。

---

## 第 8 章 学习路线图（30 分钟 → 3 小时 → 一天）

### 30 分钟：跑通 + 看懂地图

```bash
python demo.py        # 一键全场景演示（纯文本）
python run.py         # 全量测试 + 报告
```

读 README 功能表 + 本文第 0 章地图，知道每个模块在链路中的位置。

### 3 小时：吃透安全逻辑层

按第 4 章顺序读 `interlocks → ebm → ebr → exec_feedback → errstate → atp → watchdogs`，
每个模块读 `tcms/*.py` 头部 docstring + 对应测试文件，跑单个测试文件：

```bash
pytest tests/test_ebm.py -q
```

### 一天：讲出完整故事

1. 能画出全景图（第 0 章）；
2. 能讲 EBM 矩阵 + 双通道表决 + 缓解闭环（面试必问）；
3. 能讲 EBR 为什么独立于 CAN、执行反馈为什么需要三重证据；
4. 能讲错误状态机 ISO 11898-1 细节；
5. 能讲虚拟时间基为什么让测试可复现；
6. 能演示故障场景 DSL（YAML）与回放链。

---

## 附录 A：常见问题

**Q: 为什么不用 CANoe？**
A: CANoe 是成熟工具，但它不展示"我理解协议层在发生什么"。本项目把 CANoe 的核心能力
（统计、Trace、错误统计、负载率）逐一对标实现，每一步都有物理/协议依据——面试要证明
的是"知道工具背后在算什么"。

**Q: 这是真实列车协议吗？**
A: 不是。报文协议为模拟设计（`README` 说明），红线是**不还原真实车型协议（涉密）**。
但安全逻辑（联锁/EBM/EBR/错误状态机）对标真实列控系统设计。

**Q: 覆盖率为什么不是 100%？**
A: 97.94% 实测值 + 门禁。剩余为刻意保留的防御分支，QA 文档逐行说明。

**Q: 怎么接真实硬件？**
A: 环境变量切换接口（`TCMS_BUS_INTERFACE` 等），代码零改动；`hardware` marker
隔离真实硬件用例，CI 自动跳过。

---

*教程结束。现在你可以从头到尾讲一遍这个项目了。*
