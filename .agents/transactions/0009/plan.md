# 事务 0009 计划（Plan）

> 规划者产出（收官事务）。遵循「文档精炼纪律」：引用而非复述，只写新增判断。

## 1. 当前状态

各核心层已落地（`0001`–`0008`，115 测试）。缺 `evolution/loop.py`、`evoagent/cli.py`、`README.md`；`pyproject.toml` 只打包 `evoagent` 顶层；`docs/system_design.md` 缺 `Task` 定义。

## 2. 问题

项目**不可交付**：无主循环编排、无 CLI 入口、`pip install .` 装不出子包、设计文档与实现不一致（`Task` 缺定义）、无上手文档。

## 3. 目标

收官，把「可用闭环」补成「可交付成品」（5 子项一个连贯目标）：

1. `EvolutionLoop`（主循环编排，只调已实现模块）
2. `cli.py`（run / evolve / bench / list）
3. 打包修复（子包纳入）
4. 设计回补（`docs/system_design.md` 补 `Task` 定义）
5. `README.md`

## 4. 范围

**做**：上述 5 子项。

**不做**：`tools.py`/工具调用、judge 模型分离、A/B 同批交错、report 文件 I/O、`Task` 稳定 id、新第三方依赖、真实 LLM 请求（mock-first）。

## 5. 拟议变更

| 文件 | 变更 |
|---|---|
| `evoagent/config.py` | 追加 `MIN_EVOLUTION_SAMPLES`（§5.1） |
| `evoagent/evolution/loop.py` | 新建 `EvolutionLoop`（§5.2） |
| `evoagent/cli.py` | 新建 CLI 入口（§5.3） |
| `pyproject.toml` | `packages` 改 `find`（§5.4） |
| `docs/system_design.md` | 补 `Task` dataclass 定义（§5.5，仅此一处） |
| `README.md` | 新建（§5.6） |
| `tests/test_loop.py` | 新建 |
| `tests/test_cli.py` | 新建 |

### 5.1 `config.py` —— `MIN_EVOLUTION_SAMPLES`

追加 `MIN_EVOLUTION_SAMPLES = 1`（§9「样本量够才演化」；K/M 设计未钉，v1 默认 1，可调）。其余常量不动。

### 5.2 `EvolutionLoop`（`evolution/loop.py`）

```python
class EvolutionLoop:
    def __init__(self, trace_store, eval_store, extractor, evolver, validator, registry): ...
    def run(self, tasks: list[BenchmarkTask]) -> list[ValidationResult]: ...
```

- **收集**：`trace_store.list()` → 过滤 `task_source=="real"` 且 `error_type!="infra"` → 经 `eval_store.list_evals(trace_id)` 取 `passed is False` 者 → 按 `skill_id` 分组。
- **防污染（§11 规则 1，Loop 侧硬保证）**：只挖 `task_source=="real"` 的 trace，`benchmark` 来源**绝不进经验挖掘**。
- **每 skill**：样本 `< MIN_EVOLUTION_SAMPLES` → 跳过（成本控制）；否则 `registry.get_active(skill_id)` → 逐条 `extractor.extract(trace, result)` 拼 `Experience[]` → `evolver.evolve(skill, experiences)` → `validator.validate(skill_id, candidate, tasks)`。
- **失败处理**：单 skill 处理异常**捕获记录、跳过、继续**（不阻塞主流程，不重试）；`ValidationResult` 汇总返回（promoted/不显著/回归/样本不足已由 `0008` Validator 三支结局体现）。
- **分层**：只调上述六模块，不 `import sqlite3`/`Storage`、不重实现下层逻辑。

### 5.3 `cli.py`（argparse，四子命令）

```python
def main(argv: list[str] | None = None) -> int: ...   # parse → build_components → dispatch
def build_components(db_path=None): ...                # 组装 Storage→各门面→retriever→executor→evaluator→...→loop
```

- `run <task>`：`Task(task, "real")` → `retriever.retrieve_top1` → `executor.run` → 打印 `final_output`/status。
- `evolve`：`load_tasks_by_name("regression")` → `loop.run(tasks)` → 打印各 skill 的 `ValidationResult`。
- `bench <skill_id> [--set regression|extension]`：`load_tasks_by_name` → `registry.get_active` → `benchmark.run` → 打印 `BenchmarkReport`。
- `list`：`registry.list()` → 打印 active skills。
- 仅 argparse + 组装 + 分发（薄层）；`list` 无 LLM 可端到端运行，其余子命令经 mock 组件测 dispatch。

### 5.4 打包修复（`pyproject.toml`）

`[tool.setuptools] packages = ["evoagent"]` → 改 `[tool.setuptools.packages.find]` + `include = ["evoagent*"]`（自动纳入 `skills`/`execution`/`eval`/`evolution` 子包）。

### 5.5 设计回补（`docs/system_design.md`，仅 `Task` 一处）

