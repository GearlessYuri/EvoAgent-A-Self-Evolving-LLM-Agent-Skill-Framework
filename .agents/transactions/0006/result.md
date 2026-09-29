# 事务 0006 结果（Result）

> 编码者（Coder）产出。记录变更文件、测试/验证、结果、局限与后续建议。

---

## 1. 变更的文件

**新建（4）：**

| 文件 | 内容 |
|---|---|
| `evoagent/eval/evaluator.py` | `Evaluator`（六分支 eval_basis + passed 三态）+ `_judge_prompt` + `GENERIC_RUBRIC` |
| `evoagent/eval/experience.py` | `ExperienceExtractor` + `_extract_prompt` + `CATEGORIES`/`TARGET_SECTIONS`/`_MIN_CONFIDENCE` |
| `tests/test_evaluator.py` | 8 用例（六分支 / judge 跳过 / 写库回读 / 未知 type） |
| `tests/test_experience.py` | 5 用例（提取 / confidence 过滤 / 非法字段丢弃 / 非 list / 异常上抛） |

**修改（2）：**

| 文件 | 变更 |
|---|---|
| `evoagent/llm.py` | 追加 `import json` + `_parse_json_object` + `chat_json()`；docstring 删去「chat_json」 |
| `tests/test_llm.py` | 追加 4 个 `chat_json` 用例 |

未修改 `models.py`、`storage.py`、`eval/store.py`、`execution/trace.py`、`execution/executor.py`、`skills/*`、`config.py`、`__init__.py`、`pyproject.toml`、`requirements.txt`、`docs/system_design.md`；未产生运行时数据文件。

## 2. 执行的验证命令及输出摘要

**命令 1：包导入**
```
python -c "import evoagent.eval.evaluator, evoagent.eval.experience; from evoagent.llm import LLMClient"
```
输出：`import ok`

**命令 2：定向测试**
```
python -m pytest tests/test_llm.py tests/test_evaluator.py tests/test_experience.py -v
```
输出摘要：`collected 25 items`，**`25 passed in 3.02s`**。

**命令 3：全量回归**
```
python -m pytest -v
```
输出摘要：`collected 92 items`，**`92 passed in 4.32s`**（既有 75 项无回归、无失败、无 skipped）。

**命令 4：SQL 唯一性人工复核**
```
grep -rn "import sqlite3" evoagent/
```
结果：真实 `import sqlite3` 语句仅 `evoagent/storage.py:13`；`evaluator.py`/`experience.py` 无、也不访问 `storage.conn`。

## 3. 验证结果

**验收标准逐条：**

1. ✅ `chat_json(prompt) -> dict`：纯 JSON、带前后缀 JSON 均解析成功，非 JSON 抛 `ValueError`；`complete`/`complete_with_usage` 行为不变（既有 `test_llm.py` 无回归）；docstring 已删去 `chat_json`。
2. ✅ 分层：`Evaluator` 只调 `llm`/`eval_store`，`ExperienceExtractor` 只调 `llm`（grep 无 `import sqlite3`/`Storage`）。
3. ✅ 六分支 `eval_basis` + `passed` 三态：`objective`（定论 True/False）、`mixed`/`judge_rubric`（`>= PASS_THRESHOLD`）、`judge_generic`（恒 None）；含 `contains`+无 rubric → `judge_generic`+`passed=None`。
4. ✅ 跳过 judge：`objective` 定论（error/timeout、exact）不调 judge；mixed/judge_rubric/judge_generic 调 judge。
5. ✅ `objective_score`：exact/contains 命中 `1.0`、未命中 `0.0`；比较用 `objective_check["value"]`。
6. ✅ 写库回读：`get_eval(eval_id)` 回读 `objective`/`rubric_scores`/`passed`/`total_score`/`eval_basis` 一致。
7. ✅ `ExperienceExtractor`：返回 `list[Experience]`；枚举合法、`summary` 非空、`confidence` 过滤（`<0.5` 丢弃）、非法枚举/空 summary 丢弃、`trace_id`/`skill_id` 取自入参。
8. ✅ 测试全绿（全量 92 passed），全程 mock、judge 不发真实请求。
9. ✅ 无越界：不含 `Benchmark`/演化层/`test_script` 客观执行/真实 LLM 请求。

**结论：成功。** 全部验收标准满足，全部测试通过。

## 4. 已知局限

- **judge 与执行同模型**（§11.5）：本事务未引入 `LLM_JUDGE_MODEL`，judge 复用 `config.LLM_MODEL`（设计 §7 要求「不同模型」，接受简化）；若需消除自偏好偏差，后续加常量。
- **`test_script` 客观类型未实现**（§11.3）：`evaluate` 对未知 type 视作「无客观」走 judge（不崩溃），`test_script` 的客观执行延后至 `0007` Benchmark 事务。
- **`_MIN_CONFIDENCE` 硬编码在 `experience.py`**（非 `config.py`，保持「无 config 变更」）；若需调参，后续提升为 config。

## 5. 后续问题

1. `Benchmark`（任务集 + 运行器 + 汇总）——`0007`，是 `Validator` A/B 的「尺子」，届时补 `test_script` 客观执行。
2. `SkillEvolver`/`Validator`/`EvolutionLoop`（演化/编排层）。
3. judge 模型分离（若需要）与 confidence 阈值入 config。

## 6. 建议的下一步

建议下一个事务（`0007`）落地 `Benchmark`（任务集加载 + 批量「执行→评估→汇总」+ `test_script` 客观执行），随后进入演化层 `SkillEvolver`/`Validator`。

## 7. 提交

- 提交信息：`0006: 落地评估层 Evaluator 与 ExperienceExtractor`
- 提交哈希：`（提交后回填）`
