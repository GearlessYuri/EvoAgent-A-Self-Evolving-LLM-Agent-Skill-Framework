# 事务 0005 最终任务规格说明（Task）

> 优化者（Optimizer）产出。本文件是编码者实现的**唯一依据**，自包含：编码者无需阅读 `plan.md` / `review.md` 即可执行。
> 依据：`plan.md` + `review.md` + `docs/system_design.md` + 事务 `0001`–`0004` 落地后的实仓源码 + 实仓核实。
>
> 说明：本仓库事务文件实际位于 `.agents/transactions/0005/`（顶层 `transactions/` 不存在）。下文路径均以 `.agents/transactions/0005/` 为准。

---

## 1. 目标（Objective）

落地执行层 `AgentExecutor`（**v1 单轮、无工具调用**），并给 `LLMClient` 增加 usage 采集的伴生方法，闭合 `0004/result.md` §4 登记的 usage 扩展点（取路径 b：伴生方法，**不改 `complete()` 的窄契约**）：

- `evoagent/llm.py`：新增 `complete_with_usage()`（不改 `complete()` 对外行为）
- `evoagent/execution/executor.py`：`AgentExecutor`（拼 prompt → LLM → 写 Trace）
- `tests/test_llm.py`（追加）、`tests/test_executor.py`（新建）

成果须通过 `pytest` 验证，全程 mock、不发真实请求；除收尾提交外不做任何 git 操作。

## 2. 上下文（Context）

- 事务 `0001`–`0004` 已落地：底座层（含 `llm.py`）、存储门面层、检索器。全量 68 项测试通过，git `main`@`fa420b7`。
- **实仓现状（已核实）**：
  - `evoagent/llm.py`：`LLMClient` 仅 `complete(prompt) -> str` 一个公开方法；`_get_client()` 惰性 `import openai`；`complete()` 直接 `create()` 后取 `resp.choices[0].message.content`，**无计时、无 usage 返回**；`content=None` 时返回 `""`。
  - `evoagent/execution/` 下仅 `__init__.py` 与 `trace.py`（`TraceStore.save/get/list` 已就绪），**无 `executor.py`/`tools.py`**。
  - `ExecutionTrace`（`models.py`）字段：`trace_id`/`task_id`/`task_source`/`skill_id`/`skill_version`/**`started_at`（必填 str）**/**`ended_at`（必填 str）**/`steps`/`final_output`/`status`/`error`（默认 `""`）/`error_type`（默认 `""`）/`retrieval_fallback`（默认 `False`）/`usage`（`dict | None`，注释三键）。
  - `TraceStep`：`step_index`/`type`/`content`/`tool_name`（默认 `""`）/`tokens`（默认 `0`）/`latency_ms`（默认 `0`）。
  - `Task` **无 `task_id`**（`0003` 用户裁定）；`RetrievalResult(skill, score, fallback)` 的 `fallback` 即 `retrieval_fallback` 信号源；`Skill.prompt_template`/`few_shots` 为检索/注册表的现成字段。
- **设计分层（§2）**：`executor.py` 属执行层，只调 `llm` 与 `trace_store`，不 `import sqlite3`、不 `import Storage`。
- **环境**：Python 3.13.9（≥3.10）、pytest 8.4.2。

## 3. 范围（Scope）

**做（In scope）**

1. `evoagent/llm.py`：新增 `complete_with_usage()`，并让 `complete()` 复用之（§4.1）。
2. `evoagent/execution/executor.py`：`AgentExecutor`（§4.2）。
3. `tests/test_llm.py`：追加 `complete_with_usage` 用例（§4.3）。
4. `tests/test_executor.py`：新建（§4.3）。

**不做（Out of scope，明确非目标）** —— 详见 §11。

## 4. 需求（Requirements）

### 4.1 `evoagent/llm.py` —— 追加 `complete_with_usage()`（伴生方法，路径 b）

