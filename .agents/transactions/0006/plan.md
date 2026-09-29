# 事务 0006 计划（Plan）

> 规划者产出。遵循「文档精炼纪律」：引用而非复述，只写新增判断。

## 1. 当前状态

底座层（含 `llm.py`）、门面层、执行层（`SkillRetriever`/`AgentExecutor`）已就绪（`0001`–`0005`）。`evoagent/eval/` 下仅 `store.py`，无 `evaluator.py`/`experience.py`。`config.py` 已含融合权重与 `PASS_THRESHOLD`（§7 所需），无需新增配置。

## 2. 问题

Trace 无评估出口：`ExecutionTrace` 无法变成 `EvaluationResult`（分数 + passed），演化无梯度（§7）。且 `chat_json` 扩展点未落地（§7 LLM-as-judge 依赖）。

## 3. 目标

落地评估层核心（「梯度来源」）：

- `evoagent/llm.py`：新增 `chat_json()`（judge 用，§7 解析兜底）
- `evoagent/eval/evaluator.py`：`Evaluator`（客观 + judge + 融合 + passed 三态）
- `evoagent/eval/experience.py`：`ExperienceExtractor`（Trace+Result → Experience[]）
- 测试：`test_llm.py`（追加）、`test_evaluator.py`、`test_experience.py`

## 4. 范围与工作量判断

**做**：上述 3 个源文件 + 3 个测试文件。**Benchmark 顺延至 `0007`**——理由：它是 `Validator` 的「尺子」（§3.3/§11），依赖 `AgentExecutor`+`Evaluator` 均已落地，且含任务集加载/批量「执行→评估→汇总」独立大块；本事务已含 Evaluator（复杂度最高）+ ExperienceExtractor 两个连贯模块，再加 Benchmark 会超出一事务的聚焦边界。

**不做**：`Benchmark`/`SkillEvolver`/`Validator`/`EvolutionLoop`/`cli.py`/`tools.py`、`objective_check` 的 `test_script` 类型（需代码执行沙箱，延后）、真实 LLM 请求（judge 全程 mock）。

## 5. 拟议变更

| 文件 | 变更 |
|---|---|
| `evoagent/llm.py` | 追加 `chat_json(prompt) -> dict`（§5.1） |
| `evoagent/eval/evaluator.py` | 新建 `Evaluator`（§5.2） |
| `evoagent/eval/experience.py` | 新建 `ExperienceExtractor`（§5.3） |
| `tests/test_llm.py` | 追加 `chat_json` 用例 |
| `tests/test_evaluator.py` | 新建 |
| `tests/test_experience.py` | 新建 |

### 5.1 `chat_json`（`llm.py`，§7 解析兜底）

```python
def chat_json(self, prompt: str) -> dict: ...
```

- 复用 `_get_client()` 调 LLM 取文本 → `json.loads` 解析；失败则提取首个平衡 `{...}` 子串再解析；仍失败抛 `ValueError`。
- 强制 JSON 机制（`response_format={"type":"json_object"}` vs prompt 指令）由优化者定——须兼顾 DeepSeek 兼容（可能不支持 `response_format`）。
- 复用 `complete`/`complete_with_usage` 之一取文本（优化者定）；不改既有两方法的对外行为。

### 5.2 `Evaluator`（`eval/evaluator.py`）

```python
class Evaluator:
    def __init__(self, llm: LLMClient, eval_store: EvalStore): ...
    def evaluate(self, trace: ExecutionTrace, task: Task, *,
                 reference_answer: str = "", rubric: list[str] | None = None,
                 objective_check: dict | None = None) -> EvaluationResult: ...
```

- **客观层**（第一层，零 LLM）：`trace.status ∈ {error,timeout}` → 客观失败（定论）；`objective_check.type` 为 `exact` → `final_output==reference` 定论、`contains` → 半信号；`test_script` 本事务不做（需沙箱）。
- **judge 跳过**（§7 成本边界）：客观定论时跳过 judge；否则 `chat_json` 调 judge（输入 task + final_output + rubric），产出 `rubric_scores`（correctness/completeness/format/follow_skill 0~5）+ `judge_reason`。
- **融合 + passed 三态（评审盯的边界）**，四分支：
  1. 客观定论 → `eval_basis="objective"`，`passed`=客观结果，`total_score`=客观分，judge 跳过；
  2. 半信号 + rubric → `eval_basis="mixed"`，`total=0.7*obj + 0.3*judge`，`passed = total >= PASS_THRESHOLD`；
  3. 无客观 + rubric → `eval_basis="judge_rubric"`，`total=judge`，`passed = total >= PASS_THRESHOLD`；
  4. 无客观 + 无 rubric → `eval_basis="judge_generic"`，`total=judge`（通用 rubric），**`passed=None`（不判对错）**。
