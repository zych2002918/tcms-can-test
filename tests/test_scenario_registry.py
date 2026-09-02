"""场景注册表测试：仓库内 scenarios/*.yaml 直接作为用例参数化执行。

领域审计 P2-14 落地：数据资产必须被消费——新增/修改一个场景 YAML
即新增一个测试用例，场景中引用的故障键必须存在于统一故障字典
（tcms/faults.yaml，经 tcms/faultdb 校验），杜绝"场景引用幽灵故障"。
"""

from pathlib import Path

import pytest

from tcms import scenarios
from tcms.faultdb import load_fault_dictionary

SCENARIOS_DIR = Path(__file__).resolve().parent.parent / "scenarios"
DICT = load_fault_dictionary()

# 收集仓库内全部场景 YAML（作为参数化用例；无场景文件时显式跳过）
scenario_files = sorted(SCENARIOS_DIR.glob("*.yaml"))


def _scenario_id(path: Path) -> str:
    return path.stem


@pytest.mark.parametrize("path", scenario_files, ids=_scenario_id)
def test_scenario_registry_runs_clean(path):
    """每个场景 YAML 必须能完整执行且全部断言通过（all_passed）。"""
    report = scenarios.run_yaml(path)
    assert report["all_passed"] is True, f"场景 {path.name} 执行失败: {report}"
    assert report["ledger"]["total"] >= 1
    assert report["failed"] == 0


@pytest.mark.parametrize("path", scenario_files, ids=_scenario_id)
def test_scenario_faults_exist_in_dictionary(path):
    """场景引用的每个故障键必须存在于统一故障字典（FMEA 闭环）。"""
    text = path.read_text(encoding="utf-8")
    import re

    # 粗查：所有 fault: xxx 引用都应在字典中
    for m in re.finditer(r"fault:\s*([A-Za-z_][A-Za-z0-9_]*)", text):
        assert m.group(1) in DICT.keys(), (
            f"场景 {path.name} 引用未知故障 {m.group(1)!r}（字典无此键）"
        )


def test_scenario_registry_nonempty():
    """注册表非空守卫：scenarios/ 必须至少有一个场景。"""
    assert scenario_files, "scenarios/ 目录为空，注册表测试失去意义"
