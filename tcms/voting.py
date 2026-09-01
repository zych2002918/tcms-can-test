"""2oo3 速度表决（Two-out-of-Three voting）—— 对标真实列控的速度传感器冗余。

真实列控（ATP/TCMS）通常配置多个速度传感器（雷达/测速电机/多普勒），
对同一物理量给出多个测量值。2oo3 表决：
    - 三个通道中至少两个一致（容差内）才采信该速度 —— 容忍单通道故障
    - 输出"表决速度"与"通道健康状态"
    - 低于 2 个通道一致 → 速度无效（触发降级/紧急制动决策）

设计原则（与 EBM 的 SIL2 双通道一致）：
    表决冗余度与安全等级挂钩——2oo3 能容忍单通道漂移/失效，且不会因
    单一通道噪声而误判（防误报），符合 SIL2 级"多数一致才动作"思想。
"""

# 通道索引（物理传感器通道）
CH_A, CH_B, CH_C = 0, 1, 2
VALID_CHANNELS = (CH_A, CH_B, CH_C)

# 容差：两通道读数差小于等于该值视为"一致"（km/h）
VOTE_TOLERANCE_KMH = 2.0

# 表决结果状态
VOTE_VALID = "valid"        # ≥2 通道一致，输出多数速度
VOTE_DIVERGENT = "divergent"  # 无 2 通道一致，速度无效
VOTE_FAILED = "failed"      # 通道故障数 ≥2，表决器失效


class SpeedVoter2oo3:
    """2oo3 速度表决器：三通道输入 → 表决速度 + 健康状态。

    用法：
        voter = SpeedVoter2oo3()
        ok, speed, state = voter.vote([80.0, 81.0, 200.0])
    """

    def __init__(self, tolerance_kmh: float = VOTE_TOLERANCE_KMH):
        self.tolerance_kmh = tolerance_kmh
        self._faulty: set[int] = set()   # 故障通道集合

    @property
    def faulty_channels(self) -> set[int]:
        """当前故障通道集合（副本）。"""
        return set(self._faulty)

    def mark_faulty(self, channel: int) -> None:
        """标记某通道故障（对应传感器失效/断线）。"""
        if channel not in VALID_CHANNELS:
            raise ValueError(f"未知通道: {channel}（合法 {VALID_CHANNELS}）")
        self._faulty.add(channel)

    def clear_fault(self, channel: int) -> None:
        """清除某通道故障标记（传感器恢复）。"""
        if channel not in VALID_CHANNELS:
            raise ValueError(f"未知通道: {channel}（合法 {VALID_CHANNELS}）")
        self._faulty.discard(channel)

    def vote(self, speeds: list[float]) -> tuple[bool, float, str]:
        """三通道速度表决。

        参数:
            speeds: 三个通道的速度读数（km/h）。故障通道读数忽略。
        返回:
            (是否有效, 表决速度, 状态)
            状态: valid / divergent / failed
        """
        if len(speeds) != 3:
            raise ValueError(f"需要 3 个通道读数，收到 {len(speeds)}")

        healthy = [s for i, s in enumerate(speeds) if i not in self._faulty]
        if len(healthy) < 2:
            # 可用通道不足 2 个：表决器失效
            return False, 0.0, VOTE_FAILED

        # 找多数一致组（容差内两两匹配）
        for i in range(len(healthy)):
            for j in range(i + 1, len(healthy)):
                if abs(healthy[i] - healthy[j]) <= self.tolerance_kmh:
                    agreed = (healthy[i] + healthy[j]) / 2.0
                    return True, agreed, VOTE_VALID

        return False, 0.0, VOTE_DIVERGENT