- **写库**（§4 步骤 4）：`evaluate` 写 `eval_store.save_eval(result)` 并返回 `result`；`eval_id` 用 uuid，`evaluated_at` 用 UTC ISO。
- **judge 模型**：§7 要求「与执行不同模型」；本事务先用同一 `LLMClient`（`config.LLM_MODEL`），「不同 judge 模型」登记为已知简化（评审可裁定是否加 `LLM_JUDGE_MODEL`）。

### 5.3 `ExperienceExtractor`（`eval/experience.py`）

```python
class ExperienceExtractor:
    def __init__(self, llm: LLMClient): ...
    def extract(self, trace: ExecutionTrace, result: EvaluationResult) -> list[Experience]: ...
```

- 用 `chat_json` 让 LLM 定位「哪里差/好」→ 结构化 `Experience[]`（`category`/`target_section`/`suggestion`/`confidence`，字段见 §8）。
- **纯返回**（不写库）：§3.3/§4 未要求 extractor 落库；`EvalStore.save_experience` 由未来 `EvolutionLoop` 调用。按 `confidence` 过滤低置信度（阈值由优化者定）。
- `experience_id` 用 uuid；`trace_id`/`skill_id` 取自入参。

## 6. 依赖

- 运行时：标准库（`json`/`uuid`/`datetime`/`re`/`typing`）+ 既有 `openai`（经 `llm.py`）。无新第三方。
- 顺序：`llm.py`（chat_json）→ `evaluator.py` → `experience.py` → 测试。
- 既有：`LLMClient`（`0004`/`0005`）、`EvalStore`（`0002`）、`models.py` 各 dataclass（`0001`/`0003`）、`config.py` 融合权重（`0001`）。
- **无 config 变更**。

## 7. 风险

| 风险 | 缓解 |
|---|---|
| **passed 三态边界错**（该 None 时判了 pass，或客观定论时多跑 judge） | §5.2 四分支逐条落地 + 测试覆盖四种 `eval_basis`；评审重点核对 |
| **客观定论判定含糊**（exact 空 reference、contains 半信号） | 优化者钉死：`objective_check` 缺 type/value 时视为「无客观」；exact 才定论、contains 半信号 |
| **chat_json 解析兜底脆弱**（非 JSON / 裸 JSON 前缀） | 单测覆盖：纯 JSON、带前后缀的 JSON、非 JSON（抛错） |
| **judge 模型 ≠ 执行模型未落实**（§7 自偏好偏差） | 登记已知简化；优化者裁定是否引入 `LLM_JUDGE_MODEL` |
| **`test_script` 客观类型**（代码执行/沙箱） | 明确延后，`evaluate` 对未知 type 视为「无客观」而非崩溃 |
| 范围蔓延（Benchmark/演化带进） | §4 非目标逐条列出 |

## 8. 实施顺序

1. `llm.py` 加 `chat_json` + `test_llm.py` 追加用例。
2. `evaluator.py`（`Evaluator`）+ `test_evaluator.py`。
3. `experience.py`（`ExperienceExtractor`）+ `test_experience.py`。
4. 全量验证（§10）。

## 9. 验收标准

1. `chat_json` 存在，`complete`/`complete_with_usage` 行为不变（既有 `test_llm.py` 无回归）。
2. `Evaluator` 只调 `llm`/`eval_store`（grep 无 `import sqlite3`/`Storage`）。
3. **四分支 eval_basis 正确**（客观定论 / mixed / judge_rubric / judge_generic），`passed` 三态：定论判 `True/False`、mixed/judge_rubric 按 `>=PASS_THRESHOLD`、judge_generic 恒 `None`。
4. **跳过 judge**：客观定论时不调 judge（测试断言 judge 未被调用）；半信号/无客观 + rubric 时调 judge。
5. `evaluate` 写库：`EvalStore.get_eval(eval_id)` 回读 `objective`/`rubric_scores`/`passed`/`total_score` 一致。
6. `ExperienceExtractor.extract` 返回 `list[Experience]`，`category`/`target_section` 合法、`confidence` 过滤生效、`trace_id`/`skill_id` 取自入参。
7. 测试全绿（`test_llm`/`test_evaluator`/`test_experience` + 全量无回归），全程 mock、judge 不发真实请求。
8. 无越界：不含 Benchmark/演化/`test_script`/真实请求。

## 10. 验证策略

```
python -m pytest tests/test_llm.py tests/test_evaluator.py tests/test_experience.py -v
python -m pytest -v        # 全量回归
```

- `test_evaluator.py`（mock judge + `tmp_path` `EvalStore`）：四分支各一用例（覆盖 passed 三态）、judge 跳过断言（fake judge 记录调用次数）、`evaluate` 写库回读、`exact`/`contains`/未知 type 边界。
- `test_experience.py`（mock `LLMClient.chat_json`）：返回结构化 JSON → `Experience[]`；低 `confidence` 被过滤；非 JSON → 行为确定。
- 人工复核：`grep -rn "import sqlite3" evoagent/` 仅 `storage.py`；`evaluator.py`/`experience.py` 不出现。
