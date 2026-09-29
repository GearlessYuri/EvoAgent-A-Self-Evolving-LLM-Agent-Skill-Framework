# 事务 0006 最终任务规格说明（Task）

> 优化者（Optimizer）产出。本文件是编码者实现的**唯一依据**，自包含：编码者无需阅读 `plan.md` / `review.md` 即可执行。
> 依据：`plan.md` + `review.md` + `docs/system_design.md` + 事务 `0001`–`0005` 落地后的实仓源码 + 实仓核实。
>
> 说明：本仓库事务文件实际位于 `.agents/transactions/0006/`（顶层 `transactions/` 不存在）。下文路径均以 `.agents/transactions/0006/` 为准。

---

## 1. 目标（Objective）

落地评估层核心（§7「梯度来源」），闭合正向流的「评估」环节：

- `evoagent/llm.py`：新增 `chat_json()`（judge 用，含解析兜底），复用 `0004` 预留的扩展点
- `evoagent/eval/evaluator.py`：`Evaluator`（客观信号 + LLM-as-judge + 融合 + `passed` 三态）
- `evoagent/eval/experience.py`：`ExperienceExtractor`（Trace + Result → `Experience[]`）
- 测试：`tests/test_llm.py`（追加）、`tests/test_evaluator.py`、`tests/test_experience.py`

成果须通过 `pytest` 验证，judge/LLM 全程 mock、不发真实请求；除收尾提交外不做任何 git 操作。

## 2. 上下文（Context）

- 事务 `0001`–`0005` 已落地：底座（含 `llm.py`）、门面、检索器、执行器。全量 75 项测试通过，git `main`@`82963ac`。
- **实仓现状（已核实）**：
  - `evoagent/llm.py`：`complete`（复用 `complete_with_usage`）+ `complete_with_usage` 已就绪，**无 `chat_json`**；模块 docstring 第 3 行写「不实现 anthropic、多 provider 适配层、chat_json、tool calling」（本事务后失准，须更新）。
  - `evoagent/eval/store.py`（`0002`）：`EvalStore.save_eval/get_eval/list_evals/save_experience/list_experiences` 已就绪；`passed` 三态转换（`True→1`/`False→0`/`None→NULL`）与 JSON 反序列化已实现。
  - `evoagent/models.py`：`EvaluationResult`（`eval_id`/`trace_id`/`eval_basis`/`passed`/`total_score`/`objective`/`judge_score`/`rubric_scores`/`judge_reason`/`evaluated_at`，**全必填**）；`Experience`（`experience_id`/`trace_id`/`skill_id`/`category`/**`summary`**/`target_section`/`suggestion`/`confidence`，**全必填，含 `summary`**）。
  - `evoagent/config.py`：已有 `OBJECTIVE_WEIGHT=0.7`/`JUDGE_WEIGHT=0.3`/`PASS_THRESHOLD=0.6`——融合权重与阈值**无需新增**；**无** `LLM_JUDGE_MODEL`、**无** confidence 阈值。
  - `evoagent/eval/` 下**无** `evaluator.py`/`experience.py`/`benchmark.py`。
- **设计分层（§2）**：`evaluator.py`/`experience.py` 属评估层；`Evaluator` 只调 `llm`/`eval_store`，`ExperienceExtractor` 只调 `llm`；均不 `import sqlite3`、不 `import Storage`。
- **环境**：Python 3.13.9（≥3.10）、pytest 8.4.2。

## 3. 范围（Scope）

**做（In scope）**

1. `evoagent/llm.py`：新增 `chat_json()` + `_parse_json_object()` 解析兜底；更新 docstring（§4.1）。
2. `evoagent/eval/evaluator.py`：`Evaluator`（§4.2）。
3. `evoagent/eval/experience.py`：`ExperienceExtractor`（§4.3）。
4. `tests/test_llm.py`（追加）、`tests/test_evaluator.py`、`tests/test_experience.py`（§4.4）。

**不做（Out of scope，明确非目标）** —— 详见 §11。

## 4. 需求（Requirements）

### 4.1 `evoagent/llm.py` —— 追加 `chat_json()` + 解析兜底 + docstring 更新

在 `llm.py` 顶部 `import os`、`import time` 之后追加 `import json`；新增模块级 helper 与 `LLMClient` 方法：

