# 事务 0002 执行报告（Execution）

> 编码者（Coder）产出。记录实际执行的步骤、重要实现决策及理由、与 `task.md` 的偏差、遇到的问题。

---

## 1. 实际执行的步骤

1. **阅读依据与核实**：阅读 `coder.md`、`task.md`（完整）、`plan.md`/`review.md`/`context.md`（决策背景）、`project_state.md`、`active_transaction.md`、`docs/system_design.md`（§2/§3.1–§3.3/§5–§8/§10/§13）。读实仓源码（`models.py`/`config.py`/`storage.py`/`test_storage.py`），确认与 task.md §2 描述一致（`Storage.query` 不反序列化、`skills` 表无 `name`/`description`/`tags` 列、`trace_steps` 含 `truncated` 列但逻辑未实现）。
2. **按依赖顺序实现**：`config.py`（追加 2 常量）→ `storage.py`（`skills` DDL 加 3 列）→ 三个空包 `__init__.py` → `TraceStore` → `EvalStore` → `SkillRegistry` → 三个测试文件 → 更新 `test_storage.py` 的 `test_skills_columns`。
3. **验证**：`python -c "import evoagent.skills.registry, evoagent.execution.trace, evoagent.eval.store"` 成功；`python -m pytest tests/test_registry.py tests/test_trace.py tests/test_eval_store.py -v` → 26 passed；全量 `python -m pytest -v` → **52 passed**（含 0001 既有 26 项无回归）；`grep -rn "import sqlite3" evoagent/` 复核。
4. **清理**：删除 `.pytest_cache/` 与各 `__pycache__/` 生成物；确认无 `data/`、无 egg-info（测试全部用 `tmp_path` 注入，未触发生产 `data/` 落盘）。

## 2. 重要的实现决策及理由

### 2.1 `promote` / `rollback` 共享私有 `_set_active` helper
两者语义完全相同（§10「rollback 是 promote 的镜像操作」），抽一个 `_set_active(skill_id, version)`：目标不存在 → `ValueError`；先 `UPDATE` 把该 skill 下其它 active 版本置 `deprecated`（`version != ?` 排除目标，天然保证「目标已 active 时 no-op」），再 `UPDATE` 目标置 `active`。`promote` 与 `rollback` 各是一个公开方法，均调它。

### 2.2 三态 `passed` 与 `bool` 字段的门面侧转换
- `EvalStore` 用模块级 `_passed_to_int`（`True→1`/`False→0`/`None→NULL`）与 `_passed_from_row`（`1→True`/`0→False`/`NULL→None`），在 `save_eval` / `_eval_from_row` 内完成，然后交给 `EvaluationResult.from_dict`。
- `TraceStore` 读回 `retrieval_fallback`（INTEGER 0/1）时显式 `bool(...)`，`usage` 用 `json.loads(row["usage"]) if ... is not None else None`，确保 `ExecutionTrace.from_dict` 拿到的是 `bool` / `dict | None` 而非 `int` / 原始字符串（`_coerce` 对 `bool` 字段不会自动做 int→bool）。

### 2.3 JSON 反序列化只落在各门面 `get*`
`Storage.query` 返回原始 TEXT，反序列化全部由门面 `get*` 完成：`SkillRegistry.get`（`metrics`/`tags` 用 `json.loads`，`few_shots`/`tools` 交由 `Skill.from_dict` 的 `_coerce` 重建）；`TraceStore.get`/`list`（`usage`）；`EvalStore._eval_from_row`（`objective`/`rubric_scores`）。写入侧则依赖 `Storage.insert` 的 `_serialize_value` 自动 `json.dumps`，门面不手动 `json.dumps`（与 task.md §7 提示一致）。

### 2.4 `register` 的元数据先行、内容后写
先 `storage.insert("skills", ...)`（11 列），成功后再写 JSON 归档。这样重复 `(skill_id, version)` 时 `sqlite3.IntegrityError` 在写文件前上抛，不产生孤儿/覆盖的 JSON 文件。

### 2.5 门面 docstring 措辞微调（grep 卫生）
三个门面的 docstring 最初含「不 `import sqlite3`」字面串，会被 §10 的 `grep -rn "import sqlite3" evoagent/` 命中，虽非真实 import 语句但易造成误读。改为「不直接操作 SQLite」，使 grep 结果中真实 `import sqlite3` 语句仅剩 `storage.py` 一处。

## 3. 与 task.md 的偏差

| 项 | 说明 | 是否范围外 |
|---|---|---|
| 门面 docstring 措辞 | 将「不 `import sqlite3`」改为「不直接操作 SQLite」 | 否（纯注释措辞，为满足 §10 grep 验证清晰性） |

无功能性偏差：`config.py` 仅追加 2 常量、`storage.py` 仅改 `skills` DDL（通用 CRUD 契约与 `Storage` 方法签名未动）、未给 `TraceStep` 加字段、未改 `models.py`/`__init__.py`/`pyproject.toml`/`requirements.txt`/`.gitignore`、未做任何 git 操作、未引入第三方依赖。

## 4. 遇到的问题

无阻塞性问题。唯一注意点：`pyproject.toml` 仍为 `packages=["evoagent"]`（不含子包），`pip install .` 不会打包 `skills/execution/eval` 子包——task.md §11.9 已明确本事务**不得**顺手修改，登记为已知局限（见 `result.md`），测试从源码树运行不受影响。
