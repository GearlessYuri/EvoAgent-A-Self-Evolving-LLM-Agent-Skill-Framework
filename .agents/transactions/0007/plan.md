# 事务 0007 计划（Plan）

> 规划者产出。遵循「文档精炼纪律」：引用而非复述，只写新增判断。

## 1. 当前状态

底座/门面/执行层/评估层核心已就绪（`0001`–`0006`）。`eval/` 下无 `benchmark.py`；`Evaluator` 六分支就绪但 `test_script` 视作「无客观」（`evaluator.py:74-76` 注释延后）；`config.py` 无 benchmark 相关常量；`BenchmarkTask` 模型已就绪。

## 2. 问题

缺「尺子」：无 `Benchmark`，`Validator` 的 A/B（§9）无从衡量。且 §11 的防污染三规则未落地为代码可见的隔离，`test_script` 客观执行（§7）缺失。

## 3. 目标

落地 `Benchmark`（任务集加载 + 批量「执行→评估→汇总」+ 报告），补 `test_script` 客观执行，并把防污染三规则落实为代码可见机制：

- `evoagent/eval/benchmark.py`：`Benchmark` + `load_tasks` + 汇总
- `evoagent/eval/evaluator.py`：补 `test_script` 客观分支（子进程 + 超时）
- `evoagent/config.py`：加 `BENCHMARKS_DIR`、`TEST_SCRIPT_TIMEOUT_SEC`
- 测试：`test_benchmark.py`（新建）、`test_evaluator.py`（追加）

## 4. 范围与工作量判断

**做**：上述 3 源文件 + 2 测试文件。**SkillEvolver 顺延 `0008`**——理由：本事务已含任务集加载 + 批量编排 + `test_script` 安全设计 + 防污染隔离（评审重点），体量已足；SkillEvolver 与 Benchmark 无耦合、且与 `Validator`（A/B）成对，归 `0008` 更聚焦。

**不做**：`SkillEvolver`/`Validator`/`EvolutionLoop`/`cli.py`/`tools.py`、win_rate A/B（属 Validator）、report 落盘文件（本事务只产出 `BenchmarkReport` 数据对象 + `to_dict`，文件 I/O 延后）、真实 LLM 请求（全程 mock）。

## 5. 拟议变更

| 文件 | 变更 |
|---|---|
| `evoagent/config.py` | 追加 `BENCHMARKS_DIR`、`TEST_SCRIPT_TIMEOUT_SEC` |
| `evoagent/eval/evaluator.py` | 补 `test_script` 客观分支 + `_run_test_script` 子进程 helper（§5.1） |
| `evoagent/eval/benchmark.py` | 新建 `Benchmark` + `load_tasks` + `BenchmarkReport`（§5.2） |
| `tests/test_evaluator.py` | 追加 `test_script` 用例 |
| `tests/test_benchmark.py` | 新建 |

### 5.1 `test_script` 客观执行（§7，安全边界）

在 `evaluator.py` 新增模块级 `_run_test_script(script: str, output: str) -> tuple[bool, str]`，并在 `evaluate` 加 `otype == "test_script"` 分支（**定论**，同 `exact`：跳过 judge、`eval_basis="objective"`、`passed=脚本结果`）。

**执行边界（本事务最易被追问点，钉死）**：

- **子进程隔离**（选子进程，非进程内）：`subprocess.run([sys.executable, "-c", script], input=output, text=True, capture_output=True, timeout=config.TEST_SCRIPT_TIMEOUT_SEC)`；脚本从 **stdin** 读 `final_output`，`returncode == 0` → pass、非 0 → fail。
- **超时**：`subprocess.TimeoutExpired` → 捕获 → `(False, "timeout")`，不崩溃。
- **异常处理**：非零退出、`OSError`、任何异常均捕获 → `(False, detail)`；**绝不**让脚本异常逃逸到 evaluate 外。
- **`objective` dict**：`{"status", "type": "test_script", "test_pass": bool}`；`total_score = 1.0/0.0`。

### 5.2 `Benchmark`（`eval/benchmark.py`）

```python
def load_tasks(path: str) -> list[BenchmarkTask]: ...   # JSON → BenchmarkTask.from_dict
class Benchmark:
    def __init__(self, executor: AgentExecutor, evaluator: Evaluator): ...
    def run(self, tasks: list[BenchmarkTask], skill: Skill) -> BenchmarkReport: ...
class BenchmarkReport:  # benchmark.py 内 NamedTuple/dataclass（不进 models.py）
    # per_task: list[(task_id, passed, total_score)]；success_rate；avg_total_score
```

- **批量流**：每个 task → `Task(task=bt.task, task_source="benchmark")` → `executor.run(task, skill)` → `evaluator.evaluate(trace, task, reference_answer=bt.reference_answer, rubric=bt.rubric, objective_check=bt.objective_check)` → 汇总。
- **指标**（§11 单技能跑分）：`success_rate`（`passed==True` 占比）、`avg_total_score`（`total_score` 均值）。`win_rate`（A/B）属 Validator，不在本事务。
- **报告**：`BenchmarkReport.to_dict()`（JSON-ready）；落盘 `report.json`/`report.md` 属 Validator A/B 报告，延后。

