"""A6 多网段拓扑：多总线 + 网关转发 + 隔离验证测试。

覆盖：拓扑构建（段/网关）、白名单/黑名单转发规则、网段隔离（无网关
不互通）、转发统计与审计日志、热插拔段、跨网段统一接收、错误处理。
"""

import can
import pytest
from can import Bus, Message

from tcms import network
from tcms import protocol as proto


@pytest.fixture
def two_segments():
    """两个网段（propulsion / brake）的拓扑。"""
    bus_a = Bus(interface="virtual", channel="seg-prop", receive_own_messages=True)
    bus_b = Bus(interface="virtual", channel="seg-brake", receive_own_messages=True)
    net = network.BusNetwork({"propulsion": bus_a, "brake": bus_b})
    yield net
    bus_a.shutdown()
    bus_b.shutdown()


@pytest.fixture
def three_segments():
    """三个网段（propulsion / brake / doors）的拓扑，propulsion→brake→doors。"""
    buses = {
        "propulsion": Bus(interface="virtual", channel="seg-p", receive_own_messages=True),
        "brake": Bus(interface="virtual", channel="seg-b", receive_own_messages=True),
        "doors": Bus(interface="virtual", channel="seg-d", receive_own_messages=True),
    }
    net = network.BusNetwork(buses)
    yield net
    for b in buses.values():
        b.shutdown()


def _msg(arb_id: int, data: bytes = b"\x01\x02") -> Message:
    return Message(arbitration_id=arb_id, data=data, is_extended_id=False)


# ---- 拓扑构建 ----

def test_network_init_requires_segments():
    with pytest.raises(ValueError, match="至少"):
        network.BusNetwork({})


def test_add_gateway_basic(two_segments):
    gw = two_segments.add_gateway("gw1", "propulsion", "brake",
                                  allow_ids=[proto.TCMS_HEARTBEAT])
    assert gw.name == "gw1"
    assert two_segments.gateways == ["gw1"]
    assert two_segments.segments == ["brake", "propulsion"]


def test_add_gateway_duplicate_rejected(two_segments):
    two_segments.add_gateway("gw1", "propulsion", "brake")
    with pytest.raises(ValueError, match="已存在"):
        two_segments.add_gateway("gw1", "brake", "propulsion")


def test_add_gateway_missing_segment_rejected(two_segments):
    with pytest.raises(ValueError, match="源网段不存在"):
        two_segments.add_gateway("gw1", "nope", "brake")
    with pytest.raises(ValueError, match="目标网段不存在"):
        two_segments.add_gateway("gw2", "propulsion", "nope")


def test_add_gateway_same_segment_rejected(two_segments):
    with pytest.raises(ValueError, match="不能同一网段"):
        two_segments.add_gateway("gw1", "propulsion", "propulsion")


def test_add_gateway_bad_rule_rejected(two_segments):
    with pytest.raises(ValueError, match="未知规则"):
        two_segments.add_gateway("gw1", "propulsion", "brake", rule="bogus")


def test_add_segment_duplicate_rejected(two_segments):
    with pytest.raises(ValueError, match="已存在"):
        two_segments.add_segment("propulsion", two_segments._buses["propulsion"])


# ---- 转发规则 ----

def test_allow_rule_forwards_only_allowed(two_segments):
    two_segments.add_gateway("gw1", "propulsion", "brake",
                             allow_ids=[proto.TCMS_HEARTBEAT])
    two_segments.send("propulsion", _msg(proto.TCMS_HEARTBEAT))   # 允许
    two_segments.send("propulsion", _msg(proto.VEHICLE_SPEED))    # 拒绝
    msg = two_segments.recv_from("brake", timeout=0.2)
    assert msg is not None
    assert msg.arbitration_id == proto.TCMS_HEARTBEAT
    assert two_segments.recv_from("brake", timeout=0.05) is None  # 车速未转发
    st = two_segments.gateway_stats()["gw1"]
    assert st["forwarded"] == 1
    assert st["dropped"] == 1


