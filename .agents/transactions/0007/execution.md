# 事务 0007 执行报告（Execution）

> 编码者（Coder）产出。记录实际执行的步骤、重要实现决策及理由、与 `task.md` 的偏差、遇到的问题。

---

## 1. 实际执行的步骤

1. **阅读依据与核实**：阅读 `task.md`（完整）、`plan.md`/`review.md`/`context.md`（决策背景）、`project_state.md`、`active_transaction.md`、`docs/system_design.md`（§7/§11/§3.3/§13）。读实仓源码（`evaluator.py`、`executor.py`、`config.py`、`models.py`），确认与 task.md §2 一致（evaluator 六分支、`test_script` 视作「无客观」、`executor._render_prompt` 只用 `task.task`、`config` 无 benchmark 常量、`BenchmarkTask` 就绪）。
2. **按依赖顺序实现**：`config.py`（追加 2 常量）→ `evaluator.py`（`import subprocess`/`sys` + `_run_test_script` + normalization 改 + test_script 分支）→ `benchmark.py`（`load_tasks`/`load_tasks_by_name`/`BenchmarkReport`/`Benchmark`）→ `test_evaluator.py`（追加 5 用例）→ `test_benchmark.py`（新建 7 用例）。
3. **验证**：`import evoagent.eval.benchmark` 成功；`python -m pytest tests/test_evaluator.py tests/test_benchmark.py -v` → 20 passed；全量 `python -m pytest -v` → **104 passed**；`grep -rn "import sqlite3" evoagent/` 复核。
4. **收尾提交**：按 §10 授权执行（见下）。

## 2. 重要的实现决策及理由

### 2.1 `test_script` 客观定论分支 + `_run_test_script` 子进程 helper（§4.2 精确实现）
`_run_test_script(script, output)` 用 `subprocess.run([sys.executable, "-c", script], input=output, text=True, capture_output=True, timeout=config.TEST_SCRIPT_TIMEOUT_SEC)`，脚本从 stdin 读 `final_output`，`returncode==0`→pass；`TimeoutExpired`→`(False,"timeout")`；`OSError`/脚本异常全捕获→`(False, detail)`，绝不逃逸。`evaluate` 内 normalization 由 `("exact","contains")` 改为 `("exact","contains","test_script")`，新增「分支 2.5」：`value` 非字符串/空→`otype=None` 走 judge，否则子进程执行并 `objective` 定论（`test_pass` 键，跳过 judge）。

### 2.2 `Benchmark` + `BenchmarkReport`（§4.3 精确实现）
`load_tasks(path)` 严格 `BenchmarkTask.from_dict`（顶层非数组→`ValueError`）；`load_tasks_by_name(name)` 用 `BENCHMARKS_DIR/{name}.json`；`Benchmark.run(tasks, skill)` 每项 `Task(task=bt.task, task_source="benchmark")` → `executor.run` → `evaluator.evaluate(..., reference_answer/rubric/objective_check)` → 汇总；`success_rate = passed is True 数 / passed 非 None 数`（None 不计分母）、`avg_total_score` 全任务均值；`BenchmarkReport` 为 `benchmark.py` 内 `@dataclass`（不进 models.py），`to_dict()` JSON-ready、不落盘。

### 2.3 防污染三规则代码可见
① 来源隔离：`task_source="benchmark"` 固定写入并经 executor 落库；② 答案隔离：`reference_answer`/`rubric`/`objective_check` 只传 `evaluator.evaluate`，`executor.run` 的 `Task` 仅含 `task` 文本；③ extension 只考不学：`load_tasks_by_name` 分别加载，`Benchmark` 无导出经验 API。

### 2.4 分层与注入
`benchmark.py` 只编排 `executor`/`evaluator`；不 `import sqlite3`/`Storage`；测试用 mock executor/evaluator + 真实 `AgentExecutor`/`TraceStore`（tmp_path）全程不发真实 LLM 请求。

## 3. 与 task.md 的偏差

| 项 | 说明 | 是否范围外 |
|---|---|---|
| `benchmark.py` docstring 措辞 | §4.3 的 docstring 含「不 import sqlite3 / Storage」字面串，与 §9/§10 grep 冲突；改为「只编排 `AgentExecutor` + `Evaluator` 两个模块」（同 0005/0006 处理） | 否（注释措辞，满足 grep） |
| 更新既有 `test_unknown_objective_type_goes_to_judge` | §4.2 把 `test_script` 从「未知 type」改为「已知 type」，该 0006 用例以 `test_script` 作「未知 type」示例已失效；改为 `type="unknown_type"`（保持「未知 type→judge」语义，未削弱断言） | 否（§4.2 normalization 变更的必要测试修正） |

无功能性偏差：`evaluator.py` 六分支未动（仅加 test_script 分支/helper）；`config.py` 仅追加 2 常量；未改 `models.py`/`storage.py`/`store.py`/`experience.py`/`trace.py`/`executor.py`/`retriever.py`/`registry.py`/`llm.py`；未改 `docs/system_design.md`。

## 4. 遇到的问题

1. **§4.3「可选 reference_answer」与 `_from_dict` 严格性不一致**：task §4.3 声称 benchmark JSON 的 `reference_answer` 可选，但 `BenchmarkTask.from_dict`（0001 的 `_from_dict`）是严格的（`d[f.name]` 逐字段），缺 `reference_answer` 会 `KeyError`。因约束「不改 models.py」且 §4.3 给的是精确 `load_tasks` 代码，故**未改** `load_tasks`/`_from_dict`，测试 JSON 显式补 `reference_answer: ""`；把「reference_answer 实际必填」登记为已知局限（见 result.md）。
2. **§4.2 normalization 变更使 0006 用例失效**：见 §3 表格，已更新该用例的「未知 type」示例为 `unknown_type`，未削弱断言。
3. 无其它阻塞性问题。
