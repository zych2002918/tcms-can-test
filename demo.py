"""TCMS-CAN-Test 面试演示脚本：跑通"正常 → 超速 → 紧急制动 → 丢报 → 看门狗"全场景。

用法: python demo.py
输出为纯文本，可直接展示或粘贴到面试材料中。
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import can

from tcms import ebm
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
    while bus.recv(timeout=0.01) is not None:
        pass  # 清空启动期积压帧，确保统计窗口只含新建帧
    print(f"1 秒内心跳帧数: {count_frames(bus, 1.0, proto.TCMS_HEARTBEAT)} (期望≈10)")
    print(f"1 秒内手柄帧数: {count_frames(bus, 1.0, proto.TRACTION_BRAKE_HANDLE)} (期望≈20，多节点调度下 15-20 属正常)")

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

    banner("STEP 6 | 紧急制动管理（EBM：模式×原因矩阵 + 缓解/复位闭环）")
    mgr = ebm.EmergencyBrakeManager(mode=ebm.MODE_FAM)
    print(f"初始: 模式={mgr.mode}, 状态={mgr.state}")
    r = mgr.trigger("ato_fault")
    print(f"ATO 故障 → 处置={r['action']} (SIL{r['sil']}), 状态={mgr.state}, 自动降级模式={mgr.mode}")
    vote = mgr.channel_vote("overspeed", channel_a=True, channel_b=False)
    print(f"SIL4 超速双通道表决 (A触发/B正常) → 是否制动: {vote}（任一通道触发即制动，故障安全）")
    mgr.update_reason_status("ato_fault", False)
    releasable = mgr.release_condition(0.0)
    print(f"列停稳 + ATO 故障消失 → 缓解条件满足={releasable}, 状态={mgr.state}")
    mgr.reset()
    print(f"远程复位 → 状态={mgr.state}")

    banner("STEP 7 | CAN 错误状态机 + 事件记录器（统一时间线）")
    from tcms.errstate import CanErrorStateMachine
    from tcms.recorder import (
        EventRecorder, RecordedBus, hook_ebm, hook_errstate,
    )

    # 互操作：错误状态机与 EBM 的动作经 hook 写入同一个事件记录器，
    # 总线帧经 RecordedBus 装饰器透明记录 —— 安全事件与总线流量共享时间线
    rec = EventRecorder(capacity=200)
    ev_bus = can.Bus(interface="virtual", channel="tcms-demo-events",
                     receive_own_messages=True)
    rbus = RecordedBus(ev_bus, rec, node="tcms")
    sm = CanErrorStateMachine()
    hook_errstate(sm, rec, node="elcu")
    hook_ebm(mgr, rec)

    rbus.send(can.Message(arbitration_id=proto.VEHICLE_SPEED, data=bytes(8),
                          is_extended_id=False))
    for _ in range(16):
        sm.tx_error()  # TEC 0→128：error-active → error-passive
    mgr.trigger("overspeed")  # EBM 制动（记录 ebm 事件）
    mgr.update_reason_status("overspeed", False)
    mgr.release_condition(0.0)
    rbus.send(can.Message(arbitration_id=proto.ALARM_EVENT, data=bytes(8),
                          is_extended_id=False))
    rbus.recv(timeout=0.1)  # 回读自己发出的帧 → can_rx 事件

    st = rec.stats()
    print(f"时间线事件总数: {st['total']} (can_tx={st['by_type'].get('can_tx', 0)}, "
          f"can_rx={st['by_type'].get('can_rx', 0)}, "
          f"ebm={st['by_type'].get('ebm', 0)}, "
          f"errstate={st['by_type'].get('errstate', 0)})")
    print(f"错误状态机: TEC={sm.tec} → 状态 {sm.state} (期望 error-passive)  "
          f"损坏帧统计={sm.error_frames}")
    print("时间线（前 8 条，ts 为单调时钟秒）:")
    for e in rec.query()[:8]:
        print(f"  [{e['ts']:.3f}] {e['type']:<9} {e['message'] or ''} "
              f"{e['payload'] or ''}")
    ev_bus.shutdown()

    banner("DONE | 全场景演示完成")
    print("代码: https://github.com/zych2002918/tcms-can-test")


if __name__ == "__main__":
    main()