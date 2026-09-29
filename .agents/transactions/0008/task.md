# 事务 0008 最终任务规格说明（Task）

> 优化者（Optimizer）产出。本文件是编码者实现的**唯一依据**，自包含：编码者无需阅读 `plan.md` / `review.md` 即可执行。
> 依据：`plan.md` + `review.md` + `docs/system_design.md` + 事务 `0001`–`0007` 落地后的实仓源码 + 实仓核实。
>
> 说明：本仓库事务文件实际位于 `.agents/transactions/0008/`（顶层 `transactions/` 不存在）。下文路径均以 `.agents/transactions/0008/` 为准。

---

## 1. 目标（Objective）

落地演化层核心，串起「经验 → 候选 → 验证 → promote」的逆向流闭环（§9）：

- `evoagent/evolution/evolver.py`：`SkillEvolver`（`Experience[]` → 候选新版本）
- `evoagent/evolution/validator.py`：`Validator`（Benchmark A/B → win_rate 判定 → promote/丢弃/转人工）+ `ValidationResult`
- `evoagent/config.py`：加 `PROMOTE_WIN_RATE_THRESHOLD`、`MIN_REGRESSION_TASKS`
- 测试：`tests/test_evolver.py`、`tests/test_validator.py`

成果须通过 `pytest` 验证，Evolver LLM 与 Validator Benchmark 全程 mock、不发真实 LLM 请求；除收尾提交外不做任何 git 操作。

## 2. 上下文（Context）

- 事务 `0001`–`0007` 已落地：底座、门面、检索器、执行器、评估层（Evaluator/ExperienceExtractor/Benchmark）。全量 104 项测试通过，git `main`@`36bace4`。
- **实仓现状（已核实）**：
  - `evoagent/evolution/` **不存在**（无 `evolver.py`/`validator.py`）。
  - `SkillRegistry`（`0002`）：`register`（尊重 `status`，`""`→active）、`promote`/`rollback` 经 `_set_active`（目标必须已存在否则 `ValueError`；目标置 active、其余 active 转 deprecated；**不校验目标当前态**，故 draft 可直接 promote）、`get_active`/`get`。`register` 持久化 `skill.metrics` 等 11 列。
  - `Benchmark.run(tasks, skill) -> BenchmarkReport(per_task=[(task_id, passed, total_score)], success_rate, avg_total_score)`（`0007`）。
  - `EvalStore.save_experience/list_experiences`（`0002`）已就绪；`Experience` 全字段必填（**含 `trace_id`**）；`Experience.category` 含 `"failed_evolution"`。
  - `Skill` 全字段必填：`skill_id`/`name`/`description`/`version`/`tags`/`prompt_template`/`few_shots`/`tools`/`status`/`parent_version`/`change_log`/`metrics`/`created_at`/`updated_at`。
  - `config.py`：**无** `PROMOTE_WIN_RATE_THRESHOLD`/`MIN_REGRESSION_TASKS`。
- **设计分层（§2）**：`evolver.py`/`validator.py` 属演化层；Evolver 只调 `llm`，Validator 只调 `benchmark`/`registry`/`eval_store`；均不 `import sqlite3`/`Storage`。
- **环境**：Python 3.13.9（≥3.10）、pytest 8.4.2。

## 3. 范围（Scope）

**做（In scope）**

1. `evoagent/config.py`：追加 `PROMOTE_WIN_RATE_THRESHOLD`、`MIN_REGRESSION_TASKS`（§4.1）。
2. `evoagent/evolution/__init__.py`（新建包）。
3. `evoagent/evolution/evolver.py`：`SkillEvolver`（§4.2）。
4. `evoagent/evolution/validator.py`：`Validator` + `ValidationResult`（§4.3）。
5. `tests/test_evolver.py`、`tests/test_validator.py`（§4.4）。

**不做（Out of scope，明确非目标）** —— 详见 §11。

## 4. 需求（Requirements）

### 4.1 `evoagent/config.py` —— 追加两个常量

