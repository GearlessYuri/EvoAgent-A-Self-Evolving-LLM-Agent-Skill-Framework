# 事务 0005 计划（Plan）

> 规划者产出。遵循「文档精炼纪律」：引用而非复述，只写新增判断。

## 1. 当前状态

底座层（含 `llm.py`）、门面层、检索器已就绪（`0001`–`0004`，见 `project_state.md`）。`evoagent/execution/` 下仅 `trace.py`，无 `executor.py`/`tools.py`。正向流 §4 步骤 3（`AgentExecutor.run` → 输出 + Trace）断档。

## 2. 问题

`AgentExecutor` 缺失，闭环「检索 → 执行 → 写 trace」的执行环节无人承接。且 `LLMClient.complete() -> str` 丢弃 token/latency（`0004/result.md` §4 登记的扩展点），无法满足 §6 `ExecutionTrace.usage` 采集，须在本事务一并闭合。

## 3. 目标

落地执行层 `AgentExecutor`（**v1 单轮、无工具调用**），并给 `LLMClient` 增加 usage 采集的伴生方法：

- `evoagent/llm.py`：新增 `complete_with_usage()`（不改 `complete()`）
- `evoagent/execution/executor.py`：`AgentExecutor`（拼 prompt → LLM → 写 Trace）
- `tests/test_llm.py`（追加）、`tests/test_executor.py`（新建）

## 4. 范围

**做**：`llm.py` 加 `complete_with_usage`；`executor.py` 新建 `AgentExecutor`；两个测试文件。

**不做**：`tools.py`、工具调用 / function-calling、agent 多轮 loop、`max_steps`/`timeout`、`task` 类错误分类、`chat_json`、`Evaluator`、真实 LLM 请求（mock-first）。

## 5. 拟议变更

| 文件 | 变更 |
|---|---|
| `evoagent/llm.py` | 追加 `complete_with_usage(prompt) -> tuple[str, dict]`（§5.1） |
| `evoagent/execution/executor.py` | 新建 `AgentExecutor`（§5.2） |
| `tests/test_llm.py` | 追加 `complete_with_usage` 用例 |
| `tests/test_executor.py` | 新建（mock LLM） |

### 5.1 usage 扩展（`0004/result.md` §4 的路径 b：伴生方法）

```python
def complete_with_usage(self, prompt: str) -> tuple[str, dict]:
    # 返回 (content, {"total_tokens": int, "total_latency_ms": int})
```

- `total_tokens` 取 `resp.usage.total_tokens`（`resp.usage` 为 None 时记 0）；`total_latency_ms` 内部 `time.monotonic` 计时。
- **不改 `complete()`**；`complete()` 内部可改为复用 `complete_with_usage`（丢弃 usage），或保持独立实现（优化者定）。
- `total_cost` 因需定价表、设计未给，**不在此方法**返回；由 `AgentExecutor` 写 `usage` 时置 `0.0`（登记后续点）。

### 5.2 `AgentExecutor`（`execution/executor.py`）

```python
class AgentExecutor:
    def __init__(self, llm: LLMClient, trace_store: TraceStore): ...
    def run(self, task: Task, skill: Skill, *, retrieval_fallback: bool = False) -> ExecutionTrace: ...
```

- **流程**：生成 `trace_id`/`task_id`（`uuid4().hex`）→ 拼 prompt（`skill.prompt_template.format(task=task.task)` + few-shot 追加）→ `llm.complete_with_usage(prompt)` → 组 `steps` → 写 `trace_store.save(trace)` → 返回 trace。
- **steps**：`[TraceStep(0,"llm_call",prompt), TraceStep(1,"final",answer)]`。
- **status / error_type**：成功 → `success`/`""`；LLM 抛异常 → `error`/`"infra"`（§3.2 的 infra 类；`task` 类、`timeout`/`max_steps` 因无 loop/工具，本事务不产出）。
- **usage**：`{"total_tokens": ..., "total_cost": 0.0, "total_latency_ms": ...}`（v1 单次调用聚合；`total_cost` 占位）。
- **`retrieval_fallback`**：由调用方（未来 Loop/CLI）据 `RetrievalResult.fallback` 传入，本事务只落字段。
- **分层**：只调 `llm` / `trace_store`，不 `import sqlite3`、不 `import Storage`。