在 `llm.py` 顶部 `import os` 之后追加 `import time`；在 `LLMClient` 内**新增**以下方法，并**改写** `complete()` 为复用：

```python
def complete_with_usage(self, prompt: str) -> tuple[str, dict]:
    """返回 (content, usage)。usage 为 §6 三键：total_tokens / total_cost / total_latency_ms。"""
    start = time.monotonic()
    resp = self._get_client().chat.completions.create(
        model=config.LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    latency_ms = int((time.monotonic() - start) * 1000)

    content = resp.choices[0].message.content
    content = content if content is not None else ""

    usage = getattr(resp, "usage", None)
    total_tokens = getattr(usage, "total_tokens", 0) if usage is not None else 0

    return content, {
        "total_tokens": total_tokens,
        "total_cost": 0.0,          # 定价未实现，占位（见 §11.10）
        "total_latency_ms": latency_ms,
    }


def complete(self, prompt: str) -> str:
    content, _ = self.complete_with_usage(prompt)
    return content
```

**语义钉死（裁定）**：

- **返回类型**：`tuple[str, dict]`；`dict` 为 **§6 完整 3 键** `{total_tokens, total_cost, total_latency_ms}`（`total_cost` 统一由 `llm.py` 占位 `0.0`，**不**由执行层补——成本占位点集中在一处）。
- **`total_tokens`**：`resp.usage` 为 `None` 时记 `0`；否则取 `resp.usage.total_tokens`（用 `getattr(resp, "usage", None)` + `getattr(usage, "total_tokens", 0)`，容错缺失字段）。
- **`total_latency_ms`**：`time.monotonic()` 计时（秒），`int((end - start) * 1000)` 取整为毫秒。
- **`complete()` 复用（裁定）**：`complete()` 改为一行 `return self.complete_with_usage(prompt)[0]`。对外行为不变（仍只返回 `str`、`content=None` 仍返回 `""`），既有 `test_llm.py` 5 个用例**必须无回归**。
- **不改**：`__init__(client=None)`、`_get_client()`、惰性 `import openai`、key 校验；注入路径仍不 import openai（`complete_with_usage` 只多 `time.monotonic` 与 `getattr`，均不触碰 openai）。

### 4.2 `AgentExecutor`（`evoagent/execution/executor.py`）

**为什么存在**：把「用某 Skill 执行某任务」封装成一次可记录、可重放的过程，是 Trace 的来源（§3.2）。

**精确实现（含 prompt 渲染 helper）**：

```python
"""执行器 v1：单轮、无工具调用（§3.2 骨架）。

拼 prompt（模板 `{task}` 替换 + few-shot 追加）→ 调 `LLMClient.complete_with_usage` →
写 `TraceStore`。只调 `llm` / `trace_store`，不 import sqlite3 / Storage。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from ..llm import LLMClient
from ..models import ExecutionTrace, Skill, Task, TraceStep
from .trace import TraceStore


def _render_prompt(skill: Skill, task: Task) -> str:
    """拼 prompt：`{task}` 替换为任务文本 + few-shot 追加（确定性格式）。"""
    prompt = skill.prompt_template.replace("{task}", task.task)
    if skill.few_shots:
        shots = []
        for i, fs in enumerate(skill.few_shots, start=1):
            shots.append(f"示例 {i}：\n输入：{fs.input}\n输出：{fs.output}")
        prompt = prompt + "\n\n" + "\n\n".join(shots)
    return prompt


class AgentExecutor:
    def __init__(self, llm: LLMClient, trace_store: TraceStore):
        self.llm = llm
        self.trace_store = trace_store

    def run(self, task: Task, skill: Skill, *, retrieval_fallback: bool = False) -> ExecutionTrace:
        trace_id = uuid.uuid4().hex
        task_id = uuid.uuid4().hex
        started_at = datetime.now(timezone.utc).isoformat()

        prompt = _render_prompt(skill, task)

        try:
            answer, usage = self.llm.complete_with_usage(prompt)
        except Exception as exc:  # 仅捕获 LLM 调用异常；模板渲染已用 replace，不会抛
            ended_at = datetime.now(timezone.utc).isoformat()
            trace = ExecutionTrace(
                trace_id=trace_id,
                task_id=task_id,
                task_source=task.task_source,
                skill_id=skill.skill_id,
                skill_version=skill.version,
                started_at=started_at,
                ended_at=ended_at,
                steps=[TraceStep(step_index=0, type="llm_call", content=prompt)],
                final_output="",
                status="error",
                error=str(exc),
                error_type="infra",
                retrieval_fallback=retrieval_fallback,
                usage=None,
            )
            self.trace_store.save(trace)
            return trace

        ended_at = datetime.now(timezone.utc).isoformat()
        trace = ExecutionTrace(
            trace_id=trace_id,
            task_id=task_id,
            task_source=task.task_source,
            skill_id=skill.skill_id,
            skill_version=skill.version,
            started_at=started_at,
            ended_at=ended_at,
            steps=[
                TraceStep(step_index=0, type="llm_call", content=prompt),
                TraceStep(step_index=1, type="final", content=answer),
            ],
            final_output=answer,
            status="success",
            error="",
            error_type="",
            retrieval_fallback=retrieval_fallback,
            usage=usage,
        )
        self.trace_store.save(trace)
        return trace
```

