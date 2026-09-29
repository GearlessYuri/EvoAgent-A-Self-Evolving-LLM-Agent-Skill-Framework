# 事务 0009 最终任务规格说明（Task）

> 优化者（Optimizer）产出。本文件是编码者实现的**唯一依据**，自包含：编码者无需阅读 `plan.md` / `review.md` 即可执行。
> 依据：`plan.md` + `review.md` + `docs/system_design.md` + 事务 `0001`–`0008` 落地后的实仓源码 + 实仓核实。
>
> 说明：本仓库事务文件实际位于 `.agents/transactions/0009/`（顶层 `transactions/` 不存在）。下文路径均以 `.agents/transactions/0009/` 为准。

---

## 1. 目标（Objective）

收官：把「可用闭环」补成「可交付成品」。5 个子项（同一连贯目标）：

1. `evoagent/evolution/loop.py`：`EvolutionLoop`（主循环编排，只调已实现模块）
2. `evoagent/cli.py`：CLI 入口（`run` / `evolve` / `bench` / `list` 四子命令）
3. `pyproject.toml`：打包修复（子包纳入 `pip install .`）
4. `docs/system_design.md`：回补 `Task` 定义（**仅此一处**）
5. `README.md`：上手文档

成果须通过 `pytest` 验证（mock-first、自动化测试不发真实 LLM 请求）；除收尾提交外不做任何 git 操作。

## 2. 上下文（Context）

- 事务 `0001`–`0008` 已落地全部核心层，全量 115 项测试通过，git `main`@`cdc839f`。
- **实仓现状（已核实）**：
  - `evoagent/evolution/` 下**无 `loop.py`**；`evoagent/cli.py` **不存在**；仓库根**无 `README.md`**。
  - `pyproject.toml`：`[tool.setuptools] packages = ["evoagent"]`（**不含子包**）。
  - `docs/system_design.md` 缺 `Task` 定义；`models.py` 的 `Task` 实为 `task: str` + `task_source: str`（无 `task_id`，`0003` 拍板）。
  - `config.py`：已有 `PROMOTE_WIN_RATE_THRESHOLD`/`MIN_REGRESSION_TASKS`（0008），**无** `MIN_EVOLUTION_SAMPLES`。
  - 已就绪接口（Loop/CLI 直接消费，均已核实）：`TraceStore.list(skill_id=None, status=None, since=None)`（返回 summary，`steps=[]` 但含 `task_source`/`error_type`/`skill_id`/`final_output`/`status`/`trace_id`）、`EvalStore.list_evals(trace_id)`、`SkillRegistry.get_active/list`、`SkillRetriever.retrieve_top1(task) -> RetrievalResult(skill, score, fallback)`、`AgentExecutor.run(task, skill, *, retrieval_fallback=False)`、`ExperienceExtractor.extract(trace, result)`、`SkillEvolver.evolve(skill, experiences)`、`Validator.validate(skill_id, candidate, tasks) -> ValidationResult`、`Benchmark.run(tasks, skill)`、`load_tasks_by_name(name)`。
- **设计分层（§2）**：`loop.py`/`cli.py` 属编排层，只调下层模块，不 `import sqlite3`/`Storage`（`cli.py` 的 `build_components` 是组合根，**唯一**负责实例化 `Storage`）。
- **环境**：Python 3.13.9（≥3.10）、pytest 8.4.2。

## 3. 范围（Scope）

**做（In scope）**

1. `evoagent/config.py`：追加 `MIN_EVOLUTION_SAMPLES`（§4.1）。
2. `evoagent/evolution/loop.py`：`EvolutionLoop`（§4.2）。
3. `evoagent/cli.py`：CLI 入口（§4.3）。
4. `pyproject.toml`：打包修复（§4.4）。
5. `docs/system_design.md`：回补 `Task` 定义（§4.5，仅此一处）。
6. `README.md`：新建（§4.6）。
7. `tests/test_loop.py`、`tests/test_cli.py`：新建（§4.7）。

