# 事务 0005 执行报告（Execution）

> 编码者（Coder）产出。记录实际执行的步骤、重要实现决策及理由、与 `task.md` 的偏差、遇到的问题。

---

## 1. 实际执行的步骤

1. **阅读依据与核实**：阅读 `task.md`（完整）、`plan.md`/`review.md`/`context.md`（决策背景）、`project_state.md`、`active_transaction.md`、`docs/system_design.md`（§3.2/§4/§6/§13）。读实仓源码（`llm.py`、`test_llm.py`、`trace.py`、`models.py`），确认与 task.md §2 一致（`LLMClient` 仅 `complete()` 无 usage/计时；`execution/` 无 `executor.py`；`ExecutionTrace.started_at/ended_at` 必填；`Task` 无 `task_id`）。
2. **按依赖顺序实现**：`llm.py`（加 `import time` + `complete_with_usage` + `complete()` 复用）→ `test_llm.py`（`_fake_client` 扩展 `usage` 参数 + 3 用例）→ `executor.py`（`_render_prompt` + `AgentExecutor`）→ `test_executor.py`（4 用例）。
3. **验证**：`import evoagent.execution.executor` 成功；`python -m pytest tests/test_llm.py tests/test_executor.py -v` → 12 passed；全量 `python -m pytest -v` → **75 passed**；`grep -rn "import sqlite3" evoagent/` 复核。
4. **收尾提交**：按 §10 授权执行（见下）。

## 2. 重要的实现决策及理由

### 2.1 `complete_with_usage()` 伴生方法（路径 b），`complete()` 复用
按 §4.1 精确实现：`complete_with_usage()` 用 `time.monotonic()` 计时、`getattr(resp, "usage", None)` 容错、返回 §6 三键 `{total_tokens, total_cost, total_latency_ms}`（`total_cost` 由 `llm.py` 集中占位 `0.0`）；`complete()` 改为一行 `return self.complete_with_usage(prompt)[0]`，对外行为不变（仍返回 `str`、`content=None` 仍返回 `""`）。

### 2.2 `AgentExecutor` 按 §4.2 精确实现
`run(task, skill, *, retrieval_fallback=False)` 只返回 `ExecutionTrace`；`trace_id`/`task_id` 均 `uuid4().hex`；`started_at`/`ended_at` 用 `datetime.now(timezone.utc).isoformat()`（start 在 LLM 前、end 在 LLM 后）；prompt 渲染用 `str.replace("{task}", task.task)`（非 `.format()`，只替换 `{task}`、字面花括号保留、永不抛 KeyError），few-shot 按 `示例 {i}：\n输入：{input}\n输出：{output}` 追加；成功 `status="success"` + `[llm_call, final]` 两步，LLM 异常 `status="error"` + `error_type="infra"` + `[llm_call]` 一步。

### 2.3 分层与注入
`executor.py` 只 `import` 并调用 `llm` / `trace_store`，不 `import sqlite3`、不 `import Storage`；`llm`/`trace_store` 均构造注入，测试用 fake LLM + `tmp_path` TraceStore 全程 mock。

## 3. 与 task.md 的偏差

| 项 | 说明 | 是否范围外 |
|---|---|---|
| `executor.py` docstring 措辞 | §4.2 给出的 docstring 模板含「不 import sqlite3 / Storage」字面串，与 §9.3/§10「grep 无 import sqlite3/Storage」直接冲突；改为「只依赖 `llm` / `trace_store` 两个模块」，保留原意、消除 grep 误命中（与 0002–0004 同款处理） | 否（注释措辞，满足 §9.3/§10 验证） |
| 收尾提交用 `git add <显式路径>` 而非 `git add -A` | 工作树存在**本事务之前就未跟踪的 `.agents/workflow/prompts/`**（工作区角色提示词，非 0005 产物）；`git add -A` 会把它混入 0005 提交，故改为显式 stage 本事务文件，`.agents/workflow/prompts/` 保持未跟踪（见 §4） | 否（避免范围外文件入提交） |

无功能性偏差：`llm.py` 仅加方法 + `import time`（`complete()` 对外行为不变，既有 5 用例无回归）；`executor.py` 新建；未改 `models.py`/`storage.py`/`trace.py`/`registry.py`/`retriever.py`/`config.py`；未改 `docs/system_design.md`。

## 4. 遇到的问题

1. **§4.2 docstring 与 §9.3/§10 grep 自相矛盾**：task.md 给定的 executor docstring 含「import sqlite3 / Storage」字面串，而 §9.3 验收要求「grep 无 import sqlite3/Storage」。已按 §3 表格方式消解（改 docstring 措辞）。
2. **pre-existing 未跟踪目录 `.agents/workflow/prompts/`**：该目录（`coder.md`/`optimizer.md`/`planner.md`/`reviewer.md` 四个角色提示词）在 0005 开始前即未跟踪（`git ls-files` 为空），非本事务产物、非本事务范围。收尾提交未将其纳入（见 §3），仍保持未跟踪，留待工作区层决定是否/何时提交。