```python
def _parse_json_object(text: str) -> dict:
    """把 LLM 输出解析为 dict：先整体 `json.loads`，失败则提取首个平衡 `{...}` 再解析，仍失败抛 ValueError。"""
    def _try(s: str):
        try:
            obj = json.loads(s)
            return obj if isinstance(obj, dict) else None
        except (json.JSONDecodeError, ValueError):
            return None

    obj = _try(text)
    if obj is not None:
        return obj

    start = text.find("{")
    if start == -1:
        raise ValueError(f"LLM 输出无法解析为 JSON 对象: {text[:200]!r}")
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                obj = _try(text[start : i + 1])
                if obj is not None:
                    return obj
                break
    raise ValueError(f"LLM 输出无法解析为 JSON 对象: {text[:200]!r}")
```

`LLMClient` 内新增：

```python
def chat_json(self, prompt: str) -> dict:
    """judge 用：取文本 → 解析为 dict（§7 解析兜底）。"""
    text = self.complete(prompt + "\n\n请只输出一个 JSON 对象，不要输出任何其它内容。")
    return _parse_json_object(text)
```

**语义钉死（裁定）**：

- **强制 JSON 机制（§4.2 裁定）**：用 **prompt 指令**（在 prompt 末尾追加「请只输出一个 JSON 对象…」），**不**用 `response_format={"type":"json_object"}`——兼顾 DeepSeek 等 OpenAI 兼容 provider（可能不支持 `response_format`）。
- **解析兜底**：先整体 `json.loads`；失败则提取首个平衡 `{...}` 子串（按花括号计数）再解析；仍失败（含整体成功但非 dict、或无 `{`）→ 抛 `ValueError`。
- **复用 `complete()` 取文本**（judge 无需 usage），不改 `complete`/`complete_with_usage` 对外行为。
- **docstring 更新（§2.2 裁定）**：将 `llm.py` 第 3 行「不实现 anthropic、多 provider 适配层、chat_json、tool calling」改为「不实现 anthropic、多 provider 适配层、tool calling」（**仅删去 `chat_json`**，其余保留）。

### 4.2 `Evaluator`（`evoagent/eval/evaluator.py`）

**为什么存在**：把一次执行变成可比较的「分数 + 结论」，给演化提供梯度（§7）。

**精确实现**：

