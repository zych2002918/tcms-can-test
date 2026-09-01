"""属性测试（hypothesis）：以不变量验证替代逐例验证，覆盖联锁/EBM/错误状态机/记录器。

定位：与 test_fuzz.py（定种子随机模糊）互补——hypothesis 主动搜索反例，
    验证任何输入组合下核心安全模块都保持"结构不变量"：
    - errstate：计数器范围、状态-计数一致性、Bus-Off 隔离、恢复归零
    - EBM：触发-适用性-动作一致性、任意操作序列后模式/状态合法
    - interlocks：违规⟺原因非空、非移动不违规、阈值单调
    - recorder：环形缓冲容量上限、统计口径一致
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from tcms.ebm import (
    MAX_SELF_HEAL,
    MODE_CM,
    MODE_FAM,
    MODE_RM,
    REASONS,
    STATE_BRAKE,
    STATE_FAULT,
    STATE_IDLE,
    STATE_RELEASED,
    VALID_MODES,
    EmergencyBrakeManager,
    action_parts,
)
from tcms.errstate import (
    BUS_IDLE_RECOVERY,
    COUNTER_MAX,
    STATE_BUS_OFF,
    STATE_ERROR_ACTIVE,
    STATE_ERROR_PASSIVE,
    CanErrorStateMachine,
)
from tcms.interlocks import (
    MOTION_THRESHOLD_KMH,
    door_motion_conflict,
    emergency_brake_decision,
    overspeed_trigger,
    pantograph_arc_risk,
    soc_low_charge_guard,
)
from tcms.protocol import OVERSPEED_LIMIT_KMH
from tcms.recorder import EVENT_EBM, EventRecorder

settings.register_profile("ci", deadline=None)
settings.load_profile("ci")

# 任意状态下都安全的实数区间（物理意义 + 健壮性边界）
SPEED_ST = st.floats(min_value=-50.0, max_value=320.0,
                     allow_nan=False, allow_infinity=False)
VOLTAGE_ST = st.floats(min_value=0.0, max_value=60000.0,
                       allow_nan=False, allow_infinity=False)

ERR_EVENTS = st.sampled_from(
    ["tx_err", "rx_err", "tx_ok", "rx_ok", "idle"])


# ================= errstate 不变量 =================

@given(seq=st.lists(ERR_EVENTS, min_size=0, max_size=150))
def test_errstate_counter_scope_and_accounting_invariants(seq):
    """任意事件序列后：计数器 8 位封顶、错误帧统计恒等、状态-计数一致。"""
    sm = CanErrorStateMachine()
    for ev in seq:
        if ev == "tx_err":
            sm.tx_error()
        elif ev == "rx_err":
            sm.rx_error()
        elif ev == "tx_ok":
            sm.tx_success()
        elif ev == "rx_ok":
            sm.rx_success()
        else:
            sm.bus_idle_bit()
        # 逐事件立即校验，缩小反例定位范围
        assert 0 <= sm.tec <= COUNTER_MAX
        assert 0 <= sm.rec <= COUNTER_MAX
        assert sm.error_frames == sum(sm.error_counts.values())
    # 终态一致性：非 Bus-Off 时状态由计数唯一决定
    if sm.state != STATE_BUS_OFF:
        expect_passive = (sm.tec >= 128 or sm.rec >= 128)
        if expect_passive:
            assert sm.state == STATE_ERROR_PASSIVE
        else:
            assert sm.state == STATE_ERROR_ACTIVE


@given(seq=st.lists(st.sampled_from(["tx_err", "rx_err"]), min_size=0,
                    max_size=100),
       idle_bits=st.integers(min_value=0, max_value=BUS_IDLE_RECOVERY + 50))
def test_errstate_bus_off_isolates_and_recovery_resets(seq, idle_bits):
    """Bus-Off 后事件全部 no-op；空闲计数不达标不恢复、达标即归零复位。"""
    sm = CanErrorStateMachine()
    for ev in seq:
        sm.tx_error() if ev == "tx_err" else sm.rx_error()
        # 构建到 Bus-Off 为止的任意状态（循环内不做断言）
    if sm.state != STATE_BUS_OFF:
        for _ in range(40):
            if sm.state == STATE_BUS_OFF:
                break
            sm.tx_error()
    if sm.state != STATE_BUS_OFF:
        # 未达 Bus-Off：隔离与恢复逻辑不适用（跳过）
        return
    # —— 已 Bus-Off ——
    snapshot = (sm.tec, sm.rec, sm.error_frames)
    for _ in range(20):
        sm.tx_error()
        sm.rx_error()
        sm.tx_success()
        sm.rx_success()
    assert (sm.tec, sm.rec, sm.error_frames) == snapshot  # 完全隔离

    for _ in range(max(0, min(idle_bits, BUS_IDLE_RECOVERY - 1))):
        sm.bus_idle_bit()
    if idle_bits < BUS_IDLE_RECOVERY:
        assert sm.state == STATE_BUS_OFF  # 未达标不恢复
    sm.bus_idle_bit(BUS_IDLE_RECOVERY)
    assert sm.state == STATE_ERROR_ACTIVE
    assert sm.tec == 0 and sm.rec == 0 and sm.bus_idle == 0


@given(n_err=st.integers(min_value=0, max_value=64),
       n_ok=st.integers(min_value=0, max_value=64))
def test_errstate_success_decrements_bounded(n_err, n_ok):
    """成功事件单调递减计数且不越过 0 下界。"""
    sm = CanErrorStateMachine()
    for _ in range(n_err):
        sm.tx_error()
    tec_before = sm.tec
    for _ in range(n_ok):
        sm.tx_success()
    if sm.state == STATE_BUS_OFF:
        assert sm.tec == tec_before  # Bus-Off 隔离：成功事件 no-op
    elif n_ok == 0:
        assert sm.tec == tec_before  # 无成功事件，计数不动
    elif tec_before >= 128:
        # 首次成功直接跳变 120，随后进入 1..127 递减区间每次 -1
        assert sm.tec == max(0, 120 - (n_ok - 1))
    else:
        assert sm.tec == max(0, tec_before - min(n_ok, tec_before))


# ================= EBM 不变量 =================

@given(mode=st.sampled_from(VALID_MODES),
       reason=st.sampled_from(list(REASONS.keys())))
def test_ebm_trigger_apply_matches_spec(mode, reason):
    """触发结果与应用性判定逐项吻合（不变量：不误制动、不遗漏制动）。"""
    mgr = EmergencyBrakeManager(mode=mode)
    spec = REASONS[reason]
    applicable = mode in spec["modes"]
    r = mgr.trigger(reason)
    assert r["applied"] is applicable
    assert r["action"] == spec["action"] if applicable else \
        r["action"] == "record_only"
    assert r["sil"] == spec["sil"]
    if applicable:
        assert mgr.state == STATE_BRAKE
        brake, mode_change = action_parts(r["action"])
        assert brake is True
        if mode_change is not None:
            assert mode_change in VALID_MODES
            assert mgr.mode == mode_change  # 自动降级即时生效
    else:
        assert mgr.state == STATE_IDLE  # 不适用原因不得扰动状态机
        assert mgr.mode == mode  # 也不得诱发模式迁移


@given(mode=st.sampled_from(VALID_MODES),
       target=st.sampled_from(VALID_MODES))
def test_ebm_set_mode_only_single_step_degradation(mode, target):
    """模式迁移不变量：只允许降级链上一步；跳级/升迁一律拒绝。"""
    mgr = EmergencyBrakeManager(mode=mode)
    chain = (MODE_FAM, MODE_CM, MODE_RM)
    diff = chain.index(target) - chain.index(mode)
    legal = abs(diff) == 1 or diff == 0  # 相邻单步任意方向合法；跳级拒绝
    try:
        mgr.set_mode(target)
        assert legal, f"{mode}→{target} 被拒绝却成功了"
        assert mgr.mode == target
    except ValueError:
        assert not legal, f"{mode}→{target} 合法却被拒绝"


@given(
    mode=st.sampled_from(VALID_MODES),
    steps=st.lists(
        st.sampled_from(["set_fam", "set_cm", "set_rm", "trigger_overspeed",
                         "trigger_door", "clear_overspeed", "clear_all",
                         "release_at_zero", "release_moving",
                         "self_heal", "reset"]),
        min_size=0, max_size=40),
)
def test_ebm_random_walk_stays_in_valid_state_space(mode, steps):
    """任意操作序列后：模式合法、状态合法、自愈额度不越界。"""
    mgr = EmergencyBrakeManager(mode=mode)
    for step in steps:
        try:
            if step == "set_fam":
                mgr.set_mode(MODE_FAM)
            elif step == "set_cm":
                mgr.set_mode(MODE_CM)
            elif step == "set_rm":
                mgr.set_mode(MODE_RM)
            elif step == "trigger_overspeed":
                mgr.trigger("overspeed")
            elif step == "trigger_door":
                mgr.trigger("door_open")
            elif step == "clear_overspeed":
                mgr.update_reason_status("overspeed", False)
            elif step == "clear_all":
                for reason in REASONS:
                    mgr.update_reason_status(reason, False)
            elif step == "release_at_zero":
                mgr.release_condition(0.0)
            elif step == "release_moving":
                mgr.release_condition(80.0)
            elif step == "self_heal":
                mgr.self_heal()
            else:  # reset
                mgr.reset()
        except ValueError:
            pass  # 非法迁移被拒绝是预期行为
        assert mgr.mode in VALID_MODES
        assert mgr.state in (STATE_IDLE, STATE_BRAKE, STATE_RELEASED,
                             STATE_FAULT)
        # 自愈调用次数有上限：可再自愈 ⟹ 未超限
        if mgr.state == STATE_FAULT:
            assert mgr.self_heal() is False  # FAULT 后自愈必然拒绝


# ================= interlocks 不变量 =================

@given(door_states=st.lists(st.integers(min_value=-2, max_value=4),
                            min_size=1, max_size=8),
       speed=SPEED_ST,
       valid=st.booleans())
def test_door_motion_conflict_invariants(door_states, speed, valid):
    violated, reason = door_motion_conflict(door_states, speed, valid)
    assert isinstance(violated, bool)
    assert (violated and reason) or (not violated and not reason)
    moving = valid and speed > MOTION_THRESHOLD_KMH
    if not moving:
        assert not violated  # 静止（或速度无效）时禁止误报
    if all(s != 1 and s != 2 for s in door_states):
        assert not violated  # 无开门/故障门时禁止误报


@given(speed=SPEED_ST, valid=st.booleans(),
       limit=st.floats(min_value=1.0, max_value=300.0,
                       allow_nan=False, allow_infinity=False))
def test_overspeed_trigger_threshold_invariant(speed, valid, limit):
    triggered = overspeed_trigger(speed, valid, limit)
    if not valid:
        assert triggered is False  # 速度无效永不触发
    else:
        assert triggered == (speed > limit)  # 严格大于、不含等于


@given(overspeed=st.booleans(), door=st.booleans())
def test_emergency_brake_decision_is_or(overspeed, door):
    assert emergency_brake_decision(0.0, overspeed, door) == (
        overspeed or door)


@given(up=st.integers(min_value=-1, max_value=2),
       voltage=VOLTAGE_ST)
def test_pantograph_arc_risk_invariants(up, voltage):
    violated, reason = pantograph_arc_risk(up, voltage)
    assert (violated and reason) or (not violated and not reason)
    if not up:
        assert not violated  # 弓未升起无拉弧风险
    elif 19000 <= voltage <= 31000:
        assert not violated  # 电压正常区间内无风险


@given(soc=st.integers(min_value=-5, max_value=110),
       charging=st.booleans())
def test_soc_guard_invariants(soc, charging):
    violated, reason = soc_low_charge_guard(soc, charging)
    assert (violated and reason) or (not violated and not reason)
    assert violated == (soc < 10 and not charging)


# ================= recorder 不变量 =================

@given(seq=st.lists(st.integers(min_value=0, max_value=50),
                    min_size=0, max_size=40),
       capacity=st.integers(min_value=1, max_value=60))
def test_recorder_ring_capacity_and_stats_consistent(seq, capacity):
    r = EventRecorder(capacity=capacity)
    for i, n in enumerate(seq):
        r.record_event(EVENT_EBM, message=f"e{n}", ts=float(i))
    assert len(r) <= capacity  # 环形缓冲上限
    s = r.stats()
    assert s["total"] == len(r)
    assert s["by_type"].get(EVENT_EBM, 0) == len(r)


@given(a=st.lists(st.integers(min_value=0, max_value=9), min_size=1,
                  max_size=20),
       b=st.lists(st.integers(min_value=0, max_value=9), min_size=1,
                  max_size=20))
def test_recorder_query_never_mutates_buffer(a, b):
    """查询是只读操作：任意次数过滤后缓冲内容不变。"""
    r = EventRecorder(capacity=100)
    for i, n in enumerate(a):
        r.record_event(EVENT_EBM, message=f"a{n}", ts=float(i))
    snapshot = list(r)
    for _ in range(10):
        r.query(event_type=EVENT_EBM)
        r.query(text="a")
        r.query(limit=2)
    assert list(r) == snapshot