在既有常量之后追加（**不改动**任何既有常量；值来自设计 §9/§11 既定，**不得改值**）：

```python
# ── 演化 promote（事务 0008 追加） ──────────────────────────────────────────
PROMOTE_WIN_RATE_THRESHOLD = 0.55   # §9/§11 A/B promote 阈值（win_rate 下限，≥ 且 avg 不降才 promote）
MIN_REGRESSION_TASKS = 20           # §9/§11 regression 集最小题数，不足转人工
```

### 4.2 `SkillEvolver`（`evoagent/evolution/evolver.py`）

**为什么存在**：「自演进」核心——把经验变成新版本 Skill（§3.4）。

**精确实现**：

```python
"""技能演化器：Experience[] → 候选新版本（§3.4/§9）。

只调 `llm`（chat_json）；不 import sqlite3 / Storage。
v1 不改 `tools`（工具子集校验依赖 tools.py，未建）；版本恒 patch 递增。
"""

from __future__ import annotations

from datetime import datetime, timezone

from ..llm import LLMClient
from ..models import Experience, FewShot, Skill


def _bump_patch(version: str) -> str:
    """SemVer patch 递增：`x.y.z` → `x.y.(z+1)`；无法解析 → `"0.0.1"`。"""
    parts = version.split(".")
    if len(parts) == 3 and all(p.isdigit() for p in parts):
        major, minor, patch = parts
        return f"{major}.{minor}.{int(patch) + 1}"
    return "0.0.1"


def _evolve_prompt(skill: Skill, experiences: list[Experience]) -> str:
    lines = [
        f"技能：{skill.skill_id} v{skill.version}",
        f"当前 prompt_template：{skill.prompt_template}",
        "经验：",
    ]
    for exp in experiences:
        lines.append(f"- [{exp.target_section}] {exp.summary} → {exp.suggestion}")
    lines.append(
        "请输出 JSON：{\"prompt_template\": 新模板, \"few_shots\": [{\"input\",\"output\"}], \"change_log\": 改动说明}"
    )
    return "\n".join(lines)


class SkillEvolver:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    def evolve(self, skill: Skill, experiences: list[Experience]) -> Skill:
        data = self.llm.chat_json(_evolve_prompt(skill, experiences))

        prompt_template = data.get("prompt_template")
        if not isinstance(prompt_template, str) or not prompt_template.strip():
            prompt_template = skill.prompt_template

        raw_shots = data.get("few_shots")
        if isinstance(raw_shots, list) and all(isinstance(x, dict) for x in raw_shots):
            few_shots = [FewShot.from_dict(x) for x in raw_shots]
        else:
            few_shots = list(skill.few_shots)

        change_log = str(data.get("change_log", "")).strip()
        if not change_log:
            change_log = f"基于 {len(experiences)} 条经验演化"

        now = datetime.now(timezone.utc).isoformat()
        return Skill(
            skill_id=skill.skill_id,
            name=skill.name,
            description=skill.description,
            version=_bump_patch(skill.version),
            tags=list(skill.tags),
            prompt_template=prompt_template,
            few_shots=few_shots,
            tools=list(skill.tools),
            status="draft",
            parent_version=skill.version,
            change_log=change_log,
            metrics={},
            created_at=now,
            updated_at=now,
        )
```

**语义钉死（裁定）**：

