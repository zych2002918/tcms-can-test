"""TCMS 列车网络控制器仿真器。

在虚拟 CAN 总线上按 DBC 定义的周期模拟机车 TCMS 节点报文，
支持故障注入（停止发送 / 超界信号 / 异常事件），作为被测对象
（DUT）供自动化测试驱动。

用法:
    import can
    bus = can.Bus(interface="virtual")
    sim = TCMSNodeSimulator(bus, db)
    sim.start()          # 按周期发送全部周期报文
    sim.send_alarm(...)  # 触发一次报警事件
    sim.stop_message(...) # 停止某个报文（模拟丢报）
    sim.stop()
"""

import threading
import time

from can import Bus, Message

from . import protocol as proto


class TCMSNodeSimulator:
    """模拟一个 TCMS 节点组：多个周期报文 + 事件报文。"""

    def __init__(self, bus: Bus, db, heartbeat_jitter: float = 0.0):
        self.bus = bus
        self.db = db
        self.heartbeat_jitter = heartbeat_jitter  # 心跳抖动（秒），模拟时钟偏差
        self._running = False
        self._threads: list[threading.Thread] = []
        self._speed = 0.0        # 当前模拟车速 km/h
        self._handle = 0         # 手柄级位
        self._direction = 0      # 方向
        self._door_states = [0, 0, 0, 0]  # 四车门状态
        self._heartbeat_counter = 0

    # ---- 生命周期 ----

    def start(self) -> None:
        """启动全部周期报文发送线程。"""
        if self._running:
            return
        self._running = True
        self._threads = [
            self._spawn("heartbeat", proto.TCMS_HEARTBEAT, 0.100),
            self._spawn("speed", proto.VEHICLE_SPEED, 0.100),
            self._spawn("handle", proto.TRACTION_BRAKE_HANDLE, 0.050),
            self._spawn("doors", proto.DOOR_CONTROL, 0.100),
            self._spawn("pantograph", proto.PANTOGRAPH_STATUS, 0.500),
            self._spawn("brake", proto.BRAKE_SYSTEM, 0.100),
            self._spawn("energy", proto.ENERGY_STATUS, 0.500),
        ]

    def stop(self) -> None:
        """停止全部发送线程。"""
        self._running = False
        for t in self._threads:
            t.join(timeout=1.0)
        self._threads.clear()

    # ---- 状态注入（测试驱动用） ----

    def set_speed(self, kmh: float) -> None:
        """设定模拟车速。"""
        self._speed = kmh

    def set_handle(self, position: int, direction: int = 1) -> None:
        """设定手柄级位与方向。"""
        self._handle = position
        self._direction = direction

    def set_door_state(self, door_index: int, state: int) -> None:
        """设定单个车门状态（0 关 / 1 开 / 2 故障）。"""
        if 0 <= door_index < 4:
            self._door_states[door_index] = state

    def stop_message(self, message_id: int) -> None:
        """停止发送指定报文（模拟节点丢报/总线故障）。"""
        # 通过把对应线程的发送标志置空实现：这里用名称标记
        self._stopped = getattr(self, "_stopped", set())
        self._stopped.add(message_id)

    # ---- 报文构建 ----

    def _build(self, name: str, **signals) -> Message:
        data = proto.encode(self.db, name, **signals)
        return Message(
            arbitration_id=self.db.get_message_by_name(name).frame_id,
            data=data,
            is_extended_id=False,
        )

    def _send(self, name: str, **signals) -> None:
        self.bus.send(self._build(name, **signals))

    def send_alarm(self, alarm_code: int, level: int, **flags: bool) -> None:
        """事件触发：发送一条报警报文。"""
        signals = {"AlarmCode": alarm_code, "AlarmLevel": level}
        for flag in ("Overspeed", "DoorNotClosed", "FireAlarm", "PantographDrop"):
            signals[flag] = int(flags.get(flag, False))
        self._send("AlarmEvent", **signals)

    # ---- 内部 ----

    def _spawn(self, tag: str, message_id: int, period: float) -> threading.Thread:
        t = threading.Thread(target=self._loop, args=(tag, message_id, period), daemon=True)
        t.start()
        return t

    def _loop(self, tag: str, message_id: int, period: float) -> None:
        while self._running:
            if message_id not in getattr(self, "_stopped", set()):
                try:
                    self._tick(tag, message_id)
                except Exception:
                    pass
            time.sleep(period + (self.heartbeat_jitter if tag == "heartbeat" else 0.0))

    def _tick(self, tag: str, message_id: int) -> None:
        if message_id == proto.TCMS_HEARTBEAT:
            self._send("TCMS_Heartbeat",
                       NodeStatus=2, RunMode=2,
                       HeartbeatCounter=self._heartbeat_counter % 256)
            self._heartbeat_counter += 1
        elif message_id == proto.VEHICLE_SPEED:
            self._send("VehicleSpeed",
                       SpeedKmh=round(self._speed, 1),
                       SpeedValid=1 if self._speed >= 0 else 0,
                       SpeedSource=1)
        elif message_id == proto.TRACTION_BRAKE_HANDLE:
            self._send("TractionBrakeHandle",
                       HandlePosition=self._handle,
                       Direction=self._direction,
                       TractionActive=1 if self._handle > 0 and self._direction == 1 else 0,
                       BrakeActive=1 if self._direction == 2 else 0)
        elif message_id == proto.DOOR_CONTROL:
            self._send("DoorControl",
                       Door1State=self._door_states[0],
                       Door2State=self._door_states[1],
                       Door3State=self._door_states[2],
                       Door4State=self._door_states[3],
                       AllDoorsClosed=1 if all(s == 0 for s in self._door_states) else 0,
                       DoorOpenPermit=1 if any(s == 1 for s in self._door_states) else 0)
        elif message_id == proto.PANTOGRAPH_STATUS:
            self._send("PantographStatus",
                       PantographUp=1, PantographFault=0,
                       LineVoltage=25000, PantographPressure=5.0)
        elif message_id == proto.BRAKE_SYSTEM:
            self._send("BrakeSystem",
                       BrakeCylinderPressure=0.0,
                       EmergencyBrakeActive=0, BrakeFault=0, ReservePressureLow=0)
        elif message_id == proto.ENERGY_STATUS:
            self._send("EnergyStatus",
                       SocPercent=80, BatteryVoltage=750.0,
                       BatteryCurrent=-50.0, BatteryTemp=35.0, ChargeState=2)