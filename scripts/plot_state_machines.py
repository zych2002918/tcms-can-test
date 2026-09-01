"""生成状态机迁移图（EBM / ATP / CAN 错误状态机）—— 面试演示素材。

用法: python scripts/plot_state_machines.py
输出: docs/state_ebm.png / docs/state_atp.png / docs/state_errstate.png

可视化口径：
    - 每个状态一个节点（方框），迁移用带箭头曲线 + 触发条件标注
    - EBM：IDLE → BRAKE → RELEASED → IDLE + 自愈/FAULT/司机缓解序列
    - ATP：none → warning → sbi → ebi（阈值驱动，EBI 不可被覆盖）
    - 错误状态机：error-active → error-passive → bus-off → 恢复
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

from tcms import atp
from tcms import protocol as proto

OUT_DIR = "docs"


def setup_cjk_font() -> bool:
    for name in ("Microsoft YaHei", "SimHei", "Noto Sans CJK SC"):
        if name in matplotlib.font_manager.get_font_names():
            matplotlib.rcParams["font.sans-serif"] = [name, "DejaVu Sans"]
            matplotlib.rcParams["axes.unicode_minus"] = False
            return True
    return False


def _box(ax, x, y, text, color="#eef4ff", ec="#2f6fd0", fs=11):
    """绘制一个状态方框。"""
    box = FancyBboxPatch((x - 0.16, y - 0.09), 0.32, 0.18,
                         boxstyle="round,pad=0.01",
                         facecolor=color, edgecolor=ec, lw=1.6)
    ax.add_patch(box)
    ax.text(x, y, text, ha="center", va="center", fontsize=fs,
            fontweight="bold", color="#1a1a1a")


def _arrow(ax, x1, y1, x2, y2, label, color="#555555", ls="-",
           label_dx=0.0, label_dy=0.04, fs=8.5, rad=0.0, lw=1.4):
    """绘制一条带条件标注的迁移箭头。"""
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>",
                                 mutation_scale=14, color=color,
                                 linestyle=ls, lw=lw,
                                 connectionstyle=f"arc3,rad={rad}"))
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    ax.text(mx + label_dx, my + label_dy, label, ha="center", va="center",
            fontsize=fs, color=color)


def plot_ebm(cjk: bool):
    """EBM 六态迁移图（含司机缓解序列与自愈/FAULT）。"""
    fig, ax = plt.subplots(figsize=(11, 6.2))
    # 四行布局：主链（IDLE→BRAKE→RELEASED→IDLE）+ 故障/自愈/缓解分支
    _box(ax, 0.0, 1.0, "IDLE", color="#eaf7ea", ec="#2e9e44")
    _box(ax, 1.0, 1.0, "BRAKE", color="#ffeaea", ec="#d62728")
    _box(ax, 2.0, 1.0, "RELEASED", color="#eaf7ea", ec="#2e9e44")
    _box(ax, 3.0, 1.0, "FAULT", color="#fff3e0", ec="#ff7f0e")
    _box(ax, 1.0, 0.0, "WAIT_HANDLE_ZERO", color="#f3e8ff", ec="#8b5cf6")
    _box(ax, 2.0, 0.0, "WAIT_RELEASE_BTN", color="#f3e8ff", ec="#8b5cf6")

    _arrow(ax, 0.12, 1.0, 0.82, 1.0,
           "trigger(适用原因)\n超速/开门/ATO故障…", color="#d62728",
           label_dy=0.08)
    _arrow(ax, 1.18, 1.0, 1.82, 1.0,
           "零速(≤0.5km/h)\n且原因全部消失", color="#2e9e44",
           label_dy=0.08)
    _arrow(ax, 2.18, 1.0, 2.82, 1.0,
           "reset() 远程/人工复位", color="#2e9e44",
           label_dy=0.08)
    _arrow(ax, 0.82, 0.94, 1.0, 0.1, "self_heal(限1次)", color="#2e9e44",
           rad=0.25, label_dx=-0.1)
    _arrow(ax, 1.0, 0.12, 0.1, 0.94, "自愈超限 → FAULT", color="#ff7f0e",
           rad=0.25, label_dx=0.15)
    _arrow(ax, 1.08, 1.0, 0.92, 0.1, "prepare_release\n手柄回零", color="#8b5cf6",
           rad=-0.25, label_dx=0.12)
    _arrow(ax, 1.12, 0.0, 1.88, 0.0, "hold_release_button\n(<3s 可重试)",
           color="#8b5cf6", label_dy=-0.09)
    _arrow(ax, 1.88, 0.08, 0.12, 0.94, "保持≥3s\n缓解成功", color="#2e9e44",
           rad=-0.3, label_dx=0.05)
    _arrow(ax, 2.82, 1.06, 3.0, 1.0, "", color="#555555", lw=0)

    ax.set_xlim(-0.35, 3.35)
    ax.set_ylim(-0.55, 1.5)
    ax.axis("off")
    if cjk:
        ax.set_title("EBM 紧急制动管理状态机（六态：触发→缓解→复位 + 司机操作序列）")
    else:
        ax.set_title("EBM emergency brake state machine (6 states)")
    fig.tight_layout()
    out = os.path.join(OUT_DIR, "state_ebm.png")
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"已生成: {out}")


def plot_atp(cjk: bool):
    """ATP 速度监督分级迁移图（none→warning→sbi→ebi）。"""
    fig, ax = plt.subplots(figsize=(10.5, 5.2))
    _box(ax, 0.0, 1.0, "none\n(正常)", color="#eaf7ea", ec="#2e9e44")
    _box(ax, 1.0, 1.0, "warning\n(告警)", color="#fff8e1", ec="#f5a623")
    _box(ax, 2.0, 1.0, "sbi\n(常用制动)", color="#fff3e0", ec="#ff7f0e")
    _box(ax, 3.0, 1.0, "ebi\n(紧急制动)", color="#ffeaea", ec="#d62728")

    _arrow(ax, 0.15, 1.0, 0.82, 1.0, f"v > 限速-{atp.WARNING_OFFSET_KMH:.0f}",
           color="#f5a623", label_dy=0.08)
    _arrow(ax, 1.18, 1.0, 1.82, 1.0, f"v > 限速-{atp.SBI_OFFSET_KMH:.0f}",
           color="#ff7f0e", label_dy=0.08)
    _arrow(ax, 2.18, 1.0, 2.82, 1.0, f"v > 限速-{atp.EBI_OFFSET_KMH:.0f}",
           color="#d62728", label_dy=0.08)
    _arrow(ax, 0.88, 0.92, 0.12, 0.92, "降速回落", color="#2e9e44",
           label_dy=-0.06, lw=1.1)
    _arrow(ax, 1.88, 0.92, 1.12, 0.92, "降速回落", color="#2e9e44",
           label_dy=-0.06, lw=1.1)

    ax.text(2.5, 0.35,
            "EBI 是安全底线：任何模式下不可被覆盖\n（对齐 EBM 的 CRITICAL 处置）",
            ha="center", fontsize=9.5, color="#d62728",
            bbox=dict(boxstyle="round", facecolor="#fff5f5", ec="#d62728"))
    ax.set_xlim(-0.35, 3.35)
    ax.set_ylim(0.0, 1.5)
    ax.axis("off")
    if cjk:
        ax.set_title("ATP 速度监督分级（Warning/SBI/EBI 三级递进）")
    else:
        ax.set_title("ATP speed supervision levels (warning / SBI / EBI)")
    fig.tight_layout()
    out = os.path.join(OUT_DIR, "state_atp.png")
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"已生成: {out}")


def plot_errstate(cjk: bool):
    """CAN 错误状态机迁移图（ISO 11898-1）。"""
    fig, ax = plt.subplots(figsize=(10.5, 5.2))
    _box(ax, 0.0, 1.0, f"error-active\n(TEC/REC ≤ {127})", color="#eaf7ea",
         ec="#2e9e44")
    _box(ax, 1.5, 1.0, f"error-passive\n(TEC/REC ≥ {128})", color="#fff8e1",
         ec="#f5a623")
    _box(ax, 3.0, 1.0, f"bus-off\n(TEC = {256})", color="#ffeaea", ec="#d62728")

    _arrow(ax, 0.15, 1.0, 1.32, 1.0, "TEC/REC ≥ 128\n(错误计数累计)",
           color="#f5a623", label_dy=0.08)
    _arrow(ax, 1.68, 1.0, 2.82, 1.0, "TEC ≥ 256\n(发送错误连续)",
           color="#d62728", label_dy=0.08)
    _arrow(ax, 2.88, 0.92, 0.12, 0.92, "128 位总线空闲\n自动恢复 error-active",
           color="#2e9e44", label_dy=-0.06, lw=1.1)
    _arrow(ax, 1.38, 0.92, 0.12, 0.92, "错误计数回落", color="#2e9e44",
           label_dy=-0.06, lw=1.1)

    ax.text(1.5, 0.3, "bus-off 期间节点离线：不参与收发\n（隔离故障节点，保护总线）",
            ha="center", fontsize=9.5, color="#d62728",
            bbox=dict(boxstyle="round", facecolor="#fff5f5", ec="#d62728"))
    ax.set_xlim(-0.35, 3.35)
    ax.set_ylim(0.0, 1.5)
    ax.axis("off")
    if cjk:
        ax.set_title("CAN 错误状态机（ISO 11898-1：Error-Active / Passive / Bus-Off）")
    else:
        ax.set_title("CAN error state machine (ISO 11898-1)")
    fig.tight_layout()
    out = os.path.join(OUT_DIR, "state_errstate.png")
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"已生成: {out}")


def plot_door(cjk: bool):
    """车门控制状态机迁移图（Closed/Open/Fault/Unknown + 门-车联锁）。"""
    fig, ax = plt.subplots(figsize=(10.5, 5.6))
    _box(ax, 0.0, 1.0, "Closed\n(关闭)", color="#eaf7ea", ec="#2e9e44")
    _box(ax, 1.5, 1.0, "Open\n(打开)", color="#fff8e1", ec="#f5a623")
    _box(ax, 3.0, 1.0, "Fault\n(故障)", color="#ffeaea", ec="#d62728")
    _box(ax, 3.0, 0.0, "Unknown\n(未知)", color="#e8e8e8", ec="#666666")

    _arrow(ax, 0.15, 1.0, 1.32, 1.0, "开门指令\n(DoorOpenPermit)",
           color="#2e9e44", label_dy=0.08)
    _arrow(ax, 1.68, 1.0, 2.82, 1.0, "关门指令\n(AllDoorsClosed)",
           color="#2e9e44", label_dy=0.08)
    _arrow(ax, 1.62, 0.92, 2.88, 0.1, "故障(卡滞/回路异常)",
           color="#d62728", rad=0.2, label_dx=0.05, label_dy=0.1)
    _arrow(ax, 3.12, 0.92, 0.12, 0.92, "维修后复位", color="#2e9e44",
           label_dy=-0.06, lw=1.1)
    _arrow(ax, 0.12, 0.94, 0.88, 0.1, "门状态异常→Fault", color="#d62728",
           rad=0.2, label_dx=-0.2)
    _arrow(ax, 1.38, 0.94, 2.88, 0.06, "反馈丢失→Unknown", color="#666666",
           rad=0.15, label_dx=0.05)

    ax.text(1.5, -0.55,
            "门-车联锁（interlocks.door_motion_conflict）：移动中(speed > 0.5km/h)\n"
            "任一车门 Open/Fault 即违规 → 触发紧急制动。安全原则：故障门按未关闭处理。",
            ha="center", fontsize=9.5, color="#d62728",
            bbox=dict(boxstyle="round", facecolor="#fff5f5", ec="#d62728"))
    ax.set_xlim(-0.35, 3.55)
    ax.set_ylim(-0.95, 1.5)
    ax.axis("off")
    if cjk:
        ax.set_title("车门控制状态机（Closed/Open/Fault/Unknown + 门-车联锁）")
    else:
        ax.set_title("Door control state machine (Closed / Open / Fault / Unknown)")
    fig.tight_layout()
    out = os.path.join(OUT_DIR, "state_door.png")
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"已生成: {out}")


def plot_overspeed(cjk: bool):
    """超速防护状态机（安全速度链 → 超速 → 紧急制动联动）。"""
    fig, ax = plt.subplots(figsize=(11, 5.6))
    _box(ax, 0.0, 1.0, "safe\n(安全区)", color="#eaf7ea", ec="#2e9e44")
    _box(ax, 1.0, 1.0, "warning\n(告警)", color="#fff8e1", ec="#f5a623")
    _box(ax, 2.0, 1.0, "overspeed\n(超速)", color="#fff3e0", ec="#ff7f0e")
    _box(ax, 3.0, 1.0, "EBM\n(紧急制动)", color="#ffeaea", ec="#d62728")

    _arrow(ax, 0.15, 1.0, 0.82, 1.0, f"v > {proto.OVERSPEED_LIMIT_KMH:.0f}km/h",
           color="#f5a623", label_dy=0.08)
    _arrow(ax, 1.18, 1.0, 1.82, 1.0, "v > 限速(160)", color="#ff7f0e",
           label_dy=0.08)
    _arrow(ax, 2.18, 1.0, 2.82, 1.0, "v ≥ EBI\n(overspeed_trigger)",
           color="#d62728", label_dy=0.08)
    _arrow(ax, 0.88, 0.92, 0.12, 0.92, "降速回落", color="#2e9e44",
           label_dy=-0.06, lw=1.1)
    _arrow(ax, 1.88, 0.92, 1.12, 0.92, "降速回落", color="#2e9e44",
           label_dy=-0.06, lw=1.1)
    _arrow(ax, 2.88, 0.92, 0.12, 0.92, "零速+原因消失\n(ebm.release_condition)",
           color="#2e9e44", label_dy=-0.06, lw=1.1)

    ax.text(1.5, 0.3,
            "超速是 EBM 的 8 类触发原因之一：interlocks.overspeed_trigger()\n"
            "判定 → emergency_brake_decision() → ebm.trigger(\"overspeed\")\n"
            "缓解闭环：零速(≤0.5km/h) + 有效速度信号 + 原因消失",
            ha="center", fontsize=9.5, color="#d62728",
            bbox=dict(boxstyle="round", facecolor="#fff5f5", ec="#d62728"))
    ax.set_xlim(-0.35, 3.55)
    ax.set_ylim(0.0, 1.5)
    ax.axis("off")
    if cjk:
        ax.set_title("超速防护状态机（安全速度链 → 超速 → 紧急制动联动）")
    else:
        ax.set_title("Overspeed protection state machine (safe → overspeed → EBM)")
    fig.tight_layout()
    out = os.path.join(OUT_DIR, "state_overspeed.png")
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"已生成: {out}")


if __name__ == "__main__":
    os.makedirs(OUT_DIR, exist_ok=True)
    cjk_ok = setup_cjk_font()
    plot_ebm(cjk_ok)
    plot_atp(cjk_ok)
    plot_errstate(cjk_ok)
    plot_door(cjk_ok)
    plot_overspeed(cjk_ok)
    print("状态机迁移图生成完毕。")
