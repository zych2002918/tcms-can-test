# 贡献指南（Contributing）

感谢你关注 TCMS-CAN-Test！本仓库是一个**列车控制与管理系统（TCMS）CAN 总线仿真与安全功能测试平台**，代码全部用 Python 实现，对标真实轨道交通规范（ISO 11898-1 / EN 50128 / CiA 301 / ETCS SRS）。

## 开发环境

```bash
# 创建虚拟环境（推荐）
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/macOS

# 安装全部依赖（测试/可视化/lint）
pip install -r requirements.txt
```

## 代码规范

- **Python >= 3.10**（使用 `int | None` 联合类型语法）
- 每个模块**中文 docstring**，说明"对标什么真实系统/规范 + 设计原则"
- 模块级常量集中定义（阈值/枚举），不散落魔法数
- 返回结构化结果（dict / (bool, reason)），不抛异常做业务分支
- 使用 ruff 静态检查（`ruff check tcms tests demo.py run.py scripts`）

## 测试要求

- 每个新模块配 `tests/test_<模块>.py`，覆盖正常/边界/异常路径
- **覆盖率达到 97%+**（CI 门禁 `--cov-fail-under=97`）
- 新增功能先写测试（测试驱动），再实现
- 全量回归：`python -m pytest tests/ -q`
- 属性测试（hypothesis）用于不变量验证，见 `tests/test_properties.py`

## 提交流程

1. 从 `main` 切分支：`git checkout -b feat/xxx`
2. 实现 + 测试 + 文档（README/QA 数字同步）
3. 本地验证全绿（测试/覆盖率/ruff/demo 冒烟）
4. 提交并推送，开 PR（用仓库的 PR 模板）
5. CI 全绿后合并

## 文档同步约定

项目所有数字（用例数/覆盖率/语句数）必须与代码**实测一致**：
- `README.md`：徽章、架构图、模块表、测试用例设计
- `TCMS项目深挖QA.md`：面试版 QA（每模块灵魂问答）
- `项目QA.md`：开发复盘版（设计决策/踩坑）
- `简历QA表.md`：简历数字口径出处

## 常见坑

- 文件必须 **UTF-8 无 BOM**（cantools 不认 BOM）
- Python 脚本内写 markdown 用真实 `\n`，不是字面 `\\n`
- PowerShell 编辑文件偶发 `ReplaceFileW EIO (Win32 1175)` 瞬态故障——直接重试
- `Set-Content -NoNewline` 会把多行文件连成一行——用 write 工具或 `Add-Content`