**防污染三规则（代码可见，非注释）**：

1. **来源隔离**：`Task(task_source="benchmark")` 由 Benchmark 固定写入，Trace 落库该字段为 `"benchmark"`。
2. **答案隔离**：`reference_answer`/`rubric`/`objective_check` **只传 `evaluator.evaluate`**；`executor.run` 收到的 `Task` 仅含 `task` 文本（`_render_prompt` 只用 `task.task`），参考答案**结构上不进入执行路径**。
3. **extension 只考不学**：regression/extension 分别 `load_tasks` 各自文件；`run` 只产出报告，**无任何 API 把 extension 结果导出为经验**（经验接口属未来 Loop）。

## 6. 依赖

- 运行时：标准库（`json`/`subprocess`/`sys`/`uuid`/`typing`）+ 既有 `openai`（经 `llm.py`）。无新第三方。
- 顺序：`config.py`（加常量）→ `evaluator.py`（test_script）→ `benchmark.py` → 测试。
- 既有：`AgentExecutor`（`0005`）、`Evaluator`（`0006`）、`BenchmarkTask`/`Skill`/`Task`/`ExecutionTrace`（`models.py`）。

## 7. 风险

| 风险 | 缓解 |
|---|---|
| **test_script 逃逸/挂死**（恶意脚本、死循环、写宿主） | 子进程 + `timeout` + 全异常捕获（§5.1）；超时/非零退出均 fail；单测覆盖超时与异常脚本 |
| **防污染是「注释级」而非「结构级」** | §5.2 三条各配测试：Trace 落库 `task_source=="benchmark"`；executor prompt 不含 `reference_answer`；extension 无导出经验接口 |
| **客观规则误判**（exact 空值、test_script 无 stdin 约定） | 优化者钉死脚本 stdin 契约与 `value` 缺省处理；单测覆盖 |
| **报告口径**（success_rate 分母、passed=None 计入否） | 钉死：`passed is True` 计分子，`passed is None` 不计入成功率分子但计入分母（或由优化者定）；单测锁定 |
| 范围蔓延（A/B/演化带进） | §4 非目标逐条列出 |

## 8. 实施顺序

1. `config.py` 加 `BENCHMARKS_DIR`/`TEST_SCRIPT_TIMEOUT_SEC`。
2. `evaluator.py` 加 `_run_test_script` + `test_script` 分支 + `test_evaluator.py` 追加。
3. `benchmark.py`（`load_tasks` → `Benchmark.run` → `BenchmarkReport`）。
4. `test_benchmark.py`。
5. 全量验证（§10）。

## 9. 验收标准

1. `config.py` 新增 `BENCHMARKS_DIR`/`TEST_SCRIPT_TIMEOUT_SEC`；既有常量不动。
2. `evaluator.py` 的 `test_script` 分支：子进程执行、`returncode==0`→`test_pass=True`（`eval_basis="objective"`、跳过 judge）、非零/超时/异常→`test_pass=False`；不逃逸异常。
3. `Benchmark.run` 批量执行+评估，返回 `BenchmarkReport`，`success_rate`/`avg_total_score` 口径正确（`passed=None` 不计入 success 分子）。
4. **防污染①**：跑后 `TraceStore` 中相关 trace 的 `task_source=="benchmark"`。
5. **防污染②**：`reference_answer` 为某哨兵串时，executor 的 `steps[0]`（llm_call）prompt **不含**该哨兵（结构隔离验证）。
6. **防污染③**：`load_tasks` 分别加载 regression/extension 文件；`run` 无任何「导出经验」接口。
7. 测试全绿（`test_benchmark` + 追加后 `test_evaluator` + 全量无回归），全程 mock、不发真实请求、test_script 用无害脚本。
8. 无越界：不含 SkillEvolver/Validator/EvolutionLoop/win_rate A/B/report 文件 I/O/真实请求。

## 10. 验证策略

```
python -m pytest tests/test_evaluator.py tests/test_benchmark.py -v
python -m pytest -v        # 全量回归
```

- `test_evaluator.py`（追加）：`test_script` 脚本 `returncode==0` → `objective`/`test_pass=True`；`sys.exit(1)` → `False`；`while True: pass`（超时）→ `False`；脚本抛异常 → `False` 不逃逸。
- `test_benchmark.py`（mock `AgentExecutor` + `Evaluator`）：批量跑回归、汇总口径、`task_source=="benchmark"` 落库、reference_answer 哨兵不进 executor prompt、regression/extension 分文件加载。
- 人工复核：`grep -rn "import sqlite3" evoagent/` 仅 `storage.py`；`benchmark.py` 不出现。
