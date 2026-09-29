# 事务 0008 结果（Result）

> 编码者（Coder）产出。记录变更文件、测试/验证、结果、局限与后续建议。

---

## 1. 变更的文件

**新建（4）：**

| 文件 | 内容 |
|---|---|
| `evoagent/evolution/__init__.py` | 空包（docstring） |
| `evoagent/evolution/evolver.py` | `SkillEvolver` + `_bump_patch`/`_evolve_prompt` |
| `evoagent/evolution/validator.py` | `Validator` + `ValidationResult` + `_win_rate`/`_record_failed_evolution` |
| `tests/test_evolver.py` | 6 用例（候选字段 / bump_patch / 缺键兜底 / 防污染） |
| `tests/test_validator.py` | 5 用例（win_rate 口径 / 三支结局 / promote 状态机 / failed_evolution） |

**修改（1）：**

| 文件 | 变更 |
|---|---|
| `evoagent/config.py` | 追加 `PROMOTE_WIN_RATE_THRESHOLD=0.55`/`MIN_REGRESSION_TASKS=20`（既有常量未动） |

未修改 `models.py`、`storage.py`、`registry.py`、`benchmark.py`、`store.py`、`evaluator.py`、`experience.py`、`executor.py`、`retriever.py`、`llm.py`、`__init__.py`、`pyproject.toml`、`requirements.txt`、`docs/system_design.md`；未产生运行时数据文件。

## 2. 执行的验证命令及输出摘要

**命令 1：包导入**
```
python -c "import evoagent.evolution.evolver, evoagent.evolution.validator"
```
输出：`import ok`

**命令 2：定向测试**
```
python -m pytest tests/test_evolver.py tests/test_validator.py -v
```
输出摘要：`collected 11 items`，**`11 passed in 0.75s`**。

**命令 3：全量回归**
```
python -m pytest -v
```
输出摘要：`collected 115 items`，**`115 passed in 5.61s`**（既有 104 项无回归、无失败、无 skipped）。

**命令 4：SQL 唯一性人工复核**
```
grep -rn "import sqlite3" evoagent/
```
结果：真实 `import sqlite3` 语句仅 `evoagent/storage.py:13`；`evolver.py`/`validator.py` 无、也不访问 `storage.conn`。

## 3. 验证结果

**验收标准逐条：**

1. ✅ `config.py` 新增 `PROMOTE_WIN_RATE_THRESHOLD == 0.55`、`MIN_REGRESSION_TASKS == 20`（设计既定值）；既有常量不变。
2. ✅ `SkillEvolver.evolve`：候选 `version` patch 递增、`parent_version==旧版本`、`status=="draft"`、`change_log` 非空、`tools` 原样、`metrics=={}`。
3. ✅ Evolver 防污染（结构级）：`evolve()` 签名无 `reference_answer`/`rubric`/`benchmark` 参数；prompt 不含哨兵参考答案。
4. ✅ `Validator` 三支结局：样本不足→`promoted=False`/`reason="sample_insufficient"` 且写 draft、不写 failed_evolution；通过→`promoted=True` 且 `get_active==candidate`、旧版 deprecated、历史可 get、metrics 快照；不显著/回归→`promoted=False`、写 failed_evolution、候选未注册。
5. ✅ win_rate 口径：逐任务更高 1/持平 0.5/更低 0，均值正确。
6. ✅ failed_evolution 落库：`list_experiences` 查得 `category=="failed_evolution"`、`trace_id==""`、`suggestion==reason`。
7. ✅ 测试全绿（全量 115 passed），Evolver LLM 与 Validator Benchmark 全程 mock。
8. ✅ 无越界：不含 `EvolutionLoop`/`cli.py`/`tools.py`/工具演化/真实 LLM 请求/report 文件 I/O。

**结论：成功。** 全部验收标准满足，全部测试通过。

## 4. 已知局限

- **候选只用 `draft`/`active`/`deprecated` 三态**（§11.4）：设计 §10 四态机的 `candidate` 态本事务不区分（候选即 draft），登记为设计遗留的已知简化。
- **版本恒 patch 递增**（§11.3）：不做 minor/major 的 diff 量化判定，待真实 diff 需求再定。
- **A/B 是顺序跑**（§11.5）：先 old 后 new，非「同批交错 + 同 judge 模型」抵消 judge 漂移的真实语义（v1 judge 同模型 + mock 确定性，顺序跑等价）。

## 5. 后续问题

1. `EvolutionLoop`（主循环编排）+ `cli.py`——`0009`。
2. `tools.py` 与工具调用 / 工具子集校验（v1 Evolver 不改 tools，工具演化延后）。
3. judge 模型分离 + A/B 同批交错（抵消 judge 漂移）。

## 6. 建议的下一步

建议下一个事务（`0009`）落地 `EvolutionLoop`（主循环编排：收集低分 real trace → 聚合 → 提炼 → 演化 → 验证 → 更新注册表）+ `cli.py` 入口，串起完整闭环。

## 7. 提交

- 提交信息：`0008: 落地演化层 SkillEvolver 与 Validator`
- 提交哈希：`（提交后回填）`