def test_allow_rule_empty_means_all(two_segments):
    """白名单为空 = 全部转发。"""
    two_segments.add_gateway("gw1", "propulsion", "brake")
    two_segments.send("propulsion", _msg(proto.TCMS_HEARTBEAT))
    two_segments.send("propulsion", _msg(proto.VEHICLE_SPEED))
    st = two_segments.gateway_stats()["gw1"]
    assert st["forwarded"] == 2
    assert st["dropped"] == 0


def test_block_rule_forwards_except_blocked(two_segments):
    two_segments.add_gateway("gw1", "propulsion", "brake",
                             block_ids=[proto.ALARM_EVENT], rule=network.RULE_BLOCK)
    two_segments.send("propulsion", _msg(proto.TCMS_HEARTBEAT))
    two_segments.send("propulsion", _msg(proto.ALARM_EVENT))
    st = two_segments.gateway_stats()["gw1"]
    assert st["forwarded"] == 1   # 心跳转发
    assert st["dropped"] == 1     # 报警被黑名单拦截


def test_segment_isolation_no_gateway(two_segments):
    """无网关的两段互不可见（隔离）。"""
    two_segments.send("propulsion", _msg(proto.TCMS_HEARTBEAT))
    assert two_segments.recv_from("brake", timeout=0.05) is None


# ---- 数据面 ----

def test_send_unknown_segment_rejected(two_segments):
    with pytest.raises(ValueError, match="网段不存在"):
        two_segments.send("nope", _msg(proto.TCMS_HEARTBEAT))


def test_chain_forwarding_three_segments(three_segments):
    """级联转发：propulsion →(gw1)→ brake →(gw2)→ doors。"""
    three_segments.add_gateway("gw1", "propulsion", "brake")
    three_segments.add_gateway("gw2", "brake", "doors",
                               allow_ids=[proto.TCMS_HEARTBEAT])
    three_segments.send("propulsion", _msg(proto.TCMS_HEARTBEAT))
    # brake 段能收到（gw1 转发）
    assert three_segments.recv_from("brake", timeout=0.2) is not None
    # doors 段能收到（gw2 级联转发）
    assert three_segments.recv_from("doors", timeout=0.2) is not None
    st = three_segments.gateway_stats()
    assert st["gw1"]["forwarded"] == 1
    assert st["gw2"]["forwarded"] == 1


def test_forward_log_audit(two_segments):
    two_segments.add_gateway("gw1", "propulsion", "brake",
                             allow_ids=[proto.TCMS_HEARTBEAT])
    two_segments.send("propulsion", _msg(proto.TCMS_HEARTBEAT))
    two_segments.send("propulsion", _msg(proto.VEHICLE_SPEED))
    log = two_segments.forward_log()
    assert len(log) == 1  # 只记录转发成功项
    assert log[0]["gateway"] == "gw1"
    assert log[0]["arb_id"] == proto.TCMS_HEARTBEAT
    assert log[0]["forwarded"] is True
    # 深拷贝语义：外部修改不影响内部
    log[0]["gateway"] = "hacked"
    assert two_segments.forward_log()[0]["gateway"] == "gw1"


def test_reset_stats(two_segments):
    two_segments.add_gateway("gw1", "propulsion", "brake")
    two_segments.send("propulsion", _msg(proto.TCMS_HEARTBEAT))
    two_segments.reset_stats()
    assert two_segments.gateway_stats()["gw1"]["forwarded"] == 0
    assert two_segments.forward_log() == []


def test_recv_any_cross_segment(two_segments):
    """跨网段统一接收视角。"""
    two_segments.add_gateway("gw1", "propulsion", "brake")
    two_segments.send("propulsion", _msg(proto.VEHICLE_SPEED))
    got = two_segments.recv_any(timeout=0.2)
    assert got is not None
    seg, msg = got
    assert seg in ("brake", "propulsion")  # 两个段都能看到
    assert msg.arbitration_id == proto.VEHICLE_SPEED


