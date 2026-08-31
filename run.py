"""TCMS-CAN-Test 一键入口：运行全部测试并生成 HTML 报告。

用法:
    python run.py                 # 运行全部测试 + 生成 report.html
    python run.py --allure        # 同时生成 Allure 结果（allure-results/）
    python run.py -k door         # 按关键字筛选用例（透传 pytest -k）
    python run.py --no-report     # 只跑测试不生成报告
"""

import argparse
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="TCMS CAN 自动化测试入口")
    parser.add_argument("--allure", action="store_true", help="生成 Allure 结果目录")
    parser.add_argument("--no-report", action="store_true", help="不生成 HTML 报告")
    parser.add_argument("--coverage", action="store_true", help="生成代码覆盖率报告（htmlcov/）")
    parser.add_argument("-k", dest="keyword", default="", help="按用例名关键字筛选")
    args = parser.parse_args()

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