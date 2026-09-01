"""TCMS-CAN-Test 一键入口：运行全部测试并生成 HTML 报告。

用法:
    python run.py                 # 运行全部测试 + 生成 report.html
    python run.py --allure        # 同时生成 Allure 结果（allure-results/）
    python run.py -k door         # 按关键字筛选用例（透传 pytest -k）
    python run.py --no-report     # 只跑测试不生成报告
    python run.py --replay x.asc  # 回放真实 CAN 日志（.asc 格式）并统计
"""

import argparse
import subprocess
import sys


def replay_log(path: str) -> int:
    """回放 .asc 日志：解析 → 统计 → 输出摘要。"""
    from tcms import canlog

    frames = canlog.parse_asc_file(path)
    if not frames:
        print(f"[replay] {path}: 无有效帧（检查 .asc 格式）")
        return 2
    stats = canlog.log_stats(frames)
    print(f"[replay] {path}: {stats['frames']} 帧, "
          f"时长 {stats['duration_s']:.3f}s, "
          f"{len(stats['ids'])} 个仲裁 ID")
    for arb_id in stats["ids"]:
        print(f"  0x{arb_id:x}: {stats['by_id'][hex(arb_id)]} 帧")
    # 可选：接仿真回放（interlocks/watchdogs 处理每帧）

    speed_kmh = 0.0
    overrun = 0
    for f in frames:
        # 简化的业务回放：超速监督（0x200 = VehicleSpeed 信号）
        if f["arb_id"] == 0x200 and len(f["data"]) >= 2:
            speed_kmh = f["data"][0] + f["data"][1] / 10.0
        if speed_kmh > 160.0:
            overrun += 1
    print(f"[replay] 业务回放: 最高速度 {speed_kmh:.1f} km/h, "
          f"超速样本 {overrun} 次")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="TCMS CAN 自动化测试入口")
    parser.add_argument("--allure", action="store_true", help="生成 Allure 结果目录")
    parser.add_argument("--no-report", action="store_true", help="不生成 HTML 报告")
    parser.add_argument("--coverage", action="store_true", help="生成代码覆盖率报告（htmlcov/）")
    parser.add_argument("-k", dest="keyword", default="", help="按用例名关键字筛选")
    parser.add_argument("--replay", metavar="ASC_FILE", default=None,
                        help="回放真实 CAN 日志（.asc 格式）并输出统计")
    args = parser.parse_args()

    if args.replay:
        return replay_log(args.replay)

    cmd = [sys.executable, "-m", "pytest", "tests/", "-q"]
    if args.keyword:
        cmd += ["-k", args.keyword]
    if not args.no_report:
        cmd += ["--html=report.html", "--self-contained-html"]
    if args.allure:
        cmd += ["--alluredir=allure-results"]
    if args.coverage:
        cmd += ["--cov=tcms", "--cov-report=term", "--cov-report=html:htmlcov"]

    print(" ".join(cmd))
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
