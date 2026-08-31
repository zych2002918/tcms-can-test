"""列车安全联锁逻辑（测试视角的规则验证）。

面向轨道交通"安全联锁"场景的规则模块：门-车联锁、超速-制动联锁、
受电弓异常检测。供自动化测试验证 TCMS 应用逻辑的正确性，
模拟的是列控软件中"安全关键功能"的测试面。

设计原则：任何联锁违规必须显式返回原因，便于缺陷定位。
"""

from . import protocol as proto

MOTION_THRESHOLD_KMH = 0.5  # 超过该速度视为"列车移动中"


def door_motion_conflict(
    door_states: list[int],
    speed_kmh: float,
    speed_valid: bool = True,
) -> tuple[bool, str]:
    """门-车联锁：列车移动时，任一车门处于打开或故障状态即违规。

    返回 (是否违规, 原因)。安全原则：故障门按未关闭处理。
    """
    any_open = any(s == 1 for s in door_states)
    any_fault = any(s == 2 for s in door_states)
    moving = speed_valid and speed_kmh > MOTION_THRESHOLD_KMH
    if moving and any_open:
        return True, "door_open_while_moving"
    if moving and any_fault:
        return True, "door_fault_while_moving"
    return False, ""


def overspeed_trigger(
    speed_kmh: float,
    speed_valid: bool = True,
    limit: float = proto.OVERSPEED_LIMIT_KMH,
) -> bool:
    """超速判定：有效速度超过限速即触发（不含等于）。"""
    return speed_valid and speed_kmh > limit


def emergency_brake_decision(
    speed_kmh: float,
    overspeed_flag: bool,
    door_conflict: bool,
) -> bool:
    """紧急制动决策：超速 或 门联锁冲突 时触发紧急制动。"""
    return bool(overspeed_flag or door_conflict)


def pantograph_arc_risk(pantograph_up: int, line_voltage: float) -> tuple[bool, str]:
    """受电弓异常：弓升但接触网电压异常（过低/过高）存在拉弧风险。"""
    if not pantograph_up:
        return False, ""
    if line_voltage < 19000:
        return True, "line_voltage_low_with_pantograph_up"
    if line_voltage > 31000:
        return True, "line_voltage_high_with_pantograph_up"
    return False, ""


def soc_low_charge_guard(soc_percent: int, charging: bool) -> tuple[bool, str]:
    """能源联锁：SOC 过低且未充电时提示（非安全违规，降级运行信号）。"""
    if soc_percent < 10 and not charging:
        return True, "soc_critical_not_charging"
    return False, ""