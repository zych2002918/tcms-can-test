"""CANopen NMT 心跳层（CiA 301）—— 对标 CANopen 网络管理的节点监督机制。

CANopen（CiA 301）是工业/车载常用高层协议，其**心跳协议（Heartbeat）**：
    - 每个节点周期性发送 1 字节心跳报文（COB-ID = 0x700 + node_id）
    - 心跳内容 = 节点状态（Boot-up 0x00 / Stopped 0x04 / Operational 0x05 / Pre-operational 0x7F）
    - 监督方（NMT Master）配置心跳消费超时（heartbeat consumer time），
      超时未收到 → 判定节点"心跳丢失"（heartbeat event）

本模块实现：
    - 心跳生产者：节点状态机 + 周期心跳生成
    - 心跳消费者：超时监督 → 节点状态判定（在线/丢失）
    - 节点状态迁移（对应 CANopen NMT 状态机：Initialisation → Pre-operational →
      Operational ↔ Stopped）

设计原则：心跳是"节点健康"的应用层机制（区别于 errstate 的物理层错误计数），
与项目看门狗（watchdogs.py）互补——CANopen 心跳带状态语义，不只是"存活"。
"""

# COB-ID 基址：心跳 = 0x700 + node_id（node_id 1-127）
HEARTBEAT_COB_BASE = 0x700
MIN_NODE_ID = 1
MAX_NODE_ID = 127

# 心跳内容（节点状态）
NMT_BOOTUP = 0x00            # 初始化完成（boot-up 消息，仅一次）
NMT_STOPPED = 0x04           # 停止（不参与通信）
NMT_OPERATIONAL = 0x05       # 运行（正常通信）
NMT_PRE_OPERATIONAL = 0x7F   # 预运行（可配置，不参与 PDO）

# 默认心跳周期（ms，真实设备典型 100-1000ms）
DEFAULT_HEARTBEAT_MS = 100

# 状态
NODE_ONLINE = "online"
NODE_HEARTBEAT_LOST = "heartbeat_lost"


class HeartbeatProducer:
    """心跳生产者：节点状态 → 心跳字节（供虚拟总线发送）。"""

    def __init__(self, node_id: int, period_ms: int = DEFAULT_HEARTBEAT_MS):
        if not (MIN_NODE_ID <= node_id <= MAX_NODE_ID):
            raise ValueError(f"node_id 必须在 {MIN_NODE_ID}-{MAX_NODE_ID}（收到 {node_id}）")
        self.node_id = node_id
        self.period_ms = period_ms
        self.state: int = NMT_PRE_OPERATIONAL
        self._bootup_sent: bool = False

    @property
    def cob_id(self) -> int:
        """心跳报文 COB-ID（0x700 + node_id）。"""
        return HEARTBEAT_COB_BASE + self.node_id

    def set_state(self, state: int) -> None:
        """切换节点状态（合法 NMT 状态字节）。"""
        if state not in (NMT_STOPPED, NMT_OPERATIONAL, NMT_PRE_OPERATIONAL):
            raise ValueError(f"非法 NMT 状态字节: {state:#x}")
        self.state = state

    def heartbeat_payload(self) -> bytes:
        """生成心跳报文负载（1 字节状态）。首帧前先发 boot-up。"""
        if not self._bootup_sent:
            self._bootup_sent = True
            return bytes([NMT_BOOTUP])
        return bytes([self.state])

    def reset(self) -> None:
        """复位：回到 Pre-operational，boot-up 待重发。"""
        self.state = NMT_PRE_OPERATIONAL
        self._bootup_sent = False


class HeartbeatConsumer:
    """心跳消费者：监督节点心跳，超时判定心跳丢失。

    用法：
        hc = HeartbeatConsumer(period_ms=100, timeout_ms=300)
        hc.on_heartbeat(0x05)     # 收到 Operational 心跳
        hc.check_timeout()        # 距上次 > 300ms → heartbeat_lost
    """

    def __init__(self, period_ms: int = DEFAULT_HEARTBEAT_MS, timeout_ms: int | None = None):
        self.period_ms = period_ms
        self.timeout_ms = timeout_ms or period_ms * 3
        self._last_ts: float | None = None
        self._state: str = NODE_HEARTBEAT_LOST
        self._events: int = 0

    @property
    def state(self) -> str:
        return self._state

    def on_heartbeat(self, payload: bytes | int, timestamp_s: float) -> None:
        """收到心跳（payload 为状态字节）。记录时间与状态。"""
        byte = payload if isinstance(payload, int) else payload[0]
        if byte == NMT_BOOTUP:
            # boot-up 视为节点重新初始化，重置计时
            self._last_ts = timestamp_s
            self._state = NODE_ONLINE
            return
        self._last_ts = timestamp_s
        self._state = NODE_ONLINE

    def check_timeout(self, timestamp_s: float) -> str:
        """超时检查：距上次心跳 > timeout → heartbeat_lost（并计数事件）。"""
        if self._last_ts is not None and timestamp_s - self._last_ts > self.timeout_ms / 1000.0:
            if self._state == NODE_ONLINE:
                self._events += 1
            self._state = NODE_HEARTBEAT_LOST
        return self._state

    def reset(self) -> None:
        """复位：回到 lost 状态。"""
        self._last_ts = None
        self._state = NODE_HEARTBEAT_LOST
        self._events = 0