**不做（Out of scope，明确非目标）** —— 详见 §11。

## 4. 需求（Requirements）

### 4.1 `evoagent/config.py` —— 追加一个常量

在既有常量之后追加（**不改动**任何既有常量）：

```python
# ── 演化触发（事务 0009 追加） ──────────────────────────────────────────────
MIN_EVOLUTION_SAMPLES = 1   # §9 触发阈值：某 skill 低分样本数 ≥ 此值才演化（v1 简化，见 §11.3）
```

### 4.2 `EvolutionLoop`（`evoagent/evolution/loop.py`）

**为什么存在**：把各模块串成闭环，控制何时演化（§3.5，系统「神经系统」）。

**精确实现**：

```python
"""演化主循环：收集低分 real trace → 按 skill 聚合 → 提炼 → 演化 → 验证 → 更新注册表（§3.5/§9）。

只编排下层模块，不 import sqlite3 / Storage、不重实现。
防污染（§11 规则 1）：只挖 task_source=="real" 的 trace。
"""

from __future__ import annotations

from .. import config
from ..eval.experience import ExperienceExtractor
from ..eval.store import EvalStore
from ..execution.trace import TraceStore
from ..models import BenchmarkTask
from ..skills.registry import SkillRegistry
from .evolver import SkillEvolver
from .validator import ValidationResult, Validator


class EvolutionLoop:
    def __init__(
        self,
        trace_store: TraceStore,
        eval_store: EvalStore,
        extractor: ExperienceExtractor,
        evolver: SkillEvolver,
        validator: Validator,
        registry: SkillRegistry,
    ):
        self.trace_store = trace_store
        self.eval_store = eval_store
        self.extractor = extractor
        self.evolver = evolver
        self.validator = validator
        self.registry = registry

    def run(self, tasks: list[BenchmarkTask]) -> list[ValidationResult]:
        # 1) 收集低分 real trace（内存过滤，summary trace 够用，不逐条 get）
        low_by_skill: dict[str, list] = {}
        for trace in self.trace_store.list():
            if trace.task_source != "real":       # §11 防污染：只挖 real
                continue
            if trace.error_type == "infra":      # §9：infra 不计
                continue
            for result in self.eval_store.list_evals(trace.trace_id):
                if result.passed is False:       # §9：只挖低分
                    low_by_skill.setdefault(trace.skill_id, []).append((trace, result))

        outcomes: list[ValidationResult] = []
        for skill_id, items in low_by_skill.items():
            if len(items) < config.MIN_EVOLUTION_SAMPLES:  # 样本不足跳过
                continue
            try:
                skill = self.registry.get_active(skill_id)
                if skill is None:                        # 无 active 跳过
                    continue
                experiences = []
                for trace, result in items:
                    experiences.extend(self.extractor.extract(trace, result))
                if not experiences:                      # 全被 confidence 过滤 → 跳过
                    continue
                candidate = self.evolver.evolve(skill, experiences)
                vr = self.validator.validate(skill_id, candidate, tasks)
                outcomes.append(vr)
            except Exception:
                continue  # 单 skill 失败跳过、不阻塞、不重试
        return outcomes
```

**语义钉死（裁定）**：