```python
"""评估器：客观信号 + LLM-as-judge 融合 + passed 三态（§7）。

只调 `llm` / `eval_store`；不 import sqlite3 / Storage。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from .. import config
from ..llm import LLMClient
from ..models import EvaluationResult, ExecutionTrace, Task
from .store import EvalStore

GENERIC_RUBRIC = ["correctness", "completeness", "format", "follow_skill"]  # §7 通用 rubric


def _judge_prompt(task_text: str, final_output: str, rubric_dims: list[str], reference_answer: str) -> str:
    dims = "、".join(rubric_dims)
    ref = f"\n参考答案：{reference_answer}" if reference_answer else ""
    return (
        f"任务：{task_text}\n"
        f"执行输出：{final_output}\n"
        f"评分维度：{dims}{ref}\n"
        f"请对每个维度打 0~5 分，并以 JSON 输出 {{'rubric_scores': {{维度: 分数}}, 'reason': '理由'}}。"
    )


class Evaluator:
    def __init__(self, llm: LLMClient, eval_store: EvalStore):
        self.llm = llm
        self.eval_store = eval_store

    def _judge(self, task_text, final_output, rubric_dims, reference_answer) -> tuple[float, dict, str]:
        data = self.llm.chat_json(_judge_prompt(task_text, final_output, rubric_dims, reference_answer))
        raw = data.get("rubric_scores") or {}
        numeric = {k: v for k, v in raw.items() if isinstance(v, (int, float))}
        judge_score = (sum(numeric.values()) / len(numeric)) / 5.0 if numeric else 0.0
        return judge_score, numeric, str(data.get("reason", ""))

    def evaluate(
        self,
        trace: ExecutionTrace,
        task: Task,
        *,
        reference_answer: str = "",
        rubric: list[str] | None = None,
        objective_check: dict | None = None,
    ) -> EvaluationResult:
        status = trace.status
        final_output = trace.final_output

        def _result(eval_basis, passed, total_score, objective, judge_score, rubric_scores, judge_reason):
            r = EvaluationResult(
                eval_id=uuid.uuid4().hex,
                trace_id=trace.trace_id,
                eval_basis=eval_basis,
                passed=passed,
                total_score=total_score,
                objective=objective,
                judge_score=judge_score,
                rubric_scores=rubric_scores,
                judge_reason=judge_reason,
                evaluated_at=datetime.now(timezone.utc).isoformat(),
            )
            self.eval_store.save_eval(r)
            return r

        # 分支 1：执行状态 error/timeout → 客观失败定论（跳过 judge）
        if status in ("error", "timeout"):
            return _result("objective", False, 0.0, {"status": status}, 0.0, {}, "")

        otype = objective_check.get("type") if objective_check else None
        if otype not in ("exact", "contains"):
            otype = None  # 未知 type（含 test_script）视为「无客观」，延后到 0007

        # 分支 2：exact → 客观定论（跳过 judge）
        if otype == "exact":
            matched = final_output == objective_check.get("value")
            return _result(
                "objective", matched, 1.0 if matched else 0.0,
                {"status": status, "type": "exact", "matched": matched}, 0.0, {}, "",
            )

        # 分支 3：contains 半信号 + rubric → mixed（0.7*obj + 0.3*judge）
        if otype == "contains" and rubric:
            matched = objective_check.get("value") in final_output
            obj_score = 1.0 if matched else 0.0
            judge_score, rubric_scores, reason = self._judge(task.task, final_output, rubric, reference_answer)
            total = config.OBJECTIVE_WEIGHT * obj_score + config.JUDGE_WEIGHT * judge_score
            return _result(
                "mixed", total >= config.PASS_THRESHOLD, total,
                {"status": status, "type": "contains", "matched": matched},
                judge_score, rubric_scores, reason,
            )

        # 分支 4：contains 半信号 + 无 rubric → 归入 judge_generic（passed=None）
        if otype == "contains" and not rubric:
            matched = objective_check.get("value") in final_output
            judge_score, rubric_scores, reason = self._judge(task.task, final_output, GENERIC_RUBRIC, reference_answer)
            return _result(
                "judge_generic", None, judge_score,
                {"status": status, "type": "contains", "matched": matched},
                judge_score, rubric_scores, reason,
            )

        # 分支 5：无客观 + rubric → judge_rubric
        if rubric:
            judge_score, rubric_scores, reason = self._judge(task.task, final_output, rubric, reference_answer)
            return _result(
                "judge_rubric", judge_score >= config.PASS_THRESHOLD, judge_score,
                {"status": status}, judge_score, rubric_scores, reason,
            )

        # 分支 6：无客观 + 无 rubric → judge_generic（passed=None）
        judge_score, rubric_scores, reason = self._judge(task.task, final_output, GENERIC_RUBRIC, reference_answer)
        return _result(
            "judge_generic", None, judge_score,
            {"status": status}, judge_score, rubric_scores, reason,
        )
```

**语义钉死（裁定，对应评审 §3.1–§3.5）**：

- **`objective_score` 映射**：`exact` → `matched = (final_output == objective_check["value"])`；`contains` → `matched = (objective_check["value"] in final_output)`；`objective_score = 1.0 if matched else 0.0`（二元 0/1）。
- **比较目标（§3.3）**：客观规则比较用 **`objective_check["value"]`**；`reference_answer` **不参与客观规则**，仅供 `_judge_prompt` 作上下文（非空时写入 prompt）。
- **`judge_score` 归一**：judge 输出 `rubric_scores`（各维度 0~5）；`judge_score = (sum/len)/5.0`（0~1）；`rubric_scores` 无数值维度 → `judge_score = 0.0`。`rubric_scores` 存 judge 返回的 0~5 数值 dict。
- **六分支 `eval_basis` + `passed` 三态**（见代码注释）：分支 1/2 → `objective`（`passed` 定论 `False`/`True`，跳过 judge）；分支 3 → `mixed`（`passed = total >= PASS_THRESHOLD`）；分支 5 → `judge_rubric`（同上）；分支 4/6 → `judge_generic`（**`passed=None`**）。
- **`objective` dict 口径（§3.4）**：分支 1 填 `{"status"}`；exact/contains 填 `{"status", "type", "matched"}`；judge_rubric/judge_generic（无客观）填 `{"status"}`。
- **跳过 judge 记 0**：分支 1/2 `judge_score=0.0`、`rubric_scores={}`、`judge_reason=""`。
- **客观失败 `total_score=0.0`**（分支 1）。
- **`test_script`（§3.5）**：`type` 不在 `{"exact","contains"}`（含 `test_script`）→ `otype=None` 视作「无客观」，走 judge 分支；登记为已知延后（`0007` Benchmark 事务补客观执行）。
- **写库 + 返回**：`evaluate` 先 `eval_store.save_eval(result)` 再返回 `result`；`eval_id=uuid4().hex`、`evaluated_at=datetime.now(timezone.utc).isoformat()`。
- **judge 模型（§4.1 裁定）**：**接受同模型简化**——judge 与执行共用 `config.LLM_MODEL`；登记为已知局限（§11.9）。本事务**不引入** `LLM_JUDGE_MODEL`（保持「无 config 变更」）。