## 6. 依赖

- 运行时：标准库（`uuid`/`time`/`typing`）+ 既有 `openai`（经 `llm.py` 惰性 import）。无新第三方。
- 顺序：`llm.py`（加方法）→ `executor.py` → 测试。
- 既有模块：`LLMClient`（`0004`）、`TraceStore`（`0002`）、`Task`/`Skill`/`TraceStep`/`ExecutionTrace`（`models.py`）。
- 无 config 变更。

## 7. 风险

| 风险 | 缓解 |
|---|---|
| `complete_with_usage` 与 `complete` 逻辑重复 / 不一致 | 优化者裁定二选一（复用 vs 独立）；测试分别锁定两者行为 |
| `resp.usage` 为 None（部分 provider/流式）致崩溃 | `complete_with_usage` 对 `resp.usage` 缺失记 0 |
| prompt 模板含非法占位符 → `format()` 抛 KeyError | 视为 skill 作者责任，异常按 infra 记 error trace（或优化者另裁定分类）；不吞 |
| `usage.total_cost=0.0` 是占位，误当作真实成本 | 明确登记「定价未实现」为已知局限，`result.md` 记录 |
| `task_id`/`trace_id` 用 uuid 不可复现，测试难断言 | 测试不预测 ID，改用「写后 `TraceStore.get(trace.trace_id)` 回读相等」断言；或 `run` 支持注入 ID（优化者定） |
| 范围蔓延（把 tools.py / loop / Evaluator 带进） | §4 非目标逐条列出 |

## 8. 实施顺序

1. `llm.py` 加 `complete_with_usage`。
2. `tests/test_llm.py` 追加用例。
3. `executor.py` 实现 `AgentExecutor`。
4. `tests/test_executor.py`。
5. 验证（§10）。

## 9. 验收标准

1. `llm.py` 新增 `complete_with_usage`，`complete()` 行为不变（既有 `test_llm.py` 无回归）。
2. `executor.py` 存在且可导入；`AgentExecutor` 只调 `llm`/`trace_store`（grep 无 `import sqlite3`/`Storage`）。
3. `run(task, skill)` 生成 trace 并写入 `TraceStore`；`TraceStore.get(trace.trace_id)` 回读字段一致。
4. prompt 填充：`prompt_template` 的 `{task}` 被 `task.task` 替换，few-shot 被纳入。
5. 成功路径：`final_output == mock 回答`、`status=="success"`、`error_type==""`、`usage` 含三键且 `total_cost==0.0`、`steps` 为 `[llm_call, final]`。
6. 失败路径：mock LLM 抛异常 → `status=="error"`、`error_type=="infra"`、`final_output==""`。
7. `retrieval_fallback` 参数正确落入 trace 字段。
8. 测试：`test_executor.py` + 追加后的 `test_llm.py` 全绿，全量 `python -m pytest` 无回归；全程 mock、不发真实请求。
9. 无越界：不含 tools.py/tool calling/loop/`task` 错误分类/`chat_json`/`Evaluator`/真实请求。

## 10. 验证策略

```
python -m pytest tests/test_llm.py tests/test_executor.py -v
python -m pytest -v        # 全量回归
```

- `test_llm.py`：`complete_with_usage` 返回 `(text, {"total_tokens", "total_latency_ms"})`；`resp.usage=None` → tokens 0；`complete()` 仍只回 str。
- `test_executor.py`（mock `LLMClient` + `tmp_path` `TraceStore`）：成功 / 异常（infra）/ prompt 填充 / usage / retrieval_fallback 落字段 / 写后回读一致。
- 人工复核：`grep -rn "import sqlite3" evoagent/` 仅 `storage.py`；`executor.py` 不出现。