- **收集过滤（§2.1 裁定）**：`task_source`/`error_type` 过滤在 **Loop 侧内存完成**（`TraceStore.list()` 不支持这两参）；`list()` 返回 summary 行已含 `task_source`/`error_type` 列，`extractor.extract` 只用 summary 字段，**不逐条 `get()`**（避免 N+1）。
- **过滤口径（§9）**：只挖 `task_source=="real"` 且 `error_type!="infra"` 且存在 `passed is False` 的 eval。
- **触发（§4.1 裁定）**：`len(items) < MIN_EVOLUTION_SAMPLES` → 跳过；**只做「总样本数阈值」，不实现「连续 M 次」、不实现「定时」模式**（登记为 §9 简化，§11.3）。
- **每 skill 流程**：`registry.get_active(skill_id)` → 逐条 `extractor.extract` 拼 `Experience[]` → `evolver.evolve` → `validator.validate(skill_id, candidate, tasks)`。
- **边界（§4.4 裁定）**：`get_active` 返回 `None` → 跳过；`extract` 返回空 → 跳过；`tasks` 为空 → 不特殊处理（`Validator` 的 `< MIN_REGRESSION_TASKS` 分支会产出 `sample_insufficient`）；无低分 trace → 返回 `[]`。
- **失败处理**：单 skill 处理异常**捕获、跳过、继续**（不阻塞主流程、不重试）；返回 `list[ValidationResult]`（promoted/不显著/回归/样本不足已由 0008 Validator 体现）。
- **分层**：只调六模块，不 `import sqlite3`/`Storage`、不重实现。

### 4.3 `cli.py`（`evoagent/cli.py`）

**精确实现**：

```python
"""CLI 入口：run / evolve / bench / list 四子命令（§13）。薄层：argparse + 组装 + 分发。"""

from __future__ import annotations

import argparse
from types import SimpleNamespace

from . import config
from .eval.benchmark import Benchmark, load_tasks_by_name
from .eval.evaluator import Evaluator
from .eval.experience import ExperienceExtractor
from .eval.store import EvalStore
from .evolution.evolver import SkillEvolver
from .evolution.loop import EvolutionLoop
from .evolution.validator import Validator
from .execution.executor import AgentExecutor
from .execution.trace import TraceStore
from .llm import LLMClient
from .models import Task
from .skills.registry import SkillRegistry
from .skills.retriever import SkillRetriever
from .storage import Storage


def build_components(db_path=None):
    """组合根：全量组装所有组件（`list` 子命令冗余但可接受）。"""
    storage = Storage(db_path if db_path else config.DB_PATH)
    storage.connect()
    storage.init_schema()

    registry = SkillRegistry(storage, skills_dir=config.SKILLS_DIR)
    trace_store = TraceStore(storage)
    eval_store = EvalStore(storage)
    llm = LLMClient()
    retriever = SkillRetriever(registry)
    executor = AgentExecutor(llm, trace_store)
    evaluator = Evaluator(llm, eval_store)
    extractor = ExperienceExtractor(llm)
    benchmark = Benchmark(executor, evaluator)
    evolver = SkillEvolver(llm)
    validator = Validator(benchmark, registry, eval_store)
    loop = EvolutionLoop(trace_store, eval_store, extractor, evolver, validator, registry)

    return SimpleNamespace(
        storage=storage, registry=registry, trace_store=trace_store, eval_store=eval_store,
        llm=llm, retriever=retriever, executor=executor, evaluator=evaluator,
        extractor=extractor, benchmark=benchmark, evolver=evolver, validator=validator, loop=loop,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="evoagent")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    p_run = sub.add_parser("run")
    p_run.add_argument("task")
    sub.add_parser("evolve")
    p_bench = sub.add_parser("bench")
    p_bench.add_argument("skill_id")
    p_bench.add_argument("--set", default="regression", choices=["regression", "extension"])

    args = parser.parse_args(argv)
    c = build_components()

    if args.command == "list":
        for skill in c.registry.list():
            print(f"{skill.skill_id}\t{skill.version}\t{skill.status}\t{skill.name}")
        return 0

    if args.command == "run":
        task = Task(task=args.task, task_source="real")
        r = c.retriever.retrieve_top1(task)
        trace = c.executor.run(task, r.skill, retrieval_fallback=r.fallback)  # §3.4 裁定：映射 fallback
        print(trace.final_output)
        return 0 if trace.status == "success" else 1

    if args.command == "evolve":
        tasks = load_tasks_by_name("regression")
        for vr in c.loop.run(tasks):
            print(f"{vr.reason}\twin_rate={vr.win_rate:.3f}\tsample_size={vr.sample_size}")
        return 0

    if args.command == "bench":
        tasks = load_tasks_by_name(args.set)
        skill = c.registry.get_active(args.skill_id)
        if skill is None:
            print(f"skill not found: {args.skill_id}")
            return 1
        report = c.benchmark.run(tasks, skill)
        print(report.to_dict())
        return 0

    return 0
```