- **签名**：`evolve(skill: Skill, experiences: list[Experience]) -> Skill`。**无任何 `reference_answer`/`rubric`/`benchmark` 参数**——参考答案在 Evolver 侧**结构上不可达**（§11 答案隔离）；prompt 仅由 `skill`（id/version/prompt_template）+ `experience`（target_section/summary/suggestion）拼装。
- **输出候选**：`status="draft"`（§4/§9 裁定用 draft，见 §4.5）、`parent_version=skill.version`、`version` 严格递增（patch bump）、`metrics={}`（draft 未验证无得分）、`tools=list(skill.tools)`（**v1 不改 tools**，`target_section=="tools"` 的经验在 prompt 中照传、但工具本身不演化）、`created_at`/`updated_at` 用 `datetime.now(timezone.utc).isoformat()`。
- **LLM 输出 JSON schema（§4.2 裁定）**：`{"prompt_template": str, "few_shots": [{"input","output"}], "change_log": str}`。
  - `prompt_template` 缺失/非 str/空 → 回退旧 `skill.prompt_template`。
  - `few_shots` 缺失/非 list/元素非 dict → 回退旧 `skill.few_shots`（复制）。
  - `change_log` 缺失/空 → 默认 `"基于 N 条经验演化"`（保证**非空**）。
- **版本跳级（§3.2 裁定）**：**代码确定性 patch 递增**（`_bump_patch`），**不**由 LLM 定版本、**不**做 diff→minor/major 判定。理由：patch/minor/major 的「diff 大小量化」是 §10 语义、v1 无消费者，恒 patch 保证「严格递增」可测；minor/major 登记为已知简化（§11.6）。

### 4.3 `Validator`（`evoagent/evolution/validator.py`）

**为什么存在**：演化可能「改坏」，新版本上线前必须过 Benchmark A/B 防回归（§3.4/§9）。

**精确实现**：

```python
"""验证器：Benchmark A/B → win_rate 判定 → promote / 丢弃 / 转人工（§9/§11）。

只调 `benchmark` / `registry` / `eval_store`；不 import sqlite3 / Storage。
"""

from __future__ import annotations

import dataclasses
import uuid

from .. import config
from ..eval.benchmark import Benchmark, BenchmarkTask
from ..eval.store import EvalStore
from ..models import Experience, Skill
from ..skills.registry import SkillRegistry


@dataclasses.dataclass
class ValidationResult:
    promoted: bool
    win_rate: float
    old_avg: float
    new_avg: float
    sample_size: int
    reason: str  # "promoted" | "sample_insufficient" | "insignificant" | "regression"


def _win_rate(old_report, new_report) -> float:
    """逐任务配对：new_score 更高记 1、持平记 0.5、更低记 0，取均值（§11）。"""
    n = len(old_report.per_task)
    if n == 0:
        return 0.0
    wins = 0.0
    for (_, _, old_score), (_, _, new_score) in zip(old_report.per_task, new_report.per_task):
        if new_score > old_score:
            wins += 1.0
        elif new_score == old_score:
            wins += 0.5
    return wins / n


class Validator:
    def __init__(self, benchmark: Benchmark, registry: SkillRegistry, eval_store: EvalStore):
        self.benchmark = benchmark
        self.registry = registry
        self.eval_store = eval_store

    def validate(self, skill_id: str, candidate: Skill, tasks: list[BenchmarkTask]) -> ValidationResult:
        old = self.registry.get_active(skill_id)
        old_report = self.benchmark.run(tasks, old)
        new_report = self.benchmark.run(tasks, candidate)

        win_rate = _win_rate(old_report, new_report)
        old_avg = old_report.avg_total_score
        new_avg = new_report.avg_total_score
        sample_size = len(tasks)

        # 结局 1：样本不足 → 转人工（register 留 draft，不写 failed_evolution）
        if sample_size < config.MIN_REGRESSION_TASKS:
            self.registry.register(candidate)
            return ValidationResult(False, win_rate, old_avg, new_avg, sample_size, "sample_insufficient")

        # 结局 2：通过 → register(draft) + promote，metrics 快照
        if win_rate >= config.PROMOTE_WIN_RATE_THRESHOLD and new_avg >= old_avg:
            candidate.metrics = {
                "benchmark": {
                    "win_rate": win_rate,
                    "success_rate": new_report.success_rate,
                    "avg_total_score": new_avg,
                }
            }
            self.registry.register(candidate)
            self.registry.promote(skill_id, candidate.version)
            return ValidationResult(True, win_rate, old_avg, new_avg, sample_size, "promoted")

        # 结局 3：不显著（0.5 < win_rate < 0.55 且 avg 不降）→ 丢弃 + failed_evolution
        if win_rate > 0.5 and new_avg >= old_avg:
            self._record_failed_evolution(skill_id, win_rate, old_avg, new_avg, "insignificant")
            return ValidationResult(False, win_rate, old_avg, new_avg, sample_size, "insignificant")

        # 结局 4：回归（win_rate ≤ 0.5 或 avg 下降）→ 丢弃 + failed_evolution
        self._record_failed_evolution(skill_id, win_rate, old_avg, new_avg, "regression")
        return ValidationResult(False, win_rate, old_avg, new_avg, sample_size, "regression")

    def _record_failed_evolution(self, skill_id, win_rate, old_avg, new_avg, reason):
        self.eval_store.save_experience(Experience(
            experience_id=uuid.uuid4().hex,
            trace_id="",  # 演化失败无关联 trace（§3.3 裁定）
            skill_id=skill_id,
            category="failed_evolution",
            summary=f"演化验证未通过：win_rate={win_rate:.3f}, old_avg={old_avg:.3f}, new_avg={new_avg:.3f}",
            target_section="",
            suggestion=reason,  # "insignificant" / "regression"
            confidence=1.0,
        ))
```

