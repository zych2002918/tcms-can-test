# TCMS-CAN-Test — 列车网络控制（TCMS）CAN 报文自动化测试框架

[![CI](https://github.com/zych2002918/tcms-can-test/actions/workflows/ci.yml/badge.svg)](https://github.com/zych2002918/tcms-can-test/actions)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue)](#)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](#)
[![tests: 80](https://img.shields.io/badge/tests-80%20passed-brightgreen)](#)

针对轨道交通列车网络控制系统（TCMS / 列车控制管理系统）的 CAN 总线报文自动化测试框架。

通过**虚拟 CAN 总线 + DBC 协议数据库 + 报文仿真器（被测对象 DUT）**，对列车控制报文的
**周期、ID 合法性、信号值域、边界值、枚举、事件联动、丢报检测、安全联锁逻辑**进行
自动化验证，输出结构化测试报告。无硬件依赖，可本地运行，可接入 CI。

```
┌─────────────────────┐  发送  ┌──────────────────┐  采集/断言   ┌─────────────────┐
│  TCMSNodeSimulator   │ ─────▶ │ 虚拟 CAN 总线       │ ───────────▶ │ pytest 测试套件    │
│  MultiNodeSimulator  │        │ (python-can virtual)│             │  80 个用例        │
│  （被测系统 DUT）    │        └──────────────────┘             └─────────────────┘
└─────────────────────┘          故障注入：节点失活 / 停止发送 / 越界 / 抖动 / 事件
```

## 功能特性

| 模块 | 说明 |
|------|------|
| `dbc/tcms.dbc` | 列车控制网络协议数据库：8 个报文（心跳/车速/牵引制动/车门/报警/受电弓/制动/能源），含周期属性与枚举值表 |
| `tcms/simulator.py` | 单节点 TCMS 仿真器：按 DBC 周期（50/100/500ms）自动发送周期报文，支持事件报文与故障注入 |
| `tcms/multinode.py` | **多节点总线仿真**：VCU（主控）/BCU（制动）/BMS（能源）独立节点，支持节点级失活与恢复（断电/通信中断场景） |
| `tcms/interlocks.py` | 列车安全联锁逻辑（测试视角规则）：门-车联锁、超速-制动联锁、受电弓异常、能源联锁 |
| `tcms/parser.py` | 报文采集与解码辅助：周期统计、丢报检测 |
| `tests/` | **80 个自动化用例**，覆盖五层：协议静态验证、仿真器行为、故障注入与边界值、安全联锁逻辑、多节点总线 |

## 快速开始

```bash
python -m venv .venv
.venv/Scripts/activate            # Windows；Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python run.py                     # 运行全部测试 + 生成 report.html
```

一键入口：

```bash
python run.py                     # 全部测试 + HTML 报告
python run.py --allure            # 额外生成 Allure 结果
python run.py -k door             # 按关键字筛选用例
python run.py --no-report         # 只跑测试
```

生成 Allure 报告（需安装 [allure 命令行](https://allurereport.org/docs/install/)）：

```bash
pytest tests/ --alluredir=allure-results
allure serve allure-results
```

## 测试用例设计（80 个）

**协议静态验证（`test_protocol.py`）**：DBC 结构完整性、报文 ID 唯一性与标准帧约束、
DLC、周期属性（50/100/500ms）、报警事件型配置、信号物理值域（车速 0-200km/h、
SOC 0-100%、温度 -40~120℃）、枚举值表、节点表。

**仿真器行为（`test_simulator.py`）**：7 个周期报文在总线上齐发、心跳/手柄周期实测、
心跳计数器单调递增、车速设置-解码往返一致、牵引/制动联动逻辑、车门状态与
AllDoorsClosed/开门许可联动、报警事件触发与解码、丢报注入。

**故障注入与边界值（`test_fault_injection.py`）**：车速/手柄/SOC/温度边界值编码与
越界拒绝、超速→报警事件联动（>160km/h）、心跳丢失检测、单报文丢失不影响其他报文、
时钟抖动下计数器完整性、车门故障安全（AllDoorsClosed 不得置位）、原始帧往返无损、
未知报文 ID 拒绝解码。

**安全联锁逻辑（`test_interlocks.py`）**：门-车联锁（开门/故障状态下移动即违规）、
超速判定边界（160km/h 含等于不触发）、紧急制动决策矩阵、受电弓拉弧风险
（电压异常 + 弓升）、SOC 能源联锁。

**多节点总线（`test_multinode.py`）**：节点-报文归属映射完整性、节点级失活隔离
（BMS 失活仅影响能源报文）、BCU 失活隔离、节点恢复后报文重新出现、未知节点拒绝。

## CI

GitHub Actions（`.github/workflows/ci.yml`）：Python 3.10/3.11/3.12 矩阵，
每次 push / PR 自动运行全部测试。

## 技术栈

Python · python-can（虚拟 CAN）· cantools（DBC 解析/编码）· pytest · pytest-html · Allure · GitHub Actions

## 后续规划

- [ ] CRC 校验与错误帧注入
- [ ] 真实 CAN 硬件适配（PCAN / 周立功）
- [ ] 列车门控/超速逻辑状态机可视化

## 说明

本项目为学习/求职展示用途的轨道交通测试工具，报文协议为模拟设计，非真实车型协议。