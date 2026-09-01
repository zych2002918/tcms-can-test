"""多网段拓扑抽象（A6）—— 多总线 + 网关转发（只做拓扑，不做协议）。

对标真实列控网络：MVB/TRDP/以太网并存的多网段结构，不同子系统
（牵引/制动/门控/信号）挂在不同网段上，网段之间通过**网关**按
报文 ID 过滤转发——网关是"拓扑上的门"，不是协议转换器。

设计原则（红线内）：
    - 只做拓扑抽象：Segment（命名总线）+ Gateway（ID 过滤转发规则）
    - 不重写 MVB/TRDP 协议，不绑定任何真实协议细节
    - 网关转发规则 = 报文 ID 白名单/黑名单（对标真实网关的报文过滤表）
    - 转发路径可统计、可审计（面试点：拓扑可观测性）

用法：
    net = BusNetwork({"propulsion": bus_a, "brake": bus_b})
    net.add_gateway("gw1", src="propulsion", dst="brake",
                    allow_ids=[proto.TCMS_HEARTBEAT])
    net.send("propulsion", msg)   # 自动按规则转发到 brake 段
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Iterable

import can
from can import Bus, Message

# 转发规则类型
RULE_ALLOW = "allow"   # 白名单：仅在列表中
RULE_BLOCK = "block"   # 黑名单：不在列表中


@dataclass
class Gateway:
    """网段间报文网关：按 ID 规则过滤转发。

    属性：
        name:      网关名（审计用）
        src:       源网段名
        dst:       目标网段名
        allow_ids: 白名单（rule=allow 时生效；为空 = 全部转发）
        block_ids: 黑名单（rule=block 时生效；为空 = 全部转发）
        rule:      RULE_ALLOW / RULE_BLOCK
        forwarded: 累计转发帧数（可观测性）
        dropped:   累计丢弃帧数（可观测性）
    """

    name: str
    src: str
    dst: str
    allow_ids: set[int] = field(default_factory=set)
    block_ids: set[int] = field(default_factory=set)
    rule: str = RULE_ALLOW
    forwarded: int = 0
    dropped: int = 0

    def should_forward(self, arb_id: int) -> bool:
        """按规则判定某报文 ID 是否应转发。"""
        if self.rule == RULE_ALLOW:
            return arb_id in self.allow_ids if self.allow_ids else True
        return arb_id not in self.block_ids


class BusNetwork:
    """多网段拓扑：命名总线集合 + 网关互联 + 自动路由。

    发送路径：net.send(segment, msg) → 该段所有出站网关按规则转发
    接收路径：net.recv_from(segment) → 该段本地总线消息
    隔离验证：无网关的两段互不可见（测试"网段隔离"）
    """

    def __init__(self, buses: dict[str, Bus]):
        if not buses:
            raise ValueError("至少需要一个网段")
        self._buses: dict[str, Bus] = dict(buses)
        self._gateways: dict[str, Gateway] = {}
        self._by_src: dict[str, list[str]] = {}   # src → 网关名列表
        self._forward_log: list[dict] = []        # 审计日志（深拷贝语义）

    # ---- 拓扑构建 ----

    def add_segment(self, name: str, bus: Bus) -> None:
        """追加网段（运行时热插拔）。"""
        if name in self._buses:
            raise ValueError(f"网段已存在: {name}")
        self._buses[name] = bus

    def add_gateway(self, name: str, src: str, dst: str,
                    allow_ids: Iterable[int] | None = None,
                    block_ids: Iterable[int] | None = None,
                    rule: str = RULE_ALLOW) -> Gateway:
        """添加网关。网段必须已存在且 src != dst。"""
        if name in self._gateways:
            raise ValueError(f"网关已存在: {name}")
        if src not in self._buses:
            raise ValueError(f"源网段不存在: {src}")
        if dst not in self._buses:
            raise ValueError(f"目标网段不存在: {dst}")
        if src == dst:
            raise ValueError("网关源/目标不能同一网段")
        if rule not in (RULE_ALLOW, RULE_BLOCK):
            raise ValueError(f"未知规则: {rule}")
        gw = Gateway(name, src, dst,
                     allow_ids=set(allow_ids or []),
                     block_ids=set(block_ids or []), rule=rule)
        self._gateways[name] = gw
        self._by_src.setdefault(src, []).append(name)
        return gw

    # ---- 数据面 ----

    def send(self, segment: str, msg: Message) -> bool:
        """发送报文到指定网段，并自动触发出站网关级联转发。

        返回是否成功发送到本地段（转发结果在网关统计中）。
        """
        if segment not in self._buses:
            raise ValueError(f"网段不存在: {segment}")
        bus = self._buses[segment]
        try:
            bus.send(msg)
            ok = True
        except can.CanError:
            ok = False
        self._route(msg, segment, {segment})
        return ok

    def _route(self, msg: Message, from_segment: str, visited: set[str]) -> None:
        """从某段出发，沿出站网关级联转发（visited 防环）。"""
        for gw_name in self._by_src.get(from_segment, ()):
            gw = self._gateways[gw_name]
            if gw.dst in visited:
                continue  # 防环：避免 A→B→A 无限转发
            if gw.should_forward(msg.arbitration_id):
                dst_bus = self._buses[gw.dst]
                try:
                    dst_bus.send(msg)
                    dst_ok = True
                except can.CanError:
                    dst_ok = False
                gw.forwarded += 1
                self._forward_log.append({
                    "gateway": gw.name, "src": gw.src, "dst": gw.dst,
                    "arb_id": msg.arbitration_id,
                    "forwarded": dst_ok,
                })
                self._route(msg, gw.dst, visited | {from_segment})
            else:
                gw.dropped += 1

    def recv_from(self, segment: str, timeout: float = 0.0) -> Message | None:
        """从指定网段接收一条报文（本地段视角）。"""
        if segment not in self._buses:
            raise ValueError(f"网段不存在: {segment}")
        return self._buses[segment].recv(timeout=timeout)

    def recv_any(self, timeout: float = 0.0) -> tuple[str, Message] | None:
        """跨网段接收：返回 (网段名, 报文)，按段名排序轮询。

        用于"全网段统一视角"（对标真实测试台的网络级监控）。
        """
        for name in sorted(self._buses):
            msg = self._buses[name].recv(timeout=0.0)
            if msg is not None:
                return name, msg
        # 全部空时再阻塞等 timeout：小步轮询全部段，避免只盯第一段
        if timeout > 0:
            deadline = time.monotonic() + timeout
            names = sorted(self._buses)
            while True:
                for name in names:
                    msg = self._buses[name].recv(timeout=0.01)
                    if msg is not None:
                        return name, msg
                if time.monotonic() >= deadline:
                    return None
        return None

    # ---- 管理面 ----

    @property
    def segments(self) -> list[str]:
        return sorted(self._buses)

    @property
    def gateways(self) -> list[str]:
        return list(self._gateways)

    def gateway_stats(self) -> dict[str, dict]:
        """网关统计（转发/丢弃计数）。"""
        return {name: {"forwarded": gw.forwarded, "dropped": gw.dropped}
                for name, gw in self._gateways.items()}

    def forward_log(self) -> list[dict]:
        """转发审计日志（深拷贝，防止外部篡改）。"""
        return [dict(e) for e in self._forward_log]

    def reset_stats(self) -> None:
        """清零网关计数与转发日志。"""
        for gw in self._gateways.values():
            gw.forwarded = 0
            gw.dropped = 0
        self._forward_log.clear()