**语义钉死（裁定）**：

- **`build_components` 全量组装（§4.3 裁定）**：一次性组装全部组件（`list` 子命令冗余但可接受——`LLMClient()` 惰性构建不强制 API key、安全）；`build_components` 是**唯一** `import Storage` / 调 `connect()`/`init_schema()` 的地方。返回 `SimpleNamespace`（字段见代码）。
- **`run` 的 `retrieval_fallback` 映射（§3.4 裁定）**：`r = retriever.retrieve_top1(task)` → `executor.run(task, r.skill, retrieval_fallback=r.fallback)`（不得漏传，否则落库 `retrieval_fallback` 恒 False）。
- **四子命令**：`list`（无 LLM、可端到端）、`run <task>`、`evolve`（`load_tasks_by_name("regression")`）、`bench <skill_id> [--set regression|extension]`。
- **薄层**：仅 argparse + 组装 + 分发；`main(argv=None) -> int`（返回进程退出码，`run` 成功 0 / 失败 1）。

### 4.4 打包修复（`pyproject.toml`）

将 `[tool.setuptools]` 段由 `packages = ["evoagent"]` 改为：

```toml
[tool.setuptools.packages.find]
include = ["evoagent*"]
```

（自动纳入 `skills`/`execution`/`eval`/`evolution` 子包。）

### 4.5 设计回补（`docs/system_design.md`，仅 `Task` 一处）

- **placement（§4.2 裁定）**：在 §4「数据流设计」标题之后、「**正向流（运行时，每次执行都走）**」列表之前，插入一个 `Task` dataclass 代码块（不新增章节编号、不扰动 §5–§11）。
- **内容（与 `models.py` 逐字段一致）**：

  ```python
  @dataclass
  class Task:
      task: str          # 任务描述（文本，供检索与执行）
      task_source: str   # "real"（真实任务）| "benchmark"（跑分）——§4 防污染标签
  ```

- **严格约束**：**仅此一处新增**；不得改动任何其它章节、不得「顺手优化」措辞/结构；`git diff docs/system_design.md` 只允许该一处新增。

### 4.6 `README.md`（仓库根）

新建，**必须含**：

1. 一句话项目说明（自演进 Agent Skill 平台）。
2. 架构概览（§1 闭环：Task → 检索 → 执行 → Trace → 评估 → 经验 → 演化 → 验证 → 注册表）。
3. 快速上手：安装（`pip install .`）、CLI 四子命令用法（`python -m evoagent.cli list/run/evolve/bench`）、设 `DEEPSEEK_API_KEY` 跑 `run`。
4. **前置说明（§3.2 裁定）**：`evolve`/`bench` 需先有 `data/benchmarks/{regression,extension}.json` 与已注册 skill（种子技能尚未播种，需自行 `register`）；无这些时 `evolve`/`bench` 会 `FileNotFoundError` 或空跑——如实标注，**不杜撰「开箱即用」**。
5. 指向 `docs/system_design.md`。

### 4.7 测试要求

- `tests/test_loop.py`、`tests/test_cli.py`：见 §10，全程 mock、自动化测试不发真实 LLM 请求。

## 5. 约束（Constraints）