**语义钉死（裁定）**：

- **构造签名**：`AgentExecutor(llm: LLMClient, trace_store: TraceStore)`（依赖注入，便于测试）。
- **返回契约（裁定）**：`run()` **只返回 `ExecutionTrace`**（`final_output` 已在 `trace.final_output` 与 `steps[1].content` 内），不额外返回并列的输出。
- **`trace_id`/`task_id`**：均 `uuid.uuid4().hex`（每次执行新值）。
- **`started_at`/`ended_at`（§2.1 钉死）**：`datetime.now(timezone.utc).isoformat()`（UTC ISO-8601 字符串）；`started_at` 在 LLM 调用前取、`ended_at` 在调用后取。
- **prompt 渲染（§3.5/§4.2 钉死）**：用 `str.replace("{task}", task.task)`，**不用 `.format()`**——只替换 `{task}`、字面花括号与其它占位符原样保留、**永不抛 KeyError**；few-shot 追加格式固定为 `示例 {i}：\n输入：{input}\n输出：{output}`，多个示例以 `\n\n` 连接，整体以 `\n\n` 接在模板后。
- **成功路径**：`status="success"`、`error=""`、`error_type=""`、`final_output=answer`、`steps=[TraceStep(0,"llm_call",prompt), TraceStep(1,"final",answer)]`、`usage` 为 `complete_with_usage` 返回的三键 dict。
- **失败路径**：LLM 调用抛异常 → `status="error"`、`error_type="infra"`（§3.2 的 infra 类）、`error=str(exc)`、`final_output=""`、`steps=[TraceStep(0,"llm_call",prompt)]`、`usage=None`。**只捕获 LLM 调用异常**；模板渲染用 `.replace` 不会抛，故无「模板错误归类」问题（§2.2 已通过改用 `.replace` 消解）。
- **`retrieval_fallback`**：由调用方（未来 Loop/CLI）据 `RetrievalResult.fallback` 传入，本事务只落字段，不做判断。
- **`skill.tools` 忽略**（v1 无工具调用）。
- **分层**：只调 `llm`/`trace_store`，不 `import sqlite3`、不 `import Storage`。

### 4.3 测试要求

- `tests/test_llm.py`（追加）：见 §10。
- `tests/test_executor.py`（新建）：见 §10，mock `LLMClient` + `tmp_path` `TraceStore`，全程不发真实请求。

## 5. 约束（Constraints）