### 4.3 `ExperienceExtractor`（`evoagent/eval/experience.py`）

**为什么存在**：把「这次为什么差/好」提炼成结构化改进点，供 Evolver 使用（§3.3/§8）。

**精确实现**：

```python
"""经验提炼：Trace + EvaluationResult → Experience[]（§8）。

只调 `llm`（chat_json）；纯返回不写库，落库由未来 EvolutionLoop 调 EvalStore.save_experience。
"""

from __future__ import annotations

import uuid

from ..llm import LLMClient
from ..models import EvaluationResult, ExecutionTrace, Experience

CATEGORIES = {
    "missing_step", "wrong_instruction", "bad_example",
    "tool_misuse", "hallucination", "good_pattern", "failed_evolution",
}
TARGET_SECTIONS = {"prompt_template", "few_shots", "tools"}
_MIN_CONFIDENCE = 0.5  # 低置信度过滤阈值（extractor 内部阈值，非全局 config）


def _extract_prompt(trace: ExecutionTrace, result: EvaluationResult) -> str:
    return (
        f"技能：{trace.skill_id}\n"
        f"任务状态：{trace.status}\n"
        f"最终输出：{trace.final_output}\n"
        f"评估：total_score={result.total_score}, passed={result.passed}, reason={result.judge_reason}\n"
        f"请提炼改进经验，输出 {{\"experiences\": [{{\"category\", \"target_section\", "
        f"\"summary\", \"suggestion\", \"confidence\"}}]}}"
    )


class ExperienceExtractor:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    def extract(self, trace: ExecutionTrace, result: EvaluationResult) -> list[Experience]:
        data = self.llm.chat_json(_extract_prompt(trace, result))
        raw_items = data.get("experiences", [])
        if not isinstance(raw_items, list):
            raw_items = []

        out: list[Experience] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            category = item.get("category")
            target_section = item.get("target_section")
            summary = str(item.get("summary", "")).strip()
            if category not in CATEGORIES or target_section not in TARGET_SECTIONS:
                continue  # 非法枚举：丢弃该条（§4.4 裁定）
            if not summary:
                continue  # summary 必填，空则丢弃（§2.1）
            try:
                confidence = float(item.get("confidence", 0.0))
            except (TypeError, ValueError):
                confidence = 0.0
            confidence = max(0.0, min(1.0, confidence))
            if confidence < _MIN_CONFIDENCE:
                continue  # 低置信度过滤（§9）
            out.append(Experience(
                experience_id=uuid.uuid4().hex,
                trace_id=trace.trace_id,
                skill_id=trace.skill_id,
                category=category,
                summary=summary,
                target_section=target_section,
                suggestion=str(item.get("suggestion", "")),
                confidence=confidence,
            ))
        return out
```

**语义钉死（裁定）**：

- **返回 `list[Experience]`，纯返回不写库**（§3.3/§4 未要求 extractor 落库；`EvalStore.save_experience` 由未来 `EvolutionLoop` 调用）。
- **`Experience` 全字段产出（§2.1）**：含 `summary`（必填）；`experience_id=uuid4().hex`；`trace_id`/`skill_id` 取自入参 `trace`。
- **字段校验（§4.4 裁定）**：`category` 不在 `CATEGORIES`、或 `target_section` 不在 `TARGET_SECTIONS`、或 `summary` 为空 → **丢弃该条**（不产出非法 `Experience`，避免污染下游 Evolver）。`suggestion` 缺失 → `""`。
- **confidence**：`float(...)` 转换失败记 `0.0`；`clamp` 到 `[0,1]`；`< _MIN_CONFIDENCE`（0.5）→ 丢弃。
- **`_MIN_CONFIDENCE` 落点（§4.3 裁定）**：硬编码在 `experience.py` 为模块常量 `0.5`（**不进 `config.py`**，保持「无 config 变更」）；若日后需调参，再提升为 config。
- **分层**：只调 `llm`，不 `import sqlite3`、不 `import Storage`、不写库。