1. **语言 / 运行时**：Python 3.10+（本机 3.13.9）；类型注解统一 `X | None`。
2. **运行时依赖**：标准库 + 既有 `openai>=1.0`；**无新第三方**。
3. **分层**：`loop.py` 只编排下层模块；`cli.py` 的 `build_components` 是唯一 `import Storage`/`connect()`/`init_schema()` 处；`storage.py` 仍是全项目唯一写 SQL/`import sqlite3` 处。
4. **不改既有**：不改 `models.py`/`storage.py`/`registry.py`/`retriever.py`/`executor.py`/`trace.py`/`evaluator.py`/`experience.py`/`benchmark.py`/`evolver.py`/`validator.py`/`llm.py`；`config.py` 仅追加一常量。
5. **设计文档只读（除 §4.5）**：`docs/system_design.md` 仅允许 §4.5 所述一处新增，其余只读。
6. **不越界**：不实现 `tools.py`/工具调用、judge 模型分离、A/B 同批交错、report 文件 I/O、`Task` 稳定 id。
7. **命名**：类 `PascalCase`、方法/函数 `snake_case`、常量 `UPPER_SNAKE_CASE`。
8. **测试口径（§2.2 裁定）**：**自动化测试 mock-first、不发真实 LLM 请求；CLI 运行时（用户调用 `run`/`evolve`/`bench`）发真实 LLM 请求是预期行为**。

## 6. 相关文件 / 模块（Relevant Files / Modules）

**本事务新建：**

| 文件 | 内容 |
|---|---|
| `evoagent/evolution/loop.py` | `EvolutionLoop`（§4.2） |
| `evoagent/cli.py` | `main` + `build_components`（§4.3） |
| `README.md` | 上手文档（§4.6） |
| `tests/test_loop.py` | §4.7/§10 |
| `tests/test_cli.py` | §4.7/§10 |

**本事务修改：**

| 文件 | 变更 |
|---|---|
| `evoagent/config.py` | 追加 `MIN_EVOLUTION_SAMPLES`（§4.1） |
| `pyproject.toml` | `[tool.setuptools]` 改 `packages.find`（§4.4） |
| `docs/system_design.md` | 回补 `Task` 定义（§4.5，仅一处） |

**只读参照（不修改）：** 其余 `evoagent/*`、`tests/*`、`.agents/transactions/0001/`–`0009/` 的历史产物（`plan.md`/`review.md` 等不可改）。

## 7. 推荐的实现策略（Recommended Implementation Strategy）

依赖关系：`config.py` → `loop.py` → `cli.py` → `pyproject.toml` → 设计回补 + README → 测试 → 验证 → 收尾提交。

1. **`config.py`**：追加 `MIN_EVOLUTION_SAMPLES`。
2. **`loop.py`**：按 §4.2 实现 `EvolutionLoop`。
3. **`cli.py`**：按 §4.3 实现 `build_components` + `main`。
4. **`pyproject.toml`**：改 `packages.find`。
5. **`docs/system_design.md`**：按 §4.5 补 `Task`；**`README.md`**：按 §4.6 写。
6. **`test_loop.py`/`test_cli.py`**：按 §10 写。
7. **验证**：运行 §10 命令（含打包人工验证 + 设计 diff 核对），确认全绿。
8. **收尾提交**：按 §10 末尾执行。

## 8. 预期变更（Expected Changes）

| 文件 | 变更性质 |
|---|---|
| `evoagent/config.py` | 修改：追加 `MIN_EVOLUTION_SAMPLES`（既有常量不动） |
| `evoagent/evolution/loop.py` | 新建 |
| `evoagent/cli.py` | 新建 |
| `pyproject.toml` | 修改：`packages` → `packages.find` |
| `docs/system_design.md` | 修改：补 `Task` 定义（仅一处） |
| `README.md` | 新建 |
| `tests/test_loop.py` | 新建 |
| `tests/test_cli.py` | 新建 |

（不修改其余 `evoagent/*`、其余 `tests/*`、`requirements.txt`、`.gitignore`、`__init__.py`；不产生运行时数据文件到源码树。）