1. **语言 / 运行时**：Python 3.10+（本机 3.13.9）；类型注解统一 `X | None`。
2. **运行时依赖**：仅标准库（`uuid`/`time`/`datetime`/`typing`）；不新增第三方（`openai` 仍经 `llm.py` 惰性 import）。
3. **分层**：`executor.py` 只调 `llm`/`trace_store`；`storage.py` 仍是全项目唯一 `import sqlite3`/写 SQL 处。
4. **不改既有**：`complete()` 对外行为不变（既有 `test_llm.py` 无回归）；不改 `models.py`/`storage.py`/`trace.py`/`retriever.py`/`registry.py`/`config.py`（**本事务无 config 变更**）。
5. **不越界**：不实现 `tools.py`/工具调用/多轮 loop/`max_steps`/`timeout`/`task` 类错误分类/`chat_json`/`Evaluator`/真实 LLM 请求。
6. **命名**：类 `PascalCase`、方法/函数 `snake_case`、常量 `UPPER_SNAKE_CASE`；`_render_prompt` 为模块级私有函数。
7. **错误处理**：仅捕获 LLM 调用异常（记 infra error trace），其余不吞；不自定义异常类。

## 6. 相关文件 / 模块（Relevant Files / Modules）

**本事务新建：**

| 文件 | 内容 |
|---|---|
| `evoagent/execution/executor.py` | `AgentExecutor` + `_render_prompt`（§4.2） |
| `tests/test_executor.py` | mock-first 单测（§4.3/§10） |

**本事务修改：**

| 文件 | 变更 |
|---|---|
| `evoagent/llm.py` | 追加 `complete_with_usage()` + `import time`；`complete()` 改为复用（§4.1） |
| `tests/test_llm.py` | 追加 `complete_with_usage` 用例（§4.3/§10） |

**只读参照（不修改）：** `evoagent/models.py`、`evoagent/storage.py`、`evoagent/skills/registry.py`、`evoagent/skills/retriever.py`、`evoagent/execution/trace.py`、`evoagent/config.py`、`docs/system_design.md`、`.agents/transactions/0001/`–`0005/` 的历史产物（`plan.md`/`review.md` 等不可改）。

## 7. 推荐的实现策略（Recommended Implementation Strategy）

依赖关系：`llm.py`（加 `complete_with_usage` + 复用 `complete`）→ `tests/test_llm.py`（追加）→ `executor.py`（`AgentExecutor`）→ `tests/test_executor.py` → 验证 → 收尾提交。

1. **`llm.py`**：加 `import time`；按 §4.1 加 `complete_with_usage`，`complete()` 改为复用。
2. **`tests/test_llm.py`**：追加 `complete_with_usage` 用例，并确认既有 5 用例无回归。
3. **`executor.py`**：按 §4.2 实现 `_render_prompt` + `AgentExecutor.run`。
4. **`tests/test_executor.py`**：按 §10 写。
5. **验证**：运行 §10 命令，确认全绿。
6. **收尾提交**：按 §10 末尾执行。

## 8. 预期变更（Expected Changes）

| 文件 | 变更性质 |
|---|---|
| `evoagent/llm.py` | 修改：追加 `complete_with_usage()` + `import time`；`complete()` 改为复用（对外行为不变） |
| `evoagent/execution/executor.py` | 新建 |
| `tests/test_llm.py` | 修改：追加 `complete_with_usage` 用例 |
| `tests/test_executor.py` | 新建 |

（不修改 `models.py`、`storage.py`、`trace.py`、`registry.py`、`retriever.py`、`store.py`、`config.py`、`__init__.py`、`pyproject.toml`、`requirements.txt`、`docs/system_design.md`；不产生运行时数据文件。）

## 9. 验收标准（Acceptance Criteria）

