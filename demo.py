"""TCMS-CAN-Test 面试演示脚本：跑通"正常 → 超速 → 紧急制动 → 丢报 → 看门狗"全场景。

用法: python demo.py
输出为纯文本，可直接展示或粘贴到面试材料中。
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import can

from tcms import protocol as proto
from tcms.multinode import MultiNodeSimulator
from tcms.parser import count_frames
from tcms.watchdogs import NodeHealthTable


def banner(title):
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def main() -> None:
    bus = can.Bus(interface="virtual", channel="tcms-demo", receive_own_messages=True)
    db = proto.load_database()

    banner("STEP 1 | 启动多节点仿真（VCU / BCU / BMS）")
    sim = MultiNodeSimulator(bus, db)
    sim.start()
    time.sleep(0.8)
    print(f"总线活跃节点: {sim.active_nodes}")
    print(f"1 秒内心跳帧数: {count_frames(bus, 1.0, proto.TCMS_HEARTBEAT)} (期望≈10)")
    print(f"1 秒内手柄帧数: {count_frames(bus, 1.0, proto.TRACTION_BRAKE_HANDLE)} (期望≈20)")

    banner("STEP 2 | 超速场景（>160km/h → 超速报警 → 紧急制动判定）")
    sim.send_alarm(1, 2, Overspeed=True)
    time.sleep(0.1)
    n = count_frames(bus, 0.3, proto.ALARM_EVENT)
    print(f"超速报警帧收到 {n} 条")

    banner("STEP 3 | 节点失活（模拟 BMS 断电）")
    sim.disable_node("BMS")
    time.sleep(0.6)
    n = count_frames(bus, 0.5, proto.ENERGY_STATUS)
    print(f"BMS 失活后能源报文帧数: {n} (期望 0)")
    print(f"其余节点仍活跃: {sim.active_nodes}")

    banner("STEP 4 | 心跳看门狗（3 周期未收心跳 → 节点判离线）")
    table = NodeHealthTable(cycle_time=0.1, miss_threshold=3)
    for _ in range(20):
        msg = bus.recv(timeout=0.05)
        if msg is not None and msg.arbitration_id == proto.TCMS_HEARTBEAT:
            table.feed("VCU")
    table.evaluate()
    print(f"喂心跳后 VCU 状态: {table.status('VCU')} (期望 online)")
    sim.disable_node("VCU")
    time.sleep(0.5)
    table.evaluate()
    print(f"心跳停止后 VCU 状态: {table.status('VCU')} (期望 fault)")

    banner("STEP 5 | 节点恢复（重新上电 → 2 次有效心跳回在线）")
    sim.enable_node("VCU")
    time.sleep(0.3)
    while bus.recv(timeout=0.01) is not None:
        pass
    feeds = 0
    for _ in range(10):
        msg = bus.recv(timeout=0.1)
        if msg is not None and msg.arbitration_id == proto.TCMS_HEARTBEAT:
            table.feed("VCU")
            feeds += 1
    table.evaluate()
    print(f"恢复后收到 {feeds} 次心跳，VCU 状态: {table.status('VCU')} (期望 online)")

    sim.stop()
    bus.shutdown()
    banner("DONE | 全场景演示完成")
    print("代码: https://github.com/zych2002918/tcms-can-test")


if __name__ == "__main__":
    main()