## 9. 验收标准（Acceptance Criteria）

1. **`config.py`**：新增 `MIN_EVOLUTION_SAMPLES == 1`；既有常量不变。
2. **`EvolutionLoop`（子项 1）**：mock 跑通全链路——收集低分 real trace → 分组 → extract → evolve → validate → 返回 `list[ValidationResult]`；`task_source=="benchmark"` 或 `error_type=="infra"` 的 trace 被排除（不进经验挖掘）；样本 `< MIN_EVOLUTION_SAMPLES` 的 skill 跳过；单 skill 异常不阻塞其余、不重试。
3. **`cli.py`（子项 2）**：`python -m evoagent.cli list` 端到端可跑（无 LLM）；`run`/`evolve`/`bench` 的 argparse + 分发正确（mock 组件测试）；`run` 正确映射 `retrieval_fallback`。
4. **打包修复（子项 3）**：干净环境 `pip install .` 后 `import evoagent.skills.registry, evoagent.execution.executor, evoagent.eval.benchmark, evoagent.evolution.validator` 全部成功。
5. **设计回补（子项 4）**：`docs/system_design.md` 新增 `Task` 定义与 `models.py` 逐字段一致（`task`/`task_source`，无 `task_id`）；`git diff docs/system_design.md` 仅该一处新增。
6. **`README.md`（子项 5）**：存在且含安装 + CLI 上手 + seed 数据前置说明。
7. **测试**：`test_loop.py`/`test_cli.py` 全绿，全量 `python -m pytest` 无回归；mock-first、自动化测试不发真实请求。
8. **无越界**：无新第三方依赖、无 `tools.py`、无 report 文件 I/O、无真实 LLM 请求（测试侧）。

## 10. 验证策略（Verification Strategy）

在项目根目录运行：

```
python -m pytest tests/test_loop.py tests/test_cli.py -v
```

并确认全量回归：

```
python -m pytest -v
```

**用例要求：**

- `tests/test_loop.py`（mock `TraceStore`/`EvalStore`/`extractor`/`evolver`/`validator`/`registry`）：
  - 全链路跑通：mock 返回低分 real trace → 断言 extract/evolve/validate 被以正确入参调用、返回 `list[ValidationResult]`。
  - 防污染：`task_source=="benchmark"` 或 `error_type=="infra"` 的 trace 被排除（mock extractor 不被这些 trace 调用）。
  - 边界：样本 `< 1` 跳过；`get_active` 返回 None 跳过；`extract` 返回空跳过；单 skill 抛异常不影响其余。
- `tests/test_cli.py`（monkeypatch `cli.build_components` 返回 mock 组件 / tmp Storage 真组件）：
  - 四子命令 argparse + 分发正确（`list` 端到端用 tmp Storage、无 LLM；`run`/`evolve`/`bench` 用 mock 断言分发）。
  - `run` 映射 `retrieval_fallback`（mock `retrieve_top1` 返回 `fallback=True`，断言 `executor.run(..., retrieval_fallback=True)`）。

**打包验证（人工，干净环境，§3.1 裁定：必记入 `result.md`，跳过即验收不完整）：**

```
python -m venv /tmp/evoagent-venv && /tmp/evoagent-venv/bin/pip install . && \
/tmp/evoagent-venv/bin/python -c "import evoagent.skills.registry, evoagent.execution.executor, evoagent.eval.benchmark, evoagent.evolution.validator"
```

（Windows 下用 `python -m venv <tmp> && <tmp>\Scripts\pip install . && <tmp>\Scripts\python -c ...`。）

**设计回补核对：**

```
git diff docs/system_design.md
```

仅 §4 一处新增 `Task` 代码块，字段与 `models.py` 一致。

**额外人工复核（非 pytest，编码者确认并记入 `execution.md`）：**

