# 事务 0007 最终任务规格说明（Task）

> 优化者（Optimizer）产出。本文件是编码者实现的**唯一依据**，自包含：编码者无需阅读 `plan.md` / `review.md` 即可执行。
> 依据：`plan.md` + `review.md` + `docs/system_design.md` + 事务 `0001`–`0006` 落地后的实仓源码 + 实仓核实。
>
> 说明：本仓库事务文件实际位于 `.agents/transactions/0007/`（顶层 `transactions/` 不存在）。下文路径均以 `.agents/transactions/0007/` 为准。

---

## 1. 目标（Objective）

落地 `Benchmark`（任务集加载 + 批量「执行→评估→汇总」+ 报告数据对象），补 `Evaluator` 的 `test_script` 客观执行（子进程 + 超时），并把 §11 防污染三规则落实为代码可见、可测试的隔离机制：

- `evoagent/eval/benchmark.py`：`Benchmark` + `load_tasks`/`load_tasks_by_name` + `BenchmarkReport`
- `evoagent/eval/evaluator.py`：补 `test_script` 客观分支 + `_run_test_script` 子进程 helper
- `evoagent/config.py`：加 `BENCHMARKS_DIR`、`TEST_SCRIPT_TIMEOUT_SEC`
- 测试：`tests/test_benchmark.py`（新建）、`tests/test_evaluator.py`（追加）

成果须通过 `pytest` 验证，test_script 用无害脚本、全程 mock 不发真实 LLM 请求；除收尾提交外不做任何 git 操作。

## 2. 上下文（Context）

- 事务 `0001`–`0006` 已落地：底座（含 `llm.py`）、门面、检索器、执行器、评估层（Evaluator + ExperienceExtractor）。全量 92 项测试通过，git `main`@`58d6e12`。
- **实仓现状（已核实）**：
  - `evoagent/eval/evaluator.py`：六分支；`otype not in ("exact","contains")` 时 `otype=None`（第 75–76 行注释「test_script 延后到 0007」）；exact/contains 的 `objective` dict 用 `matched` 键。
  - `evoagent/execution/executor.py`：`_render_prompt` 只用 `task.task`（`.replace("{task}")` + few-shot）；`trace.task_source = task.task_source`（第 47 行）——**来源隔离与答案隔离结构已就绪**。
  - `evoagent/models.py`：`BenchmarkTask`（`task_id`/`task`/`rubric: list[str]`/`objective_check: dict`/`tags`/`difficulty`/`reference_answer=""`）已就绪。
  - `evoagent/config.py`：**无** `BENCHMARKS_DIR`、**无** `TEST_SCRIPT_TIMEOUT_SEC`。
  - `evoagent/eval/` 下**无** `benchmark.py`。
- **设计分层（§2）**：`Benchmark` 属评估层，只编排 `executor` + `evaluator`，不直接写库、不 `import sqlite3`/`Storage`。
- **环境**：Python 3.13.9（≥3.10）、pytest 8.4.2。

## 3. 范围（Scope）

**做（In scope）**

1. `evoagent/config.py`：追加 `BENCHMARKS_DIR`、`TEST_SCRIPT_TIMEOUT_SEC`（§4.1）。
2. `evoagent/eval/evaluator.py`：补 `test_script` 客观分支 + `_run_test_script`（§4.2）。
3. `evoagent/eval/benchmark.py`：`Benchmark` + `load_tasks`/`load_tasks_by_name` + `BenchmarkReport`（§4.3）。
4. `tests/test_evaluator.py`（追加）、`tests/test_benchmark.py`（新建）（§4.4）。

**不做（Out of scope，明确非目标）** —— 详见 §11。

## 4. 需求（Requirements）

### 4.1 `evoagent/config.py` —— 追加两个常量

在既有常量之后追加（**不改动**任何既有常量）：

```python
# ── Benchmark / test_script（事务 0007 追加） ──────────────────────────────
BENCHMARKS_DIR = "data/benchmarks"   # §13 benchmark 任务集目录（regression.json / extension.json）
TEST_SCRIPT_TIMEOUT_SEC = 5          # §7 test_script 客观判题子进程超时（秒）
```

### 4.2 `evoagent/eval/evaluator.py` —— 补 `test_script` 客观分支

顶部 `import uuid` 之后追加 `import subprocess`、`import sys`；新增模块级 helper 与 `evaluate` 内的 test_script 分支：

```python
def _run_test_script(script: str, output: str) -> tuple[bool, str]:
    """子进程隔离执行判题脚本：脚本从 stdin 读 `output`（final_output），exit 0 为通过。"""
    try:
        proc = subprocess.run(
            [sys.executable, "-c", script],
            input=output,
            text=True,
            capture_output=True,
            timeout=config.TEST_SCRIPT_TIMEOUT_SEC,
        )
        return proc.returncode == 0, f"exit_code={proc.returncode}"
    except subprocess.TimeoutExpired:
        return False, "timeout"
    except Exception as exc:  # OSError 等一律捕获，绝不逃逸到 evaluate 外
        return False, str(exc)
```

在 `evaluate` 内，将第 75 行 `if otype not in ("exact", "contains"):` 改为 `if otype not in ("exact", "contains", "test_script"):`；并在「分支 2：exact」之后、「分支 3：contains」之前插入：

```python
        # 分支 2.5：test_script → 客观定论（跳过 judge），子进程执行
        if otype == "test_script":
            value = objective_check.get("value")
            if not (isinstance(value, str) and value.strip()):
                otype = None  # value 非字符串/空 → 视为「无客观」，走 judge 分支
            else:
                test_pass, _ = _run_test_script(value, final_output)
                return _result(
                    "objective", test_pass, 1.0 if test_pass else 0.0,
                    {"status": status, "type": "test_script", "test_pass": test_pass},
                    0.0, {}, "",
                )
```

**语义钉死（裁定，对应评审 §4.1/§4.2/§3.1/§3.4）**：

- **执行契约（§4.1）**：`objective_check["value"]` 即**脚本源码字符串**；脚本从 **stdin** 读 `final_output`；`returncode == 0` → `test_pass=True`，非 0 → `test_pass=False`。
- **定论语义**：`test_script` 与 `exact` 同为**客观定论**——`eval_basis="objective"`、**跳过 judge**、`passed=test_pass`、`total_score = 1.0 if test_pass else 0.0`、`judge_score=0.0`/`rubric_scores={}`/`judge_reason=""`（§7「exact/test_script → 不跑 judge」）。
- **`value` 缺失/非字符串/空串** → `otype=None` 视作「无客观」走 judge 分支（与 0006 未知 type 处理一致，不崩溃）。
- **超时**：`subprocess.TimeoutExpired` → `(False, "timeout")`；`TEST_SCRIPT_TIMEOUT_SEC = 5`（默认），超时用例 monkeypatch 成小值（见 §10）。
- **异常兜底**：非零退出、`OSError`、脚本内异常均捕获 → `(False, detail)`，**绝不**逃逸到 `evaluate` 外。
- **隔离措辞（§3.1 裁定）**：子进程 + 超时提供的是**崩溃/超时隔离**（防崩溃、防死循环、防挂死），**不是**文件系统/网络沙箱——`test_script` 是 benchmark 作者（可信）编写的判题脚本，此信任模型下足够；不可信脚本需 OS 级沙箱，登记为已知局限（§11.6）。
- **`objective` dict 键（§3.4 裁定）**：`test_script` 用 `test_pass` 键（`{"status", "type", "test_pass"}`），与 exact/contains 的 `matched` 键并列——设计 §7 注释本就列 `{status, matched, test_pass, ...}`，按 type 取不同结果键是既定约定。

### 4.3 `Benchmark`（`evoagent/eval/benchmark.py`）

**精确实现**：

```python
"""Benchmark：任务集加载 + 批量「执行→评估→汇总」+ 报告（§3.3/§11）。

只编排 `AgentExecutor` + `Evaluator`，不直接写库、不 import sqlite3 / Storage。
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from .. import config
from ..execution.executor import AgentExecutor
from ..models import BenchmarkTask, Skill, Task
from .evaluator import Evaluator


def load_tasks(path: str | Path) -> list[BenchmarkTask]:
    """从 JSON 文件加载任务列表（顶层为 JSON 数组，每项为 BenchmarkTask 字段）。"""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"benchmark 文件顶层应为数组: {path}")
    return [BenchmarkTask.from_dict(d) for d in data]


def load_tasks_by_name(name: str) -> list[BenchmarkTask]:
    """按名称从默认目录加载：`{BENCHMARKS_DIR}/{name}.json`（如 regression / extension）。"""
    return load_tasks(Path(config.BENCHMARKS_DIR) / f"{name}.json")


@dataclasses.dataclass
class BenchmarkReport:
    per_task: list[tuple[str, bool | None, float]]  # (task_id, passed, total_score)
    success_rate: float      # passed is True 数 / (passed 非 None 数)；无可判对错任务 → 0.0
    avg_total_score: float   # 全部任务 total_score 均值；无任务 → 0.0

    def to_dict(self) -> dict:
        return {
            "per_task": [
                {"task_id": tid, "passed": passed, "total_score": score}
                for tid, passed, score in self.per_task
            ],
            "success_rate": self.success_rate,
            "avg_total_score": self.avg_total_score,
        }


class Benchmark:
    def __init__(self, executor: AgentExecutor, evaluator: Evaluator):
        self.executor = executor
        self.evaluator = evaluator

    def run(self, tasks: list[BenchmarkTask], skill: Skill) -> BenchmarkReport:
        per_task: list[tuple[str, bool | None, float]] = []
        for bt in tasks:
            task = Task(task=bt.task, task_source="benchmark")
            trace = self.executor.run(task, skill)
            result = self.evaluator.evaluate(
                trace, task,
                reference_answer=bt.reference_answer,
                rubric=bt.rubric,
                objective_check=bt.objective_check,
            )
            per_task.append((bt.task_id, result.passed, result.total_score))

        decided = [p for p in per_task if p[1] is not None]
        success_rate = (sum(1 for p in decided if p[1] is True) / len(decided)) if decided else 0.0
        avg_total_score = (sum(p[2] for p in per_task) / len(per_task)) if per_task else 0.0
        return BenchmarkReport(per_task=per_task, success_rate=success_rate, avg_total_score=avg_total_score)
```

**语义钉死（裁定）**：

- **`load_tasks` JSON schema（§4.4）**：顶层为 **JSON 数组**，每项是 `BenchmarkTask` 字段 dict（必填 `task_id`/`task`/`rubric`/`objective_check`/`tags`/`difficulty`，可选 `reference_answer`）。顶层非数组 → 抛 `ValueError`。
- **`BENCHMARKS_DIR` 角色（§2.2）**：`load_tasks(path)` 用**显式路径**（可测）；`load_tasks_by_name(name)` 用 `BENCHMARKS_DIR` 作为默认根（`{BENCHMARKS_DIR}/{name}.json`）——`BENCHMARKS_DIR` 的消费者，也对应 §13 `data/benchmarks/{regression,extension}.json`。
- **批量流**：每个 `BenchmarkTask` → `Task(task=bt.task, task_source="benchmark")` → `executor.run(task, skill)` → `evaluator.evaluate(trace, task, reference_answer=bt.reference_answer, rubric=bt.rubric, objective_check=bt.objective_check)` → 汇总。
- **`success_rate` 口径（§3.2 裁定）**：`success_rate = (passed is True 数) / (passed 非 None 数)`；**`passed=None` 不计入分子、也不计入分母**（「客观通过率」只在已作出 pass/fail 判定的任务上计算）；无可判对错任务 → `0.0`。
- **`avg_total_score` 口径**：全部任务 `total_score` 均值（含 `passed=None` 者）；无任务 → `0.0`。
- **`BenchmarkReport`（§4.3）**：`benchmark.py` 内 `@dataclasses.dataclass`（**不进 `models.py`**，与 0003 先例一致），字段 `per_task: list[tuple[str, bool | None, float]]`、`success_rate: float`、`avg_total_score: float`，`to_dict()` JSON-ready。**不落盘**（report.json/report.md 属 Validator A/B，延后）。
- **防污染三规则（代码可见，§3.3 裁定）**：
  1. **来源隔离**：`Task(task_source="benchmark")` 由 `Benchmark.run` 固定写入，经 executor 落库为 `trace.task_source="benchmark"`。
  2. **答案隔离**：`reference_answer`/`rubric`/`objective_check` **只传 `evaluator.evaluate`**；`executor.run` 收到的 `Task` 仅含 `task` 文本（`_render_prompt` 只用 `task.task`），参考答案**结构上不进入执行路径**。
  3. **extension 只考不学**：`regression`/`extension` 经 `load_tasks_by_name` 各自加载；`Benchmark` **无任何「导出经验」API**（`run` 只返回 `BenchmarkReport`）。其真正的硬保证（未来 `EvolutionLoop` 只挖 `task_source=="real"` 的 trace）登记为 `0008` 演化事务的约束。
- **分层**：只编排 `executor`/`evaluator`，不直接写库、不 `import sqlite3`/`Storage`。

### 4.4 测试要求

- `tests/test_evaluator.py`（追加）、`tests/test_benchmark.py`（新建）：见 §10，全程 mock、test_script 用无害脚本。

## 5. 约束（Constraints）

1. **语言 / 运行时**：Python 3.10+（本机 3.13.9）；类型注解统一 `X | None`。
2. **运行时依赖**：标准库（`json`/`subprocess`/`sys`/`pathlib`/`dataclasses`/`typing`）；不新增第三方。
3. **分层**：`benchmark.py` 只编排 `executor`/`evaluator`；`storage.py` 仍是全项目唯一 `import sqlite3`/写 SQL 处。
4. **不改既有**：`evaluator.py` 六分支不动（仅加 test_script 分支与 helper）；不改 `models.py`/`storage.py`/`store.py`/`trace.py`/`executor.py`/`retriever.py`/`registry.py`/`experience.py`；`config.py` 仅追加两常量。
5. **不越界**：不实现 `SkillEvolver`/`Validator`/`EvolutionLoop`/`cli.py`/`tools.py`、win_rate A/B、report 文件 I/O、真实 LLM 请求。
6. **命名**：类 `PascalCase`、方法/函数 `snake_case`、常量 `UPPER_SNAKE_CASE`；`_run_test_script` 为模块级私有函数。
7. **错误处理**：`_run_test_script` 全异常捕获不逃逸；`load_tasks` 顶层非数组抛 `ValueError`；不自定义异常类。

## 6. 相关文件 / 模块（Relevant Files / Modules）

**本事务新建：**

| 文件 | 内容 |
|---|---|
| `evoagent/eval/benchmark.py` | `Benchmark` + `load_tasks`/`load_tasks_by_name` + `BenchmarkReport`（§4.3） |
| `tests/test_benchmark.py` | §4.4/§10 |

**本事务修改：**

| 文件 | 变更 |
|---|---|
| `evoagent/config.py` | 追加 `BENCHMARKS_DIR`/`TEST_SCRIPT_TIMEOUT_SEC`（§4.1） |
| `evoagent/eval/evaluator.py` | 补 `_run_test_script` + `test_script` 分支 + `import subprocess`/`sys`（§4.2） |
| `tests/test_evaluator.py` | 追加 `test_script` 用例（§4.4/§10） |

**只读参照（不修改）：** `evoagent/models.py`、`evoagent/storage.py`、`evoagent/eval/store.py`、`evoagent/eval/experience.py`、`evoagent/execution/trace.py`、`evoagent/execution/executor.py`、`evoagent/skills/*`、`evoagent/llm.py`、`docs/system_design.md`、`.agents/transactions/0001/`–`0007/` 的历史产物（`plan.md`/`review.md` 等不可改）。

## 7. 推荐的实现策略（Recommended Implementation Strategy）

依赖关系：`config.py`（加常量）→ `evaluator.py`（test_script）→ `benchmark.py` → 测试 → 验证 → 收尾提交。

1. **`config.py`**：追加两常量。
2. **`evaluator.py`**：加 `import subprocess`/`sys` + `_run_test_script`；改 normalization + 插 test_script 分支。
3. **`benchmark.py`**：按 §4.3 实现 `load_tasks`/`load_tasks_by_name`/`BenchmarkReport`/`Benchmark`。
4. **`test_evaluator.py`（追加）+ `test_benchmark.py`（新建）**：按 §10 写。
5. **验证**：运行 §10 命令，确认全绿。
6. **收尾提交**：按 §10 末尾执行。

## 8. 预期变更（Expected Changes）

| 文件 | 变更性质 |
|---|---|
| `evoagent/config.py` | 修改：追加 `BENCHMARKS_DIR`/`TEST_SCRIPT_TIMEOUT_SEC`（既有常量不动） |
| `evoagent/eval/evaluator.py` | 修改：补 `_run_test_script` + `test_script` 分支 + 两 import |
| `evoagent/eval/benchmark.py` | 新建 |
| `tests/test_evaluator.py` | 修改：追加 `test_script` 用例 |
| `tests/test_benchmark.py` | 新建 |

（不修改 `models.py`、`storage.py`、`store.py`、`experience.py`、`trace.py`、`executor.py`、`retriever.py`、`registry.py`、`llm.py`、`__init__.py`、`pyproject.toml`、`requirements.txt`、`docs/system_design.md`；不产生运行时数据文件。）

## 9. 验收标准（Acceptance Criteria）

1. **`config.py`**：新增 `BENCHMARKS_DIR == "data/benchmarks"`、`TEST_SCRIPT_TIMEOUT_SEC == 5`；既有常量不变。
2. **`test_script` 分支**：`value` 为脚本源码时子进程执行、`returncode==0` → `test_pass=True`（`eval_basis="objective"`、跳过 judge、`total_score=1.0`）；非零退出/超时/异常 → `test_pass=False`（`total_score=0.0`）；异常不逃逸；`value` 非字符串/空 → 视作「无客观」走 judge。
3. **`Benchmark.run`**：批量执行+评估，返回 `BenchmarkReport`；`success_rate` 口径正确（`passed is True 数 / passed 非 None 数`，`passed=None` 不计入分母）；`avg_total_score` 为全部任务均值；`to_dict()` JSON-ready。
4. **防污染①（来源隔离）**：真实 executor + 真实 TraceStore 跑后，`TraceStore.list()` 中相关 trace 的 `task_source == "benchmark"`（落库级验证，§2.1 裁定）。
5. **防污染②（答案隔离）**：设 `reference_answer` 为哨兵串，真实 executor 的 `steps[0]`（llm_call）prompt **不含**该哨兵（`reference_answer` 不进执行路径）。
6. **防污染③（extension 只考不学）**：`load_tasks_by_name` 分别加载 regression/extension；`Benchmark` 无任何「导出经验」接口。
7. **测试**：`test_benchmark.py` + 追加后的 `test_evaluator.py` 全绿，全量 `python -m pytest` 无回归；全程 mock、test_script 用无害脚本、不发真实 LLM 请求。
8. **无越界**：不含 `SkillEvolver`/`Validator`/`EvolutionLoop`/`cli.py`/`tools.py`/win_rate A/B/report 文件 I/O/真实 LLM 请求。

## 10. 验证策略（Verification Strategy）

在项目根目录运行：

```
python -m pytest tests/test_evaluator.py tests/test_benchmark.py -v
```

并确认全量回归：

```
python -m pytest -v
```

**用例要求：**

- `tests/test_evaluator.py`（追加，test_script 用无害脚本）：
  - 脚本 `import sys; sys.exit(0 if "hello" in sys.stdin.read() else 1)` + `final_output` 含 "hello" → `eval_basis="objective"`、`test_pass=True`、`objective["test_pass"]==True`、judge 未被调用（fake judge 记 0 次）。
  - 脚本 `sys.exit(1)` → `test_pass=False`、`total_score=0.0`。
  - 脚本 `while True: pass` → 超时（monkeypatch `config.TEST_SCRIPT_TIMEOUT_SEC` 为小值如 `0.2`）→ `test_pass=False`。
  - 脚本 `raise RuntimeError("x")` → `test_pass=False`、异常不逃逸。
  - `value` 非字符串（如 `123`）→ 走 judge 分支（`eval_basis` 非 objective）、不崩溃。
- `tests/test_benchmark.py`（mock `AgentExecutor`/`Evaluator` + 必要时真实 executor/TraceStore）：
  - **汇总口径**：mock executor + mock evaluator（`passed` 分别返回 True/False/None）→ 断言 `success_rate`（None 不计分母）、`avg_total_score`、`per_task` 形状、`to_dict()`。
  - **防污染①**：真实 `AgentExecutor`（fake LLM）+ 真实 `TraceStore(Storage(tmp_path/"x.db"))` + mock evaluator → `run` 后 `TraceStore.list()` 全部 `task_source=="benchmark"`。
  - **防污染②**：`reference_answer="SENTINEL_XYZ"` → 真实 executor 的 `steps[0].content`（llm_call prompt）不含 `"SENTINEL_XYZ"`。
  - **防污染③**：`load_tasks_by_name("regression")`/`load_tasks_by_name("extension")` 各自加载（用 tmp 下 `BENCHMARKS_DIR` 语义或 monkeypatch）；`Benchmark` 无「导出经验」方法（如 `not hasattr(benchmark, "export_experiences")`）。
  - `load_tasks` 顶层非数组 → `ValueError`。

**额外人工复核（非 pytest，编码者确认并记入 `execution.md`）：**

```
grep -rn "import sqlite3" evoagent/
```

真实 `import sqlite3` 语句**只**应出现在 `evoagent/storage.py`；`benchmark.py` 不得出现、也不得访问 `storage.conn`。

**收尾提交（用户已授权，必须执行）**：

全部验证通过后，Coder **一次性提交全部变更**：

```
git add -A && git commit -m "0007: 落地 Benchmark 与 test_script 客观执行"
```

- 提交信息**首行**必须以 `0007: ` 开头 + 一句目标概括（上例为建议措辞，可用同义简洁一句话）。
- **不 push、不 amend、不建分支、不 force-push**（仅本地提交）。
- **把提交哈希记入 `result.md`**（`git rev-parse HEAD` 取哈希）。

## 11. 明确的非目标（Explicit Non-Goals）

本任务**不做**以下任何事（防止范围蔓延）：

1. **`SkillEvolver`/`Validator`/`EvolutionLoop`/`cli.py`/`tools.py`**（演化/编排层）——SkillEvolver 与 Validator（A/B）**顺延至 `0008`。
2. **win_rate A/B**（§9 promote 规则）——属 `Validator`，不在本事务。
3. **report 文件 I/O**（落盘 `report.json`/`report.md`）：本事务只产出 `BenchmarkReport` 数据对象 + `to_dict()`，落盘属 Validator A/B 报告。
4. **按 tag/difficulty 抽取**（§3.3）：本事务**不实现**过滤接口；调用方（Validator）可预先过滤 `tasks` 列表再传入 `run`（登记为非目标）。
5. **OS 级沙箱**：`test_script` 仅「崩溃/超时隔离」（进程隔离），**不**提供文件系统/网络沙箱（§3.1）；`test_script` 是 benchmark 作者的可信判题脚本，不可信脚本需 OS 沙箱，登记为已知局限。
6. **真实 LLM 调用 / 网络请求**（全程 mock）。
7. **修改 `docs/system_design.md`**（只读）。
8. **除收尾提交（§10）外的任何 git 操作**：不 push、不 amend、不建分支、不 force-push、不拆多次提交。

---

### 已确认的决策（记录以备查；无「实现前需确认」的阻塞项）

| 裁定点 | 结论 |
|---|---|
| 验收 §9.4 与测试策略统一（§2.1） | 防污染①用**真实 executor + 真实 TraceStore**（tmp_path）落库级验证；汇总/口径用 mock executor+evaluator |
| `test_script` 契约（§4.1） | `value`=脚本源码；脚本从 stdin 读 `final_output`；`returncode==0`→pass；`value` 非字符串/空 → 视作「无客观」 |
| `TEST_SCRIPT_TIMEOUT_SEC`（§4.2） | `5` 秒；超时用例 monkeypatch 成小值（0.2）避免拖慢全量测试 |
| `success_rate` 分母（§3.2） | `passed is True 数 / passed 非 None 数`；`passed=None` 不计分子也不计分母；无可判对错任务 → 0.0 |
| `BenchmarkReport`（§4.3） | `benchmark.py` 内 `@dataclass`（不进 models.py）；`per_task: list[(task_id, passed, total_score)]` + `success_rate` + `avg_total_score` + `to_dict()` |
| `BENCHMARKS_DIR` 角色（§2.2） | `load_tasks(path)` 显式路径；`load_tasks_by_name(name)` 用 `BENCHMARKS_DIR/{name}.json` 作默认根 |
| `load_tasks` JSON schema（§4.4） | 顶层 JSON 数组，每项 `BenchmarkTask` 字段；非数组 → `ValueError` |
| `objective` dict 键（§3.4） | test_script 用 `test_pass`，exact/contains 用 `matched`，均含 `status`/`type`（§7 注释既定） |
| 隔离措辞（§3.1） | 改称「崩溃/超时隔离」，不声称「防写宿主」；OS 沙箱登记为已知局限 |
| 防污染③ 定位（§3.3） | `Benchmark` 无导出经验 API（弱保证）；硬保证「EvolutionLoop 只挖 real trace」登记为 `0008` 约束 |
| tag/difficulty 过滤（§3.5） | 本事务**不实现**，登记为非目标 |