1. **`llm.py`**：新增 `complete_with_usage(prompt) -> tuple[str, dict]`；`complete()` 对外行为不变（仍返回 `str`、`content=None` 仍返回 `""`），既有 `test_llm.py` 5 用例**无回归**。
2. **usage 形状**：`complete_with_usage` 返回的 dict 恰为 §6 三键 `{total_tokens, total_cost, total_latency_ms}`，且 `total_cost == 0.0`；`resp.usage` 缺失时 `total_tokens == 0`；`total_latency_ms` 为非负 `int`。
3. **`executor.py`**：存在且可导入；`AgentExecutor` 只调 `llm`/`trace_store`（grep 无 `import sqlite3`/`Storage`）。
4. **写后回读**：`run(task, skill)` 生成 trace 并写入 `TraceStore`；`TraceStore.get(trace.trace_id)` 重建后 `task_id`/`task_source`/`skill_id`/`skill_version`/`status`/`error_type`/`final_output`/`retrieval_fallback` 与写入一致；`started_at`/`ended_at` 为非空字符串。
5. **prompt 填充**：`steps[0]`（llm_call）的 `content` 含 `task.task` 替换结果，且（有 few-shot 时）含每个示例的 `input`/`output`；`{task}` 之外的占位符/花括号字面保留（`.replace` 行为）。
6. **成功路径**：mock LLM 返回答案 → `status=="success"`、`error_type==""`、`final_output==答案`、`usage` 含三键且 `total_cost==0.0`、`steps` 为 `[llm_call, final]` 两步且 `step_index` 为 0/1。
7. **失败路径**：mock LLM 抛异常 → `status=="error"`、`error_type=="infra"`、`final_output==""`、`usage is None`、`steps` 仅 `[llm_call]` 一步。
8. **`retrieval_fallback`**：`run(..., retrieval_fallback=True)` 后 trace 的 `retrieval_fallback` 为 `True`（默认 `False`）。
9. **测试**：`test_executor.py` + 追加后的 `test_llm.py` 全绿，全量 `python -m pytest` 无回归；全程 mock、不发真实请求。
10. **无越界**：不含 `tools.py`/工具调用/多轮 loop/`max_steps`/`timeout`/`task` 错误分类/`chat_json`/`Evaluator`/真实 LLM 请求。

## 10. 验证策略（Verification Strategy）

在项目根目录运行：

```
python -m pytest tests/test_llm.py tests/test_executor.py -v
```

并确认全量回归：

```
python -m pytest -v
```

**用例要求：**

- `tests/test_llm.py`（追加）：
  - `complete_with_usage` 返回 `(text, usage)`，`usage` 含 `total_tokens`/`total_cost`/`total_latency_ms` 三键、`total_cost == 0.0`。
  - fake `resp.usage=None` → `total_tokens == 0`；fake `resp.usage.total_tokens=42` → `total_tokens == 42`。
  - `complete()` 仍只返回 `str`，且 `complete(p) == complete_with_usage(p)[0]`。
- `tests/test_executor.py`（mock `LLMClient` + `tmp_path` `TraceStore`，全程 mock）：
  - 注入 fake `llm`（暴露 `complete_with_usage(prompt) -> tuple[str, dict]`，可设返回答案或抛异常）与 `TraceStore(Storage(tmp_path/"x.db"))`。
  - 成功 / 异常（infra）/ prompt 填充 / usage 三键 / `retrieval_fallback` 落字段 / 写后回读一致 / `started_at`/`ended_at` 非空。
  - 断言 `steps` 的 `type` 与 `step_index`（成功 `["llm_call","final"]`、失败 `["llm_call"]`）。

**额外人工复核（非 pytest，编码者确认并记入 `execution.md`）：**

```
grep -rn "import sqlite3" evoagent/
```

真实 `import sqlite3` 语句**只**应出现在 `evoagent/storage.py`；`executor.py` 不得出现、也不得访问 `storage.conn`。

**收尾提交（用户已授权，必须执行）**：

全部验证通过后，Coder **一次性提交全部变更**：

```
git add -A && git commit -m "0005: 落地执行层 AgentExecutor 与 usage 采集扩展"
```