```
grep -rn "import sqlite3" evoagent/
```

真实 `import sqlite3` 语句**只**应出现在 `evoagent/storage.py`；`loop.py`/`cli.py` 不得出现。

**收尾提交（用户已授权，必须执行）**：

全部验证通过后，Coder **一次性提交全部变更**：

```
git add -A && git commit -m "0009: 收官——落地 EvolutionLoop、CLI 与打包/文档收尾"
```

- 提交信息**首行**必须以 `0009: ` 开头 + 一句目标概括（上例为建议措辞，可用同义简洁一句话）。
- **不 push、不 amend、不建分支、不 force-push**（仅本地提交）。
- **把提交哈希记入 `result.md`**（`git rev-parse HEAD` 取哈希）。

## 11. 明确的非目标（Explicit Non-Goals）

本任务**不做**以下任何事（防止范围蔓延）：

1. **`tools.py` 与工具调用**（执行层多轮 loop / 工具子集校验）——仍为后续项。
2. **judge 模型分离**（`LLM_JUDGE_MODEL`）、**A/B 同批交错**（抵消 judge 漂移）、**report 文件 I/O**（落盘 `report.json`/`report.md`）——均已在前序登记为已知局限，本事务不补。
3. **§9 触发条件的完整实现**：本事务只做「某 skill 低分样本数 ≥ `MIN_EVOLUTION_SAMPLES`」的**总样本数阈值**，**不实现「连续 M 次」精确语义、不实现「定时（每 N 次/每天）」模式**——登记为对 §9 的已知简化。
4. **`Task` 稳定 `task_id`**（任务关联/重试）——`Task` 无 `task_id`（0003 裁定），设计回补亦不含；待后续事务。
5. **种子技能播种 / benchmark 集撰写**（§12 冷启动）——本事务只修打包与 CLI，**不播种** `data/benchmarks/*.json` 或 seed skill（README 如实标注前置）。
6. **新第三方依赖**（无）。
7. **修改 `docs/system_design.md` 除 §4.5 外的任何章节**（其余只读）。
8. **除收尾提交（§10）外的任何 git 操作**：不 push、不 amend、不建分支、不 force-push、不拆多次提交。

---

### 已确认的决策（记录以备查；无「实现前需确认」的阻塞项）

| 裁定点 | 结论 |
|---|---|
| `MIN_EVOLUTION_SAMPLES` + 触发语义（§4.1） | `= 1`；**只做总样本数阈值**，不实现「连续 M 次」/「定时」模式，登记为 §9 已知简化 |
| 措辞升级（§2.2） | 自动化测试 mock-first、不发真实请求；CLI 运行时发真实 LLM 请求是预期 |
| Loop 内存过滤（§2.1） | `task_source`/`error_type` 在 Loop 侧内存过滤；summary trace 够用、不逐条 `get()` |
| `cli.py run` 映射（§3.4） | `executor.run(task, r.skill, retrieval_fallback=r.fallback)`（从 `RetrievalResult.fallback` 映射） |
| `EvolutionLoop.run` 边界（§4.4） | `get_active=None` 跳过；`extract` 空跳过；`tasks` 空不特殊处理（走 sample_insufficient）；无低分 trace → `[]` |
| `build_components`（§4.3） | **全量组装**（list 冗余可接受），唯一 `import Storage`/`connect`/`init_schema` 处；返回 `SimpleNamespace` |
| 设计回补 placement（§4.2） | §4 标题后、正向流列表前插 `Task` 代码块；仅此一处新增 |
| 打包验证必记（§3.1） | 干净环境 `pip install .` + import 全子包，必记入 `result.md`，跳过即验收不完整 |
| seed 数据前置（§3.2） | README 如实标注 `evolve`/`bench` 需先有 benchmark 文件与已注册 skill |
| 5 子项独立验收（§3.3） | 验收标准 §9.2–§9.6 各子项独立可判定 |