def test_hot_add_segment(two_segments):
    """运行时热插拔网段。"""
    bus_c = Bus(interface="virtual", channel="seg-c", receive_own_messages=True)
    try:
        two_segments.add_segment("doors", bus_c)
        two_segments.add_gateway("gw1", "propulsion", "doors")
        two_segments.send("propulsion", _msg(proto.TCMS_HEARTBEAT))
        assert two_segments.recv_from("doors", timeout=0.2) is not None
    finally:
        bus_c.shutdown()


def test_gateway_stats_shape(two_segments):
    two_segments.add_gateway("gw1", "propulsion", "brake")
    two_segments.add_gateway("gw2", "brake", "propulsion")
    st = two_segments.gateway_stats()
    assert set(st) == {"gw1", "gw2"}
    for v in st.values():
        assert v == {"forwarded": 0, "dropped": 0}


# ---- 防御分支 / 边界 ----

def test_loop_prevention(two_segments):
    """双向网关 A→B→A 不应无限转发（防环）。"""
    two_segments.add_gateway("gw1", "propulsion", "brake")
    two_segments.add_gateway("gw2", "brake", "propulsion")
    two_segments.send("propulsion", _msg(proto.TCMS_HEARTBEAT))
    # 转发路径：propulsion→brake（gw1），不再回传（防环）
    assert two_segments.recv_from("brake", timeout=0.2) is not None
    # 两次转发累计（gw1 转发 1 次，不因环重复）
    st = two_segments.gateway_stats()
    assert st["gw1"]["forwarded"] == 1
    assert st["gw2"]["forwarded"] == 0  # 反向无报文从 brake 出发


def test_send_bus_error_returns_false(monkeypatch, two_segments):
    """本地发送失败 → send() 返回 False（不抛异常）。"""
    class BoomBus:
        def send(self, msg):
            raise can.CanError("bus broken")
        def recv(self, timeout=0.0):
            return None

    monkeypatch.setitem(two_segments._buses, "propulsion", BoomBus())
    assert two_segments.send("propulsion", _msg(0x100)) is False


def test_forward_bus_error_counts_forwarded(monkeypatch, two_segments):
    """网关目标段发送失败 → 仍计 forwarded，日志记录 forwarded=False。"""
    class BoomBus:
        def send(self, msg):
            raise can.CanError("dst broken")
        def recv(self, timeout=0.0):
            return None

    two_segments.add_gateway("gw1", "propulsion", "brake")
    monkeypatch.setitem(two_segments._buses, "brake", BoomBus())
    two_segments.send("propulsion", _msg(proto.TCMS_HEARTBEAT))
    st = two_segments.gateway_stats()["gw1"]
    assert st["forwarded"] == 1
    assert two_segments.forward_log()[0]["forwarded"] is False


def test_recv_from_unknown_segment_rejected(two_segments):
    with pytest.raises(ValueError, match="网段不存在"):
        two_segments.recv_from("nope")


def test_recv_any_blocking_wait(two_segments):
    """空总线 + timeout>0 → 阻塞等待第一段。"""
    two_segments.send("propulsion", _msg(proto.TCMS_HEARTBEAT))
    # 清空两个段
    while two_segments.recv_any(timeout=0.0) is not None:
        pass
    assert two_segments.recv_any(timeout=0.0) is None      # 空 → None
    # 阻塞等待：先发后收
    got = two_segments.recv_any(timeout=0.3)
    assert got is None or got[1].arbitration_id == proto.TCMS_HEARTBEAT


def test_recv_any_blocking_gets_message(two_segments):
    """阻塞等待窗口内有报文到达 → 返回该报文。"""
    import threading

    def delayed_send():
        import time
        time.sleep(0.1)
        two_segments.send("propulsion", _msg(proto.TCMS_HEARTBEAT))

    t = threading.Thread(target=delayed_send, daemon=True)
    t.start()
    got = two_segments.recv_any(timeout=1.0)
    assert got is not None
    seg, msg = got
    assert msg.arbitration_id == proto.TCMS_HEARTBEAT
    t.join(timeout=2.0)
