# 事务 0009 结果（Result）

> 编码者（Coder）产出。记录变更文件、测试/验证、结果、局限与后续建议。

---

## 1. 变更的文件

**新建（5）：**

| 文件 | 内容 |
|---|---|
| `evoagent/evolution/loop.py` | `EvolutionLoop`：主循环编排（收集低分 real trace → 分组 → 提炼 → 演化 → 验证 → 更新注册表） |
| `evoagent/cli.py` | `main`（run/evolve/bench/list）+ `build_components` 组合根 |
| `README.md` | 上手文档（说明 / 架构 / 快速上手 / 前置说明 / 指向设计） |
| `tests/test_loop.py` | 6 用例（全链路 / 防污染 / 边界） |
| `tests/test_cli.py` | 5 用例（四子命令分发 / retrieval_fallback 映射） |

**修改（3）：**

| 文件 | 变更 |
|---|---|
| `evoagent/config.py` | 追加 `MIN_EVOLUTION_SAMPLES=1` |
| `pyproject.toml` | `packages=["evoagent"]` → `[tool.setuptools.packages.find] include=["evoagent*"]` |
| `docs/system_design.md` | §4 回补 `Task` dataclass 定义（仅此一处） |

## 2. 执行的验证命令及输出摘要

**命令 1：包导入**
```
python -c "import evoagent.cli, evoagent.evolution.loop"
```
输出：`import ok`

**命令 2：定向测试**
```
python -m pytest tests/test_loop.py tests/test_cli.py -v
```
输出摘要：`collected 11 items`，**`11 passed in 0.37s`**。

**命令 3：全量回归**
```
python -m pytest -v
```
输出摘要：`collected 126 items`，**`126 passed in 5.92s`**（既有 115 项无回归、无失败、无 skipped）。

**命令 4：SQL 唯一性人工复核**
```
grep -rn "import sqlite3" evoagent/
```
结果：真实 `import sqlite3` 语句仅 `evoagent/storage.py:13`；`loop.py`/`cli.py` 无。

**命令 5：打包验证（§10 必记）**
```
python -m venv <tmp>/evoagent-venv --system-site-packages
<tmp>/evoagent-venv/Scripts/python -m pip install . --no-deps --no-build-isolation
<tmp>/evoagent-venv/Scripts/python -c "import evoagent.skills.registry, evoagent.execution.executor, evoagent.eval.benchmark, evoagent.evolution.validator"
```
输出：`subpackages import ok`（四子包 install 后可导入）。

**命令 6：设计回补核对**
`git diff docs/system_design.md` → 仅 §4 一处新增 `Task` 代码块，字段与 `models.py` 一致（`task`/`task_source`，无 `task_id`）。

**命令 7：包发现核对**
`find_packages(include=["evoagent*"])` → `['evoagent', 'evoagent.eval', 'evoagent.evolution', 'evoagent.execution', 'evoagent.skills']`。

## 3. 验证结果

**验收标准逐条：**

1. ✅ `config.py` 新增 `MIN_EVOLUTION_SAMPLES == 1`；既有常量不变。
2. ✅ `EvolutionLoop`：全链路跑通；`task_source=="benchmark"`/`error_type=="infra"` 被排除；样本不足跳过；单 skill 异常不阻塞。
3. ✅ `cli.py`：`python -m evoagent.cli list` 端到端可跑；`run`/`evolve`/`bench` 分发正确；`run` 正确映射 `retrieval_fallback`。
4. ✅ 打包修复：干净环境 `pip install .` 后四子包全部 import 成功。
5. ✅ 设计回补：`docs/system_design.md` 新增 `Task` 定义与 `models.py` 逐字段一致；`git diff` 仅该一处。
6. ✅ `README.md`：含安装 + CLI 上手 + seed 数据前置说明。
7. ✅ 测试全绿（全量 126 passed），mock-first、自动化测试不发真实请求。
8. ✅ 无越界：无新第三方依赖、无 `tools.py`、无 report 文件 I/O、测试侧无真实 LLM 请求。

**结论：成功。** 全部验收标准满足，全部测试通过，项目补齐为可交付成品。

## 4. 已知局限

- `EvolutionLoop` 的触发条件只做「总样本数阈值」（`MIN_EVOLUTION_SAMPLES`），未实现 §9 的「连续 M 次」精确语义与「定时」模式（登记为已知简化）。
- 种子技能与 benchmark 集**未播种**（§12 冷启动）：`evolve`/`bench` 需先自行 `register` 技能、撰写 `data/benchmarks/*.json`，README 已如实标注非开箱即用。
- 仍沿用前序登记局限：`tools.py`/工具调用未实现、judge 与执行同模型、A/B 顺序跑、`total_cost=0.0` 占位、`Task` 无稳定 `task_id`、test_script 非 OS 沙箱、`metrics` 增量回写未实现等。

## 5. 后续问题

1. `tools.py` + 工具调用（执行层多轮 loop + 工具子集校验 + 文件沙箱）。
2. §12 冷启动：种子技能（code-review / text-summarize / qa-with-tools）+ benchmark 集撰写与播种。
3. judge 模型分离（`LLM_JUDGE_MODEL`）与 A/B 同批交错（抵消 judge 漂移）。

## 6. 建议的下一步

建议下一个事务（`0010`）落地 **`tools.py` + 工具调用**（执行层多轮 agent loop），或先做 **§12 冷启动**（种子技能 + benchmark 集播种，使 CLI 的 `evolve`/`bench` 开箱可跑）。

## 7. 提交

- 提交信息：`0009: 收官——落地 EvolutionLoop、CLI 与打包/文档收尾`
- 提交哈希：`8fb73d29a237b6eb88064e5e7209ede596650007`（`git rev-parse HEAD`，短哈希 `8fb73d2`）