- 提交信息**首行**必须以 `0005: ` 开头 + 一句目标概括（上例为建议措辞，可用同义简洁一句话）。
- **不 push、不 amend、不建分支、不 force-push**（仅本地提交）。
- **把提交哈希记入 `result.md`**（`git rev-parse HEAD` 取哈希）。

## 11. 明确的非目标（Explicit Non-Goals）

本任务**不做**以下任何事（防止范围蔓延）：

1. **`evoagent/execution/tools.py`**、工具调用 / function-calling、`Skill.tools` 的加载校验、文件沙箱（§3.2 工具边界）。
2. **agent 多轮 loop**、`max_steps`、`timeout`（§3.2 的 loop 属后续事务；本事务单轮）。
3. **`task` 类错误分类**（§3.2 `error_type="task"`）——v1 单轮无工具模式下不会发生，且模板渲染已用 `.replace` 消除模板错误；本事务只产出 `infra` 类错误 trace。
4. **`chat_json()`**、结构化输出（`Evaluator`/`ExperienceExtractor` 未来需求）。
5. **`Evaluator`/`ExperienceExtractor`/`Benchmark`/`SkillEvolver`/`Validator`/`EvolutionLoop`/`cli.py`**。
6. **真实 LLM 调用 / 网络请求**（全程 mock）。
7. **修改 `docs/system_design.md`**（只读）。
8. **除收尾提交（§10）外的任何 git 操作**：不 push、不 amend、不建分支、不 force-push、不拆多次提交。
9. **`Task` 携带稳定 `task_id`**：本事务按 `0003` 用户裁定（`Task` 无 `task_id`），`task_id` 由 executor 每次执行 `uuid4()` 生成。此为**已登记的已知局限与后续决策点**——`task_id`/`trace_id` 语义趋同（每次执行新值），未来「任务关联 / 重试」需 `Task` 携带稳定 id，属后续事务。
10. **`total_cost` 真实化**：`total_cost` 恒为占位 `0.0`（定价表设计未给）。此为**已登记的已知局限**；未来定价表落地时在 `complete_with_usage` 集中实现，不拆散到执行层。

---

### 已确认的决策（记录以备查；无「实现前需确认」的阻塞项）

| 裁定点 | 结论 |
|---|---|
| `started_at`/`ended_at` 生成 | `datetime.now(timezone.utc).isoformat()`（UTC ISO-8601）；start 在 LLM 前、end 在 LLM 后 |
| prompt 渲染 | `str.replace("{task}", task.task)`（**非 `.format()`**），只替换 `{task}`、字面花括号保留、永不抛 KeyError |
| few-shot 格式 | `示例 {i}：\n输入：{input}\n输出：{output}`，多示例以 `\n\n` 连接，整体以 `\n\n` 接在模板后 |
| `complete_with_usage` 签名 | `(prompt) -> tuple[str, dict]`，dict 为 §6 三键，`total_cost=0.0` 由 `llm.py` 集中占位 |
| `total_tokens` | `getattr(resp, "usage", None)` → `getattr(usage, "total_tokens", 0)`，缺失记 0 |
| `total_latency_ms` | `time.monotonic()` 计时，`int((end-start)*1000)` 毫秒取整 |
| `complete()` 与 `complete_with_usage` 关系 | `complete()` 复用（`return self.complete_with_usage(prompt)[0]`），对外行为不变 |
| 模板错误归类 | 用 `.replace` 消解，无需归类；`run()` 仅捕获 LLM 调用异常记 infra，其余不吞 |
| `run()` 返回契约 | 只返回 `ExecutionTrace`（`final_output` 在 trace 内） |
| 失败路径 shape | `status="error"`/`error_type="infra"`/`final_output=""`/`usage=None`/`steps=[llm_call]` |
| 前瞻局限登记 | `task_id`/`trace_id` 均 uuid 语义趋同、`total_cost=0.0` 占位——写入 `result.md` 已知局限 |