**语义钉死（裁定）**：

- **签名**：`validate(skill_id: str, candidate: Skill, tasks: list[BenchmarkTask]) -> ValidationResult`；`skill_id` 用于 `registry.get_active`（应等于 `candidate.skill_id`）。
- **A/B 配对**：`old = registry.get_active(skill_id)`；`old_report = benchmark.run(tasks, old)`、`new_report = benchmark.run(tasks, candidate)`——**同一 `tasks` 列表、同顺序**（`Benchmark.run` 确定性），逐任务按 `total_score` 配对（`zip`）。
- **win_rate 口径（§11）**：逐任务 `new_score > old_score` 记 1、`==` 记 0.5、`<` 记 0，取均值。
- **三支结局（§2.1 裁定，拆分样本不足 vs 丢弃）**：
  1. **样本不足**：`sample_size < MIN_REGRESSION_TASKS(20)` → `register(candidate)`（留 **draft** 供人工）、**不写** failed_evolution、`promoted=False, reason="sample_insufficient"`。
  2. **通过**：`win_rate >= 0.55` 且 `new_avg >= old_avg` → 填 metrics 快照 → `register(candidate)`（draft）→ `promote(skill_id, candidate.version)`（draft→active、旧 active→deprecated、历史保留），`promoted=True, reason="promoted"`。
  3. **不显著**：`0.5 < win_rate < 0.55` 且 `new_avg >= old_avg` → **不注册（丢弃）**、写 failed_evolution，`reason="insignificant"`。
  4. **回归**：`win_rate <= 0.5` 或 `new_avg < old_avg` → **不注册（丢弃）**、写 failed_evolution，`reason="regression"`。
- **`reason` 取值集合（§3.4 裁定）**：`"promoted"` / `"sample_insufficient"` / `"insignificant"` / `"regression"`。
- **`metrics` 快照（§2.2 裁定）**：仅在**通过**分支（promote 前）填 `candidate.metrics = {"benchmark": {"win_rate", "success_rate", "avg_total_score"}}`，满足 §3.1「benchmark 得分作为快照随版本记录」；样本不足/丢弃分支不填。
- **promote 走状态机（不绕过）**：`register`（draft）+ `promote`（经 `_set_active`）→ 单 active、旧版 deprecated、不可变历史（§10）。
- **failed_evolution 字段映射（§3.3 裁定）**：`trace_id=""`（演化失败无关联 trace）、`target_section=""`、`suggestion=reason`、`confidence=1.0`、`summary` 含 `win_rate`/`old_avg`/`new_avg`。
- **`ValidationResult`（§4.1 裁定）**：`validator.py` 内 `@dataclasses.dataclass`（**不进 `models.py`**），字段 `promoted: bool`/`win_rate: float`/`old_avg: float`/`new_avg: float`/`sample_size: int`/`reason: str`。

