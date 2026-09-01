"""CANopen NMT 心跳层测试（CiA 301）：生产者/消费者/超时/状态迁移。"""

import pytest

from tcms import nmt as nm

NMT_BOOTUP = nm.NMT_BOOTUP
NMT_STOPPED = nm.NMT_STOPPED
NMT_OPERATIONAL = nm.NMT_OPERATIONAL
NMT_PRE_OPERATIONAL = nm.NMT_PRE_OPERATIONAL
ONLINE = nm.NODE_ONLINE
LOST = nm.NODE_HEARTBEAT_LOST


# ---- 生产者 ----

def test_producer_cob_id():
    p = nm.HeartbeatProducer(node_id=5)
    assert p.cob_id == 0x705


def test_producer_bootup_then_state():
    p = nm.HeartbeatProducer(node_id=1)
    assert p.heartbeat_payload() == bytes([NMT_BOOTUP])   # 首帧 boot-up
    assert p.heartbeat_payload() == bytes([NMT_PRE_OPERATIONAL])  # 之后当前状态


def test_producer_state_transitions():
    p = nm.HeartbeatProducer(node_id=1)
    p.set_state(NMT_OPERATIONAL)
    p.heartbeat_payload()   # 消耗 boot-up
    assert p.heartbeat_payload() == bytes([NMT_OPERATIONAL])
    p.set_state(NMT_STOPPED)
    assert p.heartbeat_payload() == bytes([NMT_STOPPED])


def test_producer_invalid_state():
    p = nm.HeartbeatProducer(node_id=1)
    with pytest.raises(ValueError):
        p.set_state(0x42)


def test_producer_reset_resent_bootup():
    p = nm.HeartbeatProducer(node_id=1)
    p.heartbeat_payload()   # boot-up
    p.reset()
    assert p.state == NMT_PRE_OPERATIONAL
    assert p.heartbeat_payload() == bytes([NMT_BOOTUP])   # 复位后重发 boot-up


def test_node_id_bounds():
    with pytest.raises(ValueError):
        nm.HeartbeatProducer(node_id=0)
    with pytest.raises(ValueError):
        nm.HeartbeatProducer(node_id=128)


# ---- 消费者 ----

def test_consumer_initial_lost():
    hc = nm.HeartbeatConsumer(period_ms=100, timeout_ms=300)
    assert hc.state == LOST


def test_consumer_online_after_heartbeat():
    hc = nm.HeartbeatConsumer(period_ms=100, timeout_ms=300)
    hc.on_heartbeat(NMT_OPERATIONAL, 0.0)
    assert hc.state == ONLINE


def test_consumer_timeout_lost():
    hc = nm.HeartbeatConsumer(period_ms=100, timeout_ms=300)
    hc.on_heartbeat(NMT_OPERATIONAL, 0.0)
    assert hc.check_timeout(0.29) == ONLINE    # < 0.3
    assert hc.check_timeout(0.31) == LOST      # > 0.3
    assert hc._events == 1


def test_consumer_bootup_resets_timer():
    hc = nm.HeartbeatConsumer(period_ms=100, timeout_ms=300)
    hc.on_heartbeat(NMT_OPERATIONAL, 0.0)
    hc.on_heartbeat(NMT_BOOTUP, 0.0)   # 节点重启：重新计时
    assert hc.state == ONLINE
    assert hc.check_timeout(0.29) == ONLINE


def test_consumer_reset():
    hc = nm.HeartbeatConsumer(period_ms=100, timeout_ms=300)
    hc.on_heartbeat(NMT_OPERATIONAL, 0.0)
    hc.reset()
    assert hc.state == LOST
    assert hc._events == 0


def test_consumer_never_received_no_timeout_event():
    """从未收到心跳时 check_timeout 不产生事件（首次上线前的静默）。"""
    hc = nm.HeartbeatConsumer(period_ms=100, timeout_ms=300)
    assert hc.check_timeout(10.0) == LOST
    assert hc._events == 0


# ---- 集成：生产者→消费者 ----

def test_producer_consumer_loop():
    p = nm.HeartbeatProducer(node_id=2)
    hc = nm.HeartbeatConsumer(period_ms=100, timeout_ms=300)
    ts = 0.0
    hc.on_heartbeat(p.heartbeat_payload(), ts)   # boot-up
    for i in range(5):
        ts += 0.1
        hc.on_heartbeat(p.heartbeat_payload(), ts)
        assert hc.check_timeout(ts) == ONLINE
    # 停止心跳 → 超时丢失
    ts += 0.35
    assert hc.check_timeout(ts) == LOST