### 4.4 测试要求

- `tests/test_llm.py`（追加）、`tests/test_evaluator.py`、`tests/test_experience.py`：见 §10，全程 mock、judge 不发真实请求。

## 5. 约束（Constraints）

1. **语言 / 运行时**：Python 3.10+（本机 3.13.9）；类型注解统一 `X | None`。
2. **运行时依赖**：标准库（`json`/`uuid`/`datetime`/`re`/`typing`）；不新增第三方（`openai` 仍经 `llm.py` 惰性 import）。
3. **分层**：`evaluator.py` 只调 `llm`/`eval_store`；`experience.py` 只调 `llm`；`storage.py` 仍是全项目唯一 `import sqlite3`/写 SQL 处。
4. **不改既有**：`complete`/`complete_with_usage` 对外行为不变（既有 `test_llm.py` 无回归）；不改 `models.py`/`storage.py`/`store.py`/`trace.py`/`executor.py`/`retriever.py`/`registry.py`/**`config.py`（无 config 变更）**。
5. **不越界**：不实现 `Benchmark`/`SkillEvolver`/`Validator`/`EvolutionLoop`/`cli.py`/`tools.py`、`test_script` 客观类型、真实 LLM 请求。
6. **命名**：类 `PascalCase`、方法/函数 `snake_case`、常量 `UPPER_SNAKE_CASE`；枚举集合 `CATEGORIES`/`TARGET_SECTIONS`、`GENERIC_RUBRIC` 为模块级常量。
7. **错误处理**：仅 `_parse_json_object` 抛 `ValueError`；judge 输出解析失败由其抛出，`evaluate`/`extract` 不额外吞异常；不自定义异常类。

## 6. 相关文件 / 模块（Relevant Files / Modules）

**本事务新建：**

| 文件 | 内容 |
|---|---|
| `evoagent/eval/evaluator.py` | `Evaluator` + `_judge_prompt` + `GENERIC_RUBRIC`（§4.2） |
| `evoagent/eval/experience.py` | `ExperienceExtractor` + `_extract_prompt` + `CATEGORIES`/`TARGET_SECTIONS`/`_MIN_CONFIDENCE`（§4.3） |
| `tests/test_evaluator.py` | §4.4/§10 |
| `tests/test_experience.py` | §4.4/§10 |

**本事务修改：**

| 文件 | 变更 |
|---|---|
| `evoagent/llm.py` | 追加 `chat_json()` + `_parse_json_object()` + `import json`；docstring 删去 `chat_json`（§4.1） |
| `tests/test_llm.py` | 追加 `chat_json` 用例（§4.4/§10） |

**只读参照（不修改）：** `evoagent/models.py`、`evoagent/storage.py`、`evoagent/eval/store.py`、`evoagent/execution/trace.py`、`evoagent/execution/executor.py`、`evoagent/skills/*`、`evoagent/config.py`、`docs/system_design.md`、`.agents/transactions/0001/`–`0006/` 的历史产物（`plan.md`/`review.md` 等不可改）。

## 7. 推荐的实现策略（Recommended Implementation Strategy）

依赖关系：`llm.py`（`chat_json` + 解析兜底）→ `tests/test_llm.py`（追加）→ `evaluator.py` → `experience.py` → `test_evaluator.py`/`test_experience.py` → 验证 → 收尾提交。

1. **`llm.py`**：加 `import json` + `_parse_json_object` + `chat_json`；更新 docstring。
2. **`tests/test_llm.py`**：追加 `chat_json` 用例（纯 JSON / 带前后缀 JSON / 非 JSON 抛 `ValueError`），确认既有 8 用例无回归。
3. **`evaluator.py`**：按 §4.2 精确实现 `GENERIC_RUBRIC`/`_judge_prompt`/`Evaluator`（六分支）。
4. **`experience.py`**：按 §4.3 精确实现 `CATEGORIES`/`TARGET_SECTIONS`/`_extract_prompt`/`ExperienceExtractor`。
5. **`test_evaluator.py`/`test_experience.py`**：按 §10 写。
6. **验证**：运行 §10 命令，确认全绿。
7. **收尾提交**：按 §10 末尾执行。

## 8. 预期变更（Expected Changes）

| 文件 | 变更性质 |
|---|---|
| `evoagent/llm.py` | 修改：追加 `chat_json`/`_parse_json_object` + `import json`；docstring 删去 `chat_json` |
| `evoagent/eval/evaluator.py` | 新建 |
| `evoagent/eval/experience.py` | 新建 |
| `tests/test_llm.py` | 修改：追加 `chat_json` 用例 |
| `tests/test_evaluator.py` | 新建 |
| `tests/test_experience.py` | 新建 |

（不修改 `models.py`、`storage.py`、`store.py`、`trace.py`、`executor.py`、`retriever.py`、`registry.py`、`config.py`、`__init__.py`、`pyproject.toml`、`requirements.txt`、`docs/system_design.md`；不产生运行时数据文件。）

## 9. 验收标准（Acceptance Criteria）

1. **`chat_json`**：存在且 `chat_json(prompt) -> dict`；纯 JSON、带前后缀 JSON 均解析成功，非 JSON（无 `{` 或不可解析）抛 `ValueError`；`complete`/`complete_with_usage` 行为不变（既有 `test_llm.py` 无回归）；`llm.py` docstring 已删去 `chat_json`。
2. **分层**：`Evaluator` 只调 `llm`/`eval_store`，`ExperienceExtractor` 只调 `llm`（grep 无 `import sqlite3`/`Storage`）。
3. **六分支 `eval_basis` + `passed` 三态**：`objective`（定论 True/False）、`mixed`/`judge_rubric`（`>= PASS_THRESHOLD`）、`judge_generic`（**恒 `None`**）；含 `contains`+无 rubric → `judge_generic`+`passed=None` 的分支。
4. **跳过 judge**：`objective` 定论（error/timeout、exact）时不调 judge（fake judge 记录调用次数为 0）；mixed/judge_rubric/judge_generic 时调 judge。
5. **`objective_score`**：exact/contains 命中 `1.0`、未命中 `0.0`；比较用 `objective_check["value"]`。
6. **写库回读**：`evaluate` 写库后 `EvalStore.get_eval(eval_id)` 回读 `objective`/`rubric_scores`/`passed`/`total_score`/`eval_basis` 一致。
7. **`ExperienceExtractor`**：返回 `list[Experience]`；`category`/`target_section` 合法、`summary` 非空、`confidence` 过滤（`<0.5` 丢弃）、非法枚举/空 summary 丢弃、`trace_id`/`skill_id` 取自入参。
8. **测试**：`test_evaluator.py`/`test_experience.py` + 追加后的 `test_llm.py` 全绿，全量 `python -m pytest` 无回归；全程 mock、judge 不发真实请求。
9. **无越界**：不含 `Benchmark`/演化层/`test_script` 客观执行/真实 LLM 请求。

## 10. 验证策略（Verification Strategy）

在项目根目录运行：

```
python -m pytest tests/test_llm.py tests/test_evaluator.py tests/test_experience.py -v
```

并确认全量回归：

```
python -m pytest -v
```

**用例要求：**

- `tests/test_llm.py`（追加）：`chat_json` 纯 JSON → dict；带前后缀（如 ``"前言 {...} 后语"``）→ 解析出 dict；非 JSON（无 `{`）→ `ValueError`；注入路径 `chat_json` 复用 `complete`（不 import openai、不发真实请求）。
- `tests/test_evaluator.py`（mock judge + `tmp_path` `EvalStore`）：
  - 六分支各一用例：`status="error"`（objective/False/0.0）、`exact` 命中与未命中（objective/True 或 False）、`contains`+rubric（mixed）、`contains`+无 rubric（judge_generic/None）、无客观+rubric（judge_rubric）、无客观+无 rubric（judge_generic/None）。
  - judge 跳过断言：`objective` 分支 fake judge（`chat_json`）未被调用。
  - 写库回读：`EvalStore.get_eval(eval_id)` 字段一致。
  - `objective_check` 未知 type（如 `test_script`）→ 视作无客观（走 judge 分支、不崩溃）。
- `tests/test_experience.py`（mock `LLMClient.chat_json`）：返回结构化 `{"experiences":[...]}` → `Experience[]`；低 `confidence` 被过滤；非法 `category`/`target_section` 或空 `summary` 被丢弃；非 JSON → 行为确定（`ValueError` 上抛）。

**额外人工复核（非 pytest，编码者确认并记入 `execution.md`）：**

```
grep -rn "import sqlite3" evoagent/
```

真实 `import sqlite3` 语句**只**应出现在 `evoagent/storage.py`；`evaluator.py`/`experience.py` 不得出现、也不得访问 `storage.conn`。

**收尾提交（用户已授权，必须执行）**：

全部验证通过后，Coder **一次性提交全部变更**：

```
git add -A && git commit -m "0006: 落地评估层 Evaluator 与 ExperienceExtractor"
```

- 提交信息**首行**必须以 `0006: ` 开头 + 一句目标概括（上例为建议措辞，可用同义简洁一句话）。
- **不 push、不 amend、不建分支、不 force-push**（仅本地提交）。
- **把提交哈希记入 `result.md`**（`git rev-parse HEAD` 取哈希）。

## 11. 明确的非目标（Explicit Non-Goals）

本任务**不做**以下任何事（防止范围蔓延）：

1. **`Benchmark`**（任务集 + 运行器 + 汇总）——**顺延至 `0007`**（它是 `Validator` 的「尺子」，含任务集加载/批量「执行→评估→汇总」独立大块）。
2. **`SkillEvolver`/`Validator`/`EvolutionLoop`/`cli.py`/`tools.py`**（演化/编排层）。
3. **`objective_check` 的 `test_script` 类型**（需代码执行沙箱）——`evaluate` 对未知 type 视作「无客观」而非崩溃，登记为延后（`0007` 补）。
4. **真实 LLM 调用 / 网络请求**（judge/LLM 全程 mock）。
5. **`LLM_JUDGE_MODEL` / judge 模型分离**：本事务接受「judge 与执行同模型」（§4.1），登记为已知局限；不引入 config 变更。
6. **`chat_json` 的 `response_format` 强制 JSON**：只用 prompt 指令 + 解析兜底（DeepSeek 兼容）。
7. **修改 `docs/system_design.md`**（只读）。
8. **除收尾提交（§10）外的任何 git 操作**：不 push、不 amend、不建分支、不 force-push、不拆多次提交。

---

### 已确认的决策（记录以备查；无「实现前需确认」的阻塞项）

| 裁定点 | 结论 |
|---|---|
| judge 模型分离（§4.1） | **接受同模型简化**：judge 与执行共用 `config.LLM_MODEL`，登记为已知局限，不引入 `LLM_JUDGE_MODEL`（保持无 config 变更） |
| `chat_json` 强制 JSON 机制（§4.2） | **prompt 指令 + 解析兜底**（先整体 `json.loads`，失败提取首个平衡 `{...}`，仍失败抛 `ValueError`），不用 `response_format` |
| `objective_score` 映射（§3.1） | exact/contains 均二元 `1.0`/`0.0`（`==` / `in`），比较用 `objective_check["value"]` |
| `contains` + 无 rubric（§3.2） | 归入 **`judge_generic` + `passed=None`**（半信号不足判对错，安全不误判）；`matched` 仍记录在 `objective` dict |
| `objective`/`judge_score` 填充（§3.4） | `objective` 各分支含 `status`（exact/contains 加 `type`+`matched`）；跳过 judge 记 `judge_score=0.0`/`rubric_scores={}`/`judge_reason=""`；客观失败 `total_score=0.0` |
| `judge_score` 归一 | `(sum(rubric_scores.values())/len)/5.0`（0~5 → 0~1）；无数值维度记 `0.0` |
| confidence 阈值（§4.3） | `_MIN_CONFIDENCE = 0.5` 硬编码在 `experience.py`（不进 config，无 config 变更） |
| 枚举校验（§4.4） | `category`/`target_section` 非法或 `summary` 空 → **丢弃该条**；confidence 非数值记 0、clamp [0,1] |
| `test_script`（§3.5） | 未知 type 视作「无客观」走 judge，登记延后到 `0007` |
| `Experience.summary`（§2.1） | 必填，extractor 产出，空则丢弃 |
| `llm.py` docstring（§2.2） | 删去「chat_json」，保留「anthropic/多 provider/tool calling」 |