### 4.4 测试要求

- `tests/test_evolver.py`、`tests/test_validator.py`：见 §10，全程 mock。

## 5. 约束（Constraints）

1. **语言 / 运行时**：Python 3.10+（本机 3.13.9）；类型注解统一 `X | None`。
2. **运行时依赖**：标准库（`uuid`/`dataclasses`/`datetime`/`typing`）；不新增第三方。
3. **分层**：`evolver.py` 只调 `llm`；`validator.py` 只调 `benchmark`/`registry`/`eval_store`；`storage.py` 仍是全项目唯一 `import sqlite3`/写 SQL 处。
4. **不改既有**：不改 `models.py`/`storage.py`/`store.py`/`registry.py`/`benchmark.py`/`evaluator.py`/`experience.py`/`executor.py`/`retriever.py`/`llm.py`；`config.py` 仅追加两常量（阈值值**不得改**）。
5. **不越界**：不实现 `EvolutionLoop`/`cli.py`/`tools.py`、工具演化、真实 LLM 请求、report 文件 I/O。
6. **命名**：类 `PascalCase`、方法/函数 `snake_case`、常量 `UPPER_SNAKE_CASE`；`_bump_patch`/`_evolve_prompt`/`_win_rate`/`_record_failed_evolution` 为模块级私有函数。
7. **错误处理**：`promote` 目标不存在时 `ValueError` 由 `registry` 上抛（Validator 不吞）；不自定义异常类。

## 6. 相关文件 / 模块（Relevant Files / Modules）

**本事务新建：**

| 文件 | 内容 |
|---|---|
| `evoagent/evolution/__init__.py` | 空包（docstring） |
| `evoagent/evolution/evolver.py` | `SkillEvolver` + `_bump_patch`/`_evolve_prompt`（§4.2） |
| `evoagent/evolution/validator.py` | `Validator` + `ValidationResult` + `_win_rate`（§4.3） |
| `tests/test_evolver.py` | §4.4/§10 |
| `tests/test_validator.py` | §4.4/§10 |

**本事务修改：**

| 文件 | 变更 |
|---|---|
| `evoagent/config.py` | 追加 `PROMOTE_WIN_RATE_THRESHOLD`/`MIN_REGRESSION_TASKS`（§4.1） |

**只读参照（不修改）：** `evoagent/models.py`、`evoagent/storage.py`、`evoagent/skills/registry.py`、`evoagent/eval/benchmark.py`、`evoagent/eval/store.py`、`evoagent/eval/evaluator.py`、`evoagent/eval/experience.py`、`evoagent/execution/*`、`evoagent/llm.py`、`docs/system_design.md`、`.agents/transactions/0001/`–`0008/` 的历史产物（`plan.md`/`review.md` 等不可改）。

## 7. 推荐的实现策略（Recommended Implementation Strategy）

依赖关系：`config.py`（加常量）→ `evolution/__init__.py` → `evolver.py` → `validator.py` → 测试 → 验证 → 收尾提交。

1. **`config.py`**：追加两常量。
2. **`evolution/__init__.py`**：新建空包。
3. **`evolver.py`**：按 §4.2 实现 `_bump_patch`/`_evolve_prompt`/`SkillEvolver`。
4. **`validator.py`**：按 §4.3 实现 `_win_rate`/`ValidationResult`/`Validator`。
5. **`test_evolver.py`/`test_validator.py`**：按 §10 写。
6. **验证**：运行 §10 命令，确认全绿。
7. **收尾提交**：按 §10 末尾执行。

## 8. 预期变更（Expected Changes）

| 文件 | 变更性质 |
|---|---|
| `evoagent/config.py` | 修改：追加 `PROMOTE_WIN_RATE_THRESHOLD`/`MIN_REGRESSION_TASKS`（既有常量不动） |
| `evoagent/evolution/__init__.py` | 新建 |
| `evoagent/evolution/evolver.py` | 新建 |
| `evoagent/evolution/validator.py` | 新建 |
| `tests/test_evolver.py` | 新建 |
| `tests/test_validator.py` | 新建 |

