"""TCMS-CAN-Test 一键入口：分层测试 + 多格式报告 + 真实日志回放。

用法:
    python run.py                     # 全量测试 + HTML 报告（默认）
    python run.py --level smoke       # 冒烟层（核心安全路径，<1s）
    python run.py -k door             # 按关键字筛选用例（透传 pytest -k）
    python run.py --junitxml          # 额外输出 JUnit XML（CI/工具链）
    python run.py --allure            # 同时生成 Allure 结果（allure-results/）
    python run.py --replay demo.asc   # 用完整回放链驱动 .asc 日志并出报告
"""

import argparse
import subprocess
import sys


def _version() -> str:
    """从包元数据读版本（与 pyproject 单源；未安装时回退仓库常量）。"""
    try:
        from importlib.metadata import version

        return version("tcms-can-test")
    except Exception:
        return "1.7.0"  # 与 pyproject.toml 保持同步的兜底


def replay_log(path: str) -> int:
    """回放 .asc 日志：ReplayChain 完整链（联锁/ATP/看门狗/EBM → 告警断言）。"""
    from tcms import replay

    chain = replay.ReplayChain.from_asc(path)
    report = chain.run()
    print(f"[replay] {path}: {report['frames']} 帧回放完成")
    print(
        f"[replay] EBM 状态: {report['ebm_state']}"
        f"{'（已触发紧急制动）' if report['ebm_triggered'] else ''}"
    )
    print(f"[replay] 看门狗: {report['watchdog_states']}")
    if report["alerts"]:
        print(f"[replay] 告警 {len(report['alerts'])} 条:")
        for a in report["alerts"]:
            print(f"  t={a['ts']:.3f}s {a['kind']}: {a['detail']}")
    else:
        print("[replay] 无告警（日志期间未触发任何安全事件）")
    print(f"[replay] 告警类别: {report['alert_kinds']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="TCMS CAN 自动化测试入口")
    parser.add_argument("--version", action="version", version=f"tcms-can-test {_version()}")
    parser.add_argument(
        "--level",
        choices=("smoke", "full"),
        default="full",
        help="测试层级：smoke=冒烟层（核心安全路径）；full=全量回归（默认）",
    )
    parser.add_argument("--allure", action="store_true", help="生成 Allure 结果目录")
    parser.add_argument("--no-report", action="store_true", help="不生成 HTML 报告")
    parser.add_argument("--coverage", action="store_true", help="生成代码覆盖率报告（htmlcov/）")
    parser.add_argument(
        "--junitxml", action="store_true", help="额外输出 JUnit XML（reports/junit.xml）"
    )
    parser.add_argument("-k", dest="keyword", default="", help="按用例名关键字筛选")
    parser.add_argument(
        "--replay",
        metavar="ASC_FILE",
        default=None,
        help="回放真实 CAN 日志（.asc）——用完整回放链驱动并输出报告",
    )
    args = parser.parse_args()

    if args.replay:
        return replay_log(args.replay)

    cmd = [sys.executable, "-m", "pytest", "tests/", "-q"]
    if args.level == "smoke":
        cmd += ["-m", "smoke"]
    if args.keyword:
        cmd += ["-k", args.keyword]
    if not args.no_report:
        cmd += ["--html=report.html", "--self-contained-html"]
    if args.allure:
        cmd += ["--alluredir=allure-results"]
    if args.junitxml:
        cmd += ["--junitxml=reports/junit.xml"]
    if args.coverage:
        cmd += ["--cov=tcms", "--cov-report=term", "--cov-report=html:htmlcov"]

    print(" ".join(cmd))
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