在 §4 附近补 `Task` dataclass 定义，**逐字段对齐 `0003` 实现**（`models.py`）：

```python
@dataclass
class Task:
    task: str          # 任务描述（文本，供检索与执行）
    task_source: str   # "real"（真实任务）| "benchmark"（跑分）——§4 防污染标签
```

**不得**改动其它任何章节；不得「顺手优化」措辞/结构。

### 5.6 `README.md`（仓库根）

项目一句话说明 + 架构概览（§1 闭环）+ 快速上手（安装、`pip install .`、CLI 四子命令、设 `DEEPSEEK_API_KEY` 跑 `run`）+ 指向 `docs/system_design.md`。不杜撰未实现能力。

## 6. 依赖

- 运行时：标准库 + 既有 `openai`。无新第三方。
- 顺序：`config.py` → `loop.py` → `cli.py` → `pyproject.toml` → 设计回补 + README → 测试。
- 既有：`TraceStore`/`EvalStore`（`0002`）、`SkillRetriever`（`0003`）、`AgentExecutor`（`0005`）、`ExperienceExtractor`（`0006`）、`Benchmark`（`0007`）、`SkillEvolver`/`Validator`（`0008`）。

## 7. 风险

| 风险 | 缓解 |
|---|---|
| **Loop 污染经验挖掘**（挖进 benchmark trace） | `task_source=="real"` 过滤为硬条件，测试断言 benchmark trace 被排除 |
| **Loop 失败阻塞主流程** | 单 skill 异常捕获跳过；测试断言一 skill 抛异常不影响其余 |
| **触发条件成本失控**（每条 trace 都演化） | `MIN_EVOLUTION_SAMPLES` + 只挖低分（passed False）；测试覆盖样本不足跳过 |
| **打包修复未验证** | 验收用干净环境 `pip install .` 后 `import evoagent.eval.benchmark` 等全子包可导入 |
| **设计回补越界**（趁机改其它章节） | 仅加 `Task` 块；diff 只允许该一处新增，验收核对 |
| **CLI 组装/分发复杂** | 薄层：组装函数独立、子命令纯分发；mock 组件测 dispatch |

## 8. 实施顺序

1. `config.py` 加 `MIN_EVOLUTION_SAMPLES`。
2. `loop.py`（`EvolutionLoop`）+ `test_loop.py`。
3. `cli.py` + `test_cli.py`。
4. `pyproject.toml` 打包修复。
5. `docs/system_design.md` 补 `Task` + `README.md`。
6. 全量验证（§10）。

## 9. 验收标准

1. `EvolutionLoop.run` mock 跑通全链路：收集低分 real trace → 分组 → extract → evolve → validate → 返回 `list[ValidationResult]`。
2. **Loop 防污染**：`task_source=="benchmark"` 或 `error_type=="infra"` 的 trace 被排除（不进经验挖掘）；测试断言。
3. **Loop 边界**：样本 `< MIN_EVOLUTION_SAMPLES` 的 skill 跳过；单 skill 异常不阻塞其余；不重试失败候选。
4. **CLI 可运行**：`python -m evoagent.cli list` 端到端可跑（无 LLM）；`run`/`evolve`/`bench` 子命令 argparse + 分发正确（mock 组件测试）。
5. **打包修复**：干净环境 `pip install .` 后 `import evoagent.skills.registry, evoagent.execution.executor, evoagent.eval.benchmark, evoagent.evolution.validator` 全部成功。
6. **设计回补一致**：`docs/system_design.md` 新增 `Task` 定义与 `models.py` 的 `Task` 逐字段一致（`task`/`task_source`，无 `task_id`）；diff 仅该一处新增。
7. `README.md` 存在且含安装 + CLI 上手。
8. 测试全绿（`test_loop`/`test_cli` + 全量无回归），mock-first 不发真实请求。
9. 无越界：无新第三方依赖、无 `tools.py`、无真实 LLM 请求。

## 10. 验证策略

```
python -m pytest tests/test_loop.py tests/test_cli.py -v
python -m pytest -v        # 全量回归
```

- `test_loop.py`（mock `TraceStore`/`EvalStore`/`extractor`/`evolver`/`validator`/`registry`）：全链路跑通；防污染过滤（benchmark/infra 排除）；样本不足跳过；单 skill 异常不阻塞。
- `test_cli.py`（mock 组件）：四子命令 argparse + 分发正确；`list` 端到端（tmp Storage）。
- **打包验证（人工，干净环境）**：`python -m venv /tmp/venv && pip install . && python -c "import evoagent.eval.benchmark, evoagent.evolution.validator"`。
- **设计回补核对**：`git diff docs/system_design.md` 仅 `Task` 一处新增，字段与 `models.py` 一致。
- 人工复核：`grep -rn "import sqlite3" evoagent/` 仅 `storage.py`；`loop.py`/`cli.py` 不出现。