（不修改 `models.py`、`storage.py`、`registry.py`、`benchmark.py`、`store.py`、`evaluator.py`、`experience.py`、`executor.py`、`retriever.py`、`llm.py`、`__init__.py`、`pyproject.toml`、`requirements.txt`、`docs/system_design.md`；不产生运行时数据文件。）

## 9. 验收标准（Acceptance Criteria）

1. **`config.py`**：新增 `PROMOTE_WIN_RATE_THRESHOLD == 0.55`、`MIN_REGRESSION_TASKS == 20`（设计既定值，不改）；既有常量不变。
2. **`SkillEvolver.evolve`**：返回候选 `Skill`——`version` 严格递增（patch bump）、`parent_version == 旧版本`、`status == "draft"`、`change_log` 非空、`tools` 原样、`metrics == {}`。
3. **Evolver 防污染（结构级）**：`evolve()` 签名无 `reference_answer`/`rubric`/`benchmark` 参数；设哨兵参考答案（经经验内容注入或检查 prompt）时，`chat_json` 收到的 prompt 不含哨兵参考答案。
4. **`Validator` 三支结局**：样本不足（<20）→ `promoted=False, reason="sample_insufficient"` 且**写** draft（`get` 可查）、**不写** failed_evolution；通过 → `promoted=True` 且 `get_active==candidate`、旧版 `deprecated`、历史版本可 `get`、`candidate.metrics` 含 benchmark 快照；不显著/回归 → `promoted=False` 且 `reason` 分别为 `insignificant`/`regression`、写 failed_evolution、候选**未注册**。
5. **win_rate 口径**：逐任务更高 1/持平 0.5/更低 0，均值正确（用 mock Benchmark 的确定 `per_task` 断言）。
6. **failed_evolution 落库**：`EvalStore.list_experiences(skill_id)` 可查到 `category=="failed_evolution"`、`trace_id==""`、`suggestion==reason` 的经验。
7. **测试**：`test_evolver.py`/`test_validator.py` 全绿，全量 `python -m pytest` 无回归；Evolver LLM 与 Validator Benchmark 全程 mock、不发真实请求。
8. **无越界**：不含 `EvolutionLoop`/`cli.py`/`tools.py`/工具演化/真实 LLM 请求/report 文件 I/O。

## 10. 验证策略（Verification Strategy）

在项目根目录运行：

```
python -m pytest tests/test_evolver.py tests/test_validator.py -v
```

并确认全量回归：

```
python -m pytest -v
```

**用例要求：**

- `tests/test_evolver.py`（mock `LLMClient.chat_json`）：
  - 候选字段：`version` patch 递增、`parent_version==旧版本`、`status=="draft"`、`change_log` 非空、`tools` 原样、`metrics=={}`。
  - LLM 输出缺键兜底：`prompt_template` 空 → 回退旧模板；`few_shots` 非 list → 回退旧 few_shots；`change_log` 空 → 默认非空。
  - 防污染：mock `chat_json` 捕获 prompt，断言 prompt 不含哨兵参考答案（结构级：`evolve` 无参考答案参数）。
- `tests/test_validator.py`（mock `Benchmark` + `tmp_path` `SkillRegistry`/`EvalStore`）：
  - 三支结局各一用例（样本不足 / 通过 / 不显著 + 回归）；`win_rate` 口径用确定 `per_task` 断言。
  - 通过分支：`registry.get_active(skill_id)==candidate`、旧版 `deprecated`、历史版本可 `get`、`candidate.metrics["benchmark"]` 含 `win_rate`/`success_rate`/`avg_total_score`。
  - 不通过/不显著：`list_experiences` 查得 `failed_evolution`、`trace_id==""`、候选未注册（`get(skill_id, candidate.version)` 为 `None`）。
  - 样本不足：候选已注册（draft）、`list_experiences` 无 failed_evolution。

**额外人工复核（非 pytest，编码者确认并记入 `execution.md`）：**

```
grep -rn "import sqlite3" evoagent/
```

真实 `import sqlite3` 语句**只**应出现在 `evoagent/storage.py`；`evolver.py`/`validator.py` 不得出现、也不得访问 `storage.conn`。

**收尾提交（用户已授权，必须执行）**：

全部验证通过后，Coder **一次性提交全部变更**：

```
git add -A && git commit -m "0008: 落地演化层 SkillEvolver 与 Validator"
```

- 提交信息**首行**必须以 `0008: ` 开头 + 一句目标概括（上例为建议措辞，可用同义简洁一句话）。
- **不 push、不 amend、不建分支、不 force-push**（仅本地提交）。
- **把提交哈希记入 `result.md`**（`git rev-parse HEAD` 取哈希）。

## 11. 明确的非目标（Explicit Non-Goals）

本任务**不做**以下任何事（防止范围蔓延）：

1. **`EvolutionLoop`（主循环编排）/ `cli.py`**——**顺延至 `0009`**。
2. **`tools.py` 与工具调用 / 工具子集校验**：v1 `SkillEvolver` 不改 `tools`（原样保留），`target_section=="tools"` 的经验虽传入 prompt、但工具不演化（工具演化依赖 `tools.py`，属后续执行层事务）。
3. **版本 minor/major 跳级**（§10「按 diff 大小自动判定」）：本事务恒 patch 递增；minor/major 的 diff 量化规则登记为已知简化（待有真实 diff 需求再定）。
4. **candidate 态**（§10 四态机）：本事务只用 `draft`/`active`/`deprecated` 三态，`candidate` 态不区分（候选即 draft），登记为设计遗留的已知简化（§3.1）。
5. **A/B「同批配对」的真正实现**：本事务是**顺序跑**（先 old 后 new）；「同批交错 + 同 judge 模型抵消漂移」的真实语义未实现（v1 judge 同模型 + mock 确定性，顺序跑等价），登记为已知局限。
6. **真实 LLM 调用 / 网络请求**（Evolver LLM、Validator Benchmark 全程 mock）。
7. **修改 `docs/system_design.md`**（只读）。
8. **除收尾提交（§10）外的任何 git 操作**：不 push、不 amend、不建分支、不 force-push、不拆多次提交。

---

### 已确认的决策（记录以备查；无「实现前需确认」的阻塞项）

| 裁定点 | 结论 |
|---|---|
| 三支结局（§2.1） | 通过 → register(draft)+promote+metrics；样本不足 → register(draft)、**不写** failed_evolution、`reason="sample_insufficient"`；不显著/回归 → **丢弃**（不注册）+ failed_evolution |
| `metrics` 快照（§2.2） | 仅在通过分支 promote 前填 `candidate.metrics={"benchmark":{"win_rate","success_rate","avg_total_score"}}` |
| 候选状态（§3.1） | 只用 `draft`（三态 draft/active/deprecated），`candidate` 态 v1 不区分，登记为设计遗留 |
| 版本跳级（§3.2） | 代码确定性 patch 递增（`_bump_patch`），不由 LLM 定、不做 minor/major diff 判定（延后） |
| `reason` 取值（§3.4） | `promoted` / `sample_insufficient` / `insignificant` / `regression` |
| failed_evolution 映射（§3.3） | `trace_id=""`、`target_section=""`、`suggestion=reason`、`confidence=1.0`、`summary` 含指标 |
| Evolver JSON schema（§4.2） | `{prompt_template, few_shots, change_log}`；缺键各自兜底（回退旧值 / 默认非空 change_log） |
| `ValidationResult`（§4.1） | `validator.py` 内 `@dataclass`（不进 models.py） |
| A/B 顺序跑（§3.5） | 登记已知局限：同批配对/judge 漂移的真实语义待后续 |
