"""2oo3 速度表决器测试：多数一致/单通道故障/表决失效/边界。"""

import pytest

from tcms import voting as vt

CH_A, CH_B, CH_C = vt.CH_A, vt.CH_B, vt.CH_C
VOTE_VALID, VOTE_DIVERGENT, VOTE_FAILED = vt.VOTE_VALID, vt.VOTE_DIVERGENT, vt.VOTE_FAILED


# ---- 基本表决 ----

@pytest.mark.parametrize("speeds,expected_valid,expected_speed", [
    ([80.0, 80.0, 80.0], True, 80.0),        # 三通道一致
    ([80.0, 81.0, 80.0], True, 80.5),        # 两两一致（容差内）取均值
    ([80.0, 82.0, 80.0], True, 81.0),        # 容差 2.0：80/82 匹配 → 均值 81
    ([80.0, 83.0, 86.0], False, 0.0),        # 两两差 >2：无一致组，发散
    ([80.0, 200.0, 200.0], True, 200.0),     # 两通道一致（80 为噪声）
    ([80.0, 81.0, 200.0], True, 80.5),       # 80/81 一致，200 为故障读数
])
def test_vote_basic(speeds, expected_valid, expected_speed):
    ok, speed, state = SpeedVoter().vote(speeds)
    assert ok is expected_valid
    if expected_valid:
        assert speed == expected_speed
        assert state == VOTE_VALID
    else:
        assert state == VOTE_DIVERGENT


def SpeedVoter():
    return vt.SpeedVoter2oo3()


def test_vote_divergent_state():
    ok, _, state = SpeedVoter().vote([10.0, 50.0, 90.0])
    assert not ok
    assert state == VOTE_DIVERGENT


# ---- 通道故障 ----

def test_mark_faulty_channel_ignored():
    voter = SpeedVoter()
    voter.mark_faulty(CH_B)
    ok, speed, state = voter.vote([80.0, 999.0, 80.0])   # B 故障读数被忽略
    assert ok and speed == 80.0 and state == VOTE_VALID


def test_two_faulty_channels_failed():
    voter = SpeedVoter()
    voter.mark_faulty(CH_A)
    voter.mark_faulty(CH_B)
    ok, _, state = voter.vote([80.0, 81.0, 80.0])
    assert not ok
    assert state == VOTE_FAILED


def test_clear_fault_restores():
    voter = SpeedVoter()
    voter.mark_faulty(CH_A)
    assert CH_A in voter.faulty_channels
    voter.clear_fault(CH_A)
    assert not voter.faulty_channels
    ok, speed, _ = voter.vote([80.0, 80.0, 80.0])
    assert ok and speed == 80.0


def test_invalid_channel_raises():
    voter = SpeedVoter()
    with pytest.raises(ValueError):
        voter.mark_faulty(5)
    with pytest.raises(ValueError):
        voter.clear_fault(-1)


# ---- 边界与异常 ----

def test_vote_requires_three_readings():
    with pytest.raises(ValueError):
        SpeedVoter().vote([80.0, 81.0])


def test_custom_tolerance():
    voter = vt.SpeedVoter2oo3(tolerance_kmh=5.0)
    ok, speed, _ = voter.vote([80.0, 84.0, 80.0])   # 差 4 < 容差 5：80/84 匹配取均值
    assert ok and speed == 82.0


def test_faulty_channels_property_is_copy():
    voter = SpeedVoter()
    voter.mark_faulty(CH_A)
    voter.faulty_channels.add(CH_B)   # 修改副本不影响内部
    assert voter.faulty_channels == {CH_A}
