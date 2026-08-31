"""列车网络控制（TCMS）CAN 协议定义与常量。

基于 dbc/tcms.dbc 的协议封装：
- 报文 ID 常量
- 信号常量（状态枚举）
- DBC 加载与节点信息
"""

from pathlib import Path

import cantools

DBC_PATH = Path(__file__).resolve().parent.parent / "dbc" / "tcms.dbc"

# ---- 报文 ID 常量 ----
TCMS_HEARTBEAT = 0x100        # TCMS 心跳（100ms）
VEHICLE_SPEED = 0x200         # 车速（100ms）
TRACTION_BRAKE_HANDLE = 0x300  # 牵引/制动手柄（50ms）
DOOR_CONTROL = 0x400          # 车门控制（100ms）
ALARM_EVENT = 0x500           # 报警事件（事件触发）
PANTOGRAPH_STATUS = 0x600     # 受电弓状态（500ms）
BRAKE_SYSTEM = 0x700          # 制动系统（100ms）
ENERGY_STATUS = 0x780         # 能源/电池状态（500ms）

# ---- 报文名称 ----
MESSAGE_NAMES = {
    TCMS_HEARTBEAT: "TCMS_Heartbeat",
    VEHICLE_SPEED: "VehicleSpeed",
    TRACTION_BRAKE_HANDLE: "TractionBrakeHandle",
    DOOR_CONTROL: "DoorControl",
    ALARM_EVENT: "AlarmEvent",
    PANTOGRAPH_STATUS: "PantographStatus",
    BRAKE_SYSTEM: "BrakeSystem",
    ENERGY_STATUS: "EnergyStatus",
}

# ---- 状态枚举 ----
NODE_STATUS = {0: "PowerOff", 1: "Standby", 2: "Active", 3: "Fault"}
RUN_MODE = {0: "Offline", 1: "Manual", 2: "ATO", 3: "Shunting", 4: "Emergency"}
DIRECTION = {0: "Neutral", 1: "Forward", 2: "Reverse", 3: "Invalid"}
DOOR_STATE = {0: "Closed", 1: "Open", 2: "Fault", 3: "Unknown"}
ALARM_LEVEL = {0: "Info", 1: "Warning", 2: "Severe", 3: "Emergency"}
CHARGE_STATE = {0: "Idle", 1: "Charging", 2: "Discharging", 3: "Fault"}

# ---- 安全阈值 ----
MAX_SPEED_KMH = 200.0        # 信号物理上限
OVERSPEED_LIMIT_KMH = 160.0  # 超速报警阈值
MAX_HANDLE_POSITION = 16     # 手柄级位上限
MAX_ALARM_LEVEL = 3          # 报警等级上限


def load_database(path: Path | str = DBC_PATH) -> cantools.database.can.Database:
    """加载 DBC 数据库。"""
    return cantools.database.load_file(path)


def encode(db, message_name: str, **signals) -> bytes:
    """编码报文：缺失信号自动补零，返回 8 字节原始数据。"""
    message = db.get_message_by_name(message_name)
    for sig in message.signals:
        signals.setdefault(sig.name, 0)
    return db.encode_message(message_name, signals)