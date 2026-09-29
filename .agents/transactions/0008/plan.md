# 事务 0008 计划（Plan）

> 规划者产出。遵循「文档精炼纪律」：引用而非复述，只写新增判断。

## 1. 当前状态

底座/门面/执行/评估（含 `Benchmark`）已就绪（`0001`–`0007`）。`evoagent/evolution/` 不存在；`SkillRegistry` 状态机（`register`/`promote`/`rollback`）与 `Benchmark.run` 已就绪；`config.py` 无 promote 阈值。

## 2. 问题

演化层缺失：`Experience[]` 无法变成候选新版本（`SkillEvolver`），`Benchmark` 无法驱动 A/B promote（`Validator`）。逆向流闭环（§9）断档。

## 3. 目标

落地演化层核心，串起「经验 → 候选 → 验证 → promote」：

- `evoagent/evolution/evolver.py`：`SkillEvolver`（Experience[] → 候选新版本）
- `evoagent/evolution/validator.py`：`Validator`（Benchmark A/B → win_rate 判定 → promote）
- `evoagent/config.py`：加 `PROMOTE_WIN_RATE_THRESHOLD`、`MIN_REGRESSION_TASKS`
- 测试：`test_evolver.py`、`test_validator.py`

## 4. 范围与工作量判断

**做**：上述 2 源 + 2 测（+ `evolution/__init__.py`）。**SkillEvolver + Validator 一并落地**——同属演化闭环、版本/防污染/A-B 贯穿两者，拆分反碎片化；体量与 `0006` 相当。`EvolutionLoop`（主循环编排）+ `cli.py` 顺延 `0009`。

**不做**：`EvolutionLoop`/`cli.py`/`tools.py`、工具子集校验（`tools.py` 未建，v1 工具不改）、真实 LLM 请求（Evolver LLM 与 Validator Benchmark 全程 mock）、report 文件 I/O。

## 5. 拟议变更

| 文件 | 变更 |
|---|---|
| `evoagent/config.py` | 追加 `PROMOTE_WIN_RATE_THRESHOLD=0.55`、`MIN_REGRESSION_TASKS=20` |
| `evoagent/evolution/__init__.py` | 新建包 |
| `evoagent/evolution/evolver.py` | 新建 `SkillEvolver`（§5.1） |
| `evoagent/evolution/validator.py` | 新建 `Validator` + `ValidationResult`（§5.2） |
| `tests/test_evolver.py` | 新建 |
| `tests/test_validator.py` | 新建 |

### 5.1 `SkillEvolver`（`evolution/evolver.py`）

```python
class SkillEvolver:
    def __init__(self, llm: LLMClient): ...
    def evolve(self, skill: Skill, experiences: list[Experience]) -> Skill: ...
```

- **输入**：旧 `Skill` + `Experience[]`（§3.4）；**输出**：候选 `Skill`（新版本、`status="draft"`、`parent_version=skill.version`、`change_log`）。
- **用 `llm.chat_json`** 让 LLM 据经验产出新 `prompt_template` + `few_shots` + `change_log` + 建议的版本跳级（patch/minor/major）；版本按 §10 SemVer 从旧版本 bump（默认 patch，diff 大则 minor/major，规则由优化者钉）。
- **v1 不改 `tools`**：工具子集校验依赖 `tools.py`（未建），本事务 `tools` 原样保留，`target_section=="tools"` 的经验跳过并登记（§3.4 工具约束延后）。
- **防污染（Evolver 侧，§11 答案隔离）**：`evolve()` 签名**无任何 `reference_answer`/`rubric`/`benchmark` 参数**，prompt 仅由 `skill` + `experience`（`category`/`target_section`/`summary`/`suggestion`）拼装——参考答案**结构上不可达**。

### 5.2 `Validator`（`evolution/validator.py`）

```python
class Validator:
    def __init__(self, benchmark: Benchmark, registry: SkillRegistry, eval_store: EvalStore): ...
    def validate(self, skill_id: str, candidate: Skill, tasks: list[BenchmarkTask]) -> ValidationResult: ...
```

- **A/B 配对**：`old = registry.get_active(skill_id)`；`old_report = benchmark.run(tasks, old)`、`new_report = benchmark.run(tasks, candidate)`（同 `tasks`、同批配对）。
- **win_rate**（§11）：逐任务 `new_score vs old_score`（`total_score`），更高记 1、持平记 0.5、更低记 0，取均值。
- **promote 判定（§9/§11，逐条对齐，阈值设计既定不改）**：
  1. `len(tasks) < MIN_REGRESSION_TASKS(20)` → **不自动 promote**，`reason="sample_insufficient"`（转人工）；
  2. `win_rate >= PROMOTE_WIN_RATE_THRESHOLD(0.55)` **且** `new_report.avg_total_score >= old_report.avg_total_score` → **promote**；
  3. `0.5 < win_rate < 0.55` → **不显著**，不 promote；
  4. 其余（win_rate≤0.5 或平均分下降）→ 不 promote。
- **promote 动作（版本衔接）**：`registry.register(candidate)`（`status="draft"`）→ `registry.promote(skill_id, candidate.version)`（draft→active、旧 active→deprecated，历史保留）。
- **不 promote 动作**：写 `category="failed_evolution"` 的 `Experience`（`eval_store.save_experience`，含 `win_rate`/`avg` 失败指标）。
- **`ValidationResult`**（`validator.py` 内 dataclass，不进 models.py）：`promoted` / `win_rate` / `old_avg` / `new_avg` / `sample_size` / `reason`。

## 6. 依赖

- 运行时：标准库 + 既有 `openai`（经 `llm.py`）。无新第三方。
- 顺序：`config.py` → `evolver.py` → `validator.py` → 测试。
- 既有：`LLMClient`（`0004`）、`SkillRegistry`（`0002`）、`Benchmark`（`0007`）、`EvalStore`（`0002`）、`Skill`/`Experience`（`models.py`）。

## 7. 风险

| 风险 | 缓解 |
|---|---|
| **A/B 阈值被改/漏对齐**（0.5/0.55/20） | 阈值集中 `config` 且值钉死（0.55/20），§5.2 四步判定逐条落地 + 测试覆盖每一步 |
| **promote 绕过状态机 / 原地改** | 只经 `registry.register`（draft）+ `registry.promote`；测试断言 promote 后单 active、旧版 deprecated、历史版本仍在 |
| **防污染（Evolver 侧）成「注释级」** | `evolve()` 无参考答案参数（结构级）；测试断言 prompt 仅含 skill+experience 内容、不含哨兵参考答案 |
| **版本跳级规则含糊** | 默认 patch、diff 大小升 minor/major，优化者钉死判定；parent_version/change_log 必填测试 |
| **win_rate 配对错位**（任务顺序不一致） | 同 `tasks` 列表顺序配对（benchmark.run 确定性）；测试锁定 |
| 范围蔓延（EvolutionLoop/cli/tools 带进） | §4 非目标逐条列出 |

## 8. 实施顺序

1. `config.py` 加 2 常量 + `evolution/__init__.py`。
2. `evolver.py`（`SkillEvolver`）+ `test_evolver.py`。
3. `validator.py`（`Validator` + `ValidationResult`）+ `test_validator.py`。
4. 全量验证（§10）。

## 9. 验收标准

1. `config.py` 新增 `PROMOTE_WIN_RATE_THRESHOLD == 0.55`、`MIN_REGRESSION_TASKS == 20`（设计既定值，不改）。
2. `SkillEvolver.evolve` 返回候选 `Skill`：`version` 严格递增、`parent_version==旧版本`、`status=="draft"`、`change_log` 非空、`tools` 原样、`metrics` 空。
3. **防污染**：`evolve()` 无参考答案参数；prompt 不含哨兵参考答案（结构级验证）。
4. **A/B 四步判定**：样本不足（<20）→ `promoted=False, reason="sample_insufficient"`；`win_rate>=0.55` 且 avg 不降 → promote；不显著（0.5<win_rate<0.55）→ 不 promote；avg 下降 → 不 promote。
5. **win_rate 口径**：逐任务更高 1/持平 0.5/更低 0，均值正确。
6. **版本衔接**：promote 后 `registry.get_active(skill_id)==candidate`、旧版 `deprecated`、历史版本可 `get`；promote 走 `registry.promote`（非绕过）。
7. **不 promote 落库**：`failed_evolution` Experience 写入 `EvalStore`（`list_experiences` 可查）。
8. 测试全绿（`test_evolver`/`test_validator` + 全量无回归），Evolver LLM 与 Validator Benchmark 全程 mock、不发真实请求。
9. 无越界：不含 `EvolutionLoop`/`cli.py`/`tools.py`/工具演化/真实请求。

## 10. 验证策略

```
python -m pytest tests/test_evolver.py tests/test_validator.py -v
python -m pytest -v        # 全量回归
```

- `test_evolver.py`（mock `LLMClient.chat_json`）：候选字段（version 递增/parent_version/status=draft/change_log/tools 原样）；防污染哨兵不进 prompt。
- `test_validator.py`（mock `Benchmark` + `tmp_path` `SkillRegistry`+`EvalStore`）：四步判定各一用例；win_rate 口径；promote 后单 active + 旧版 deprecated + 历史可查；不 promote 写 failed_evolution。
- 人工复核：`grep -rn "import sqlite3" evoagent/` 仅 `storage.py`；`evolver.py`/`validator.py` 不出现。
