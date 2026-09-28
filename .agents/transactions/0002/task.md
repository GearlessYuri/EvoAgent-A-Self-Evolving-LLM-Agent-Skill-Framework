# 事务 0002 最终任务规格说明（Task）

> 优化者（Optimizer）产出。本文件是编码者实现的**唯一依据**，自包含：编码者无需阅读 `plan.md` / `review.md` 即可执行。
> 依据：`plan.md` + `review.md` + `docs/system_design.md` + 事务 `0001` 落地后的实仓源码 + 实仓核实。
>
> 说明：本仓库事务文件实际位于 `.agents/transactions/0002/`（顶层 `transactions/` 不存在）。下文路径均以 `.agents/transactions/0002/` 为准。

---

## 1. 目标（Objective）

在事务 `0001` 已交付的**底座层**（`models.py` / `config.py` / `storage.py`）之上，落地系统设计 §2 的**存储领域门面层**，使上层模块能以**领域对象**完成持久化，并闭合 `0001` 显式后置的两处逻辑：

- `evoagent/skills/registry.py` —— `SkillRegistry`：技能版本 CRUD + 状态机 + active 指针 + 内容 JSON 归档
- `evoagent/execution/trace.py` —— `TraceStore`：Trace 写入 / 查询 + 4000 字符截断
- `evoagent/eval/store.py` —— `EvalStore`：评估结果 / 经验读写
- 配套单元测试：`tests/test_registry.py`、`tests/test_trace.py`、`tests/test_eval_store.py`

闭合的两处后置逻辑：

1. **JSON 字段反序列化**：`Storage.query()` 现以 TEXT 返回原始 JSON 字符串（`metrics` / `usage` / `objective` / `rubric_scores`），门面在 `get*` 时用 `json.loads` 还原为 dict。
2. **`trace_steps.content` 4000 字符截断 + `truncated` 置位**：`truncated` 列已在（`0001` 建好），截断逻辑归属 `TraceStore`，本事务实现。

成果须通过 `pytest` 验证，且不引入任何第三方运行时依赖、不进行任何真实 LLM 调用 / 网络请求 / git 提交。

## 2. 上下文（Context）

- 事务 `0001` 已落地底座层：`models.py`（8 个 dataclass + `_Serializable` 递归 `to_dict`/`from_dict`）、`config.py`（`DATA_DIR`/`DB_PATH` + 4 个阈值权重 + `SQLITE_WAL_ENABLED`）、`storage.py`（`Storage`：`connect()`/`init_schema()`/`insert`/`query`/`update`/`delete`，5 表，参数化 CRUD）。26 项测试通过。
- **实仓现状（已核实）**：`evoagent/` 下无 `skills/`/`execution/`/`eval/` 子包，三门面均未实现；`git` 已初始化（`main`，HEAD `78d505e`）；既有测试 `python -m pytest tests/ -q` → `26 passed`。
- `Storage` 关键行为（编码者必须据此实现，详见 `evoagent/storage.py`）：
  - `insert`/`update` 对任何 `dict`/`list` 值自动 `json.dumps` 后存 TEXT；`query` **不**自动反序列化，JSON 列以 JSON 字符串返回。
  - CRUD 一律参数化（值经 `?` 绑定）；`Storage.__init__(self, db_path=config.DB_PATH)`；`connect()` 自动建父目录 + WAL；`init_schema()` 幂等建 5 表。
  - `Storage` 是**全项目唯一 `import sqlite3` / 写 SQL** 的模块。门面**只能**调用 `Storage` 的通用 CRUD（`insert`/`query`/`update`/`delete`），**不得**访问 `storage.conn`、不得 `import sqlite3`。
- **设计分层约束（§2）**：上层只能调下层；数据对象（`models.py` dataclass）是跨层「合同」。门面与上层之间只传 dataclass 对象。
- **环境**：Python 3.13.9（≥3.10）、pytest 8.4.2，均可用。
- **git 状态提示**：工作树当前含未提交的状态文件改动（`M .agents/state/*.md`）与未跟踪的 `.agents/transactions/0002/`，属事务自身对状态文件的正常更新，**不影响本事务代码**。本事务**不做任何 git 操作**（不 add / 不 commit）；门面落盘到 `data/skills/*.json` 后 `git status` 会出现未跟踪的 `data/`，属预期（`.gitignore` 只忽略 `*.db`/`*.sqlite3`，不忽略 `data/`），**不要**把它当作范围外残留去处理。

## 3. 范围（Scope）

**做（In scope）**

1. `evoagent/config.py`（**仅追加**两个常量，不改动既有常量）：`SKILLS_DIR`、`TRACE_CONTENT_MAX_CHARS`（见 §4.1）。
2. `evoagent/storage.py`（**仅改 `skills` 表 DDL**，加 3 列；通用 CRUD 契约不动）：见 §4.2。
3. `evoagent/skills/__init__.py`、`evoagent/execution/__init__.py`、`evoagent/eval/__init__.py`（新建空包，含 docstring）。
4. `evoagent/skills/registry.py` —— `SkillRegistry`（§4.3）。
5. `evoagent/execution/trace.py` —— `TraceStore`（§4.4）。
6. `evoagent/eval/store.py` —— `EvalStore`（§4.5）。
7. `tests/test_registry.py`、`tests/test_trace.py`、`tests/test_eval_store.py`（§4.6）。
8. `tests/test_storage.py` 的 `test_skills_columns`（**仅追加**对 `name`/`description`/`tags` 三列的断言，锁定新 schema，其余不动）。

**不做（Out of scope，明确非目标）** —— 详见 §11。

## 4. 需求（Requirements）

### 4.1 `evoagent/config.py` —— 追加两个常量

在既有常量之后追加（**不改动**任何既有常量名 / 值）：

```python
# ── 存储门面（事务 0002 追加） ───────────────────────────────────────────
SKILLS_DIR = "data/skills"        # §5/§13 Skill 内容 JSON 归档根目录
TRACE_CONTENT_MAX_CHARS = 4000    # §6 trace_steps.content 截断阈值
```

### 4.2 `evoagent/storage.py` —— `skills` 表加 3 列

**裁定（§2.1 的解决）**：`Skill.name` / `description` / `tags` 持久化到 **SQLite `skills` 表**（新增 3 列），**不进 JSON 归档**。理由：

- 设计 §5 自己写明「元数据要频繁查询/统计（放进 SQLite）」，而 `name`/`description`/`tags` 正是查询字段——`list(tags=...)`（§3.1）按 tag 过滤、检索（§3.2）依赖 `description`。
- 设计 §8 的演化 `target_section` 只含 `prompt_template` / `few_shots` / `tools`（§9 演化也只改这三者），故 `name`/`description`/`tags` **不随版本演化**，是稳定元数据而非「要 diff 的内容本体」。
- 二者均偏离 §5 原文（§5 的两份清单都没列这三字段），但 SQLite 方案与 §5 的「好查询放 SQLite」原则一致，且避免 `list(tags=...)` 每次打开全部 JSON 文件（O(N) 文件读取）。
- 迁移代价为零：项目无生产数据，仅改 `_SCHEMA` 一段 DDL；3 列带默认值，`0001` 的既有测试不受影响。

将 `storage.py` 的 `_SCHEMA` 中 `skills` 表 DDL 改为（其余 4 表不动）：

```sql
CREATE TABLE IF NOT EXISTS skills (
    skill_id       TEXT NOT NULL,
    version        TEXT NOT NULL,
    name           TEXT NOT NULL DEFAULT '',
    description    TEXT NOT NULL DEFAULT '',
    tags           TEXT NOT NULL DEFAULT '[]',
    status         TEXT NOT NULL,
    parent_version TEXT NOT NULL DEFAULT '',
    change_log     TEXT NOT NULL DEFAULT '',
    metrics        TEXT NOT NULL DEFAULT '{}',
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    PRIMARY KEY (skill_id, version)
);
```

约束：

- 3 个新列**必须带默认值**（`''` / `''` / `'[]'`），保证 `0001` 的 `test_crud_roundtrip`（插入不含这三列的 `skills` 行）仍通过。
- `tags` 存 JSON 数组 TEXT（`["code","python"]`），与 `metrics` 同为 JSON TEXT 列；由 `Storage.insert` 的 `_serialize_value` 自动 `json.dumps` list 值。
- **只改这一段 DDL**，不改 `Storage` 类的方法签名 / 行为（`insert`/`query`/`update`/`delete` 的「通用契约」不变）。

### 4.3 `SkillRegistry`（`evoagent/skills/registry.py`）

**为什么存在**：技能需要「唯一可信来源」，否则无法沉淀、版本切换、回滚（§3.1）。

**构造签名（测试隔离的关键，必须如此实现）**：

```python
class SkillRegistry:
    def __init__(self, storage: Storage, skills_dir: str | Path = config.SKILLS_DIR):
        ...
```

- `storage`：由调用方注入 `Storage` 实例（测试注入 `Storage(tmp_path/"x.db")`）。
- `skills_dir`：JSON 归档根目录，默认 `config.SKILLS_DIR`；测试注入 `tmp_path/"skills"` 以实现隔离。

**方法（签名 + 语义）**：

| 方法 | 语义 |
|---|---|
| `register(skill: Skill) -> None` | 元数据写 `skills` 表（**11 列**，含 `name`/`description`/`tags`），内容本体写 JSON 归档。**尊重 `skill.status`**：`status` 为 `""`（空串）或 `None` 时才默认置 `"active"`；否则原样保存（`draft`/`candidate`/`deprecated` 均不被强制改成 active）。重复 `(skill_id, version)` → `sqlite3.IntegrityError` 上抛（PK 冲突，不 upsert）。 |
| `get(skill_id: str, version: str) -> Skill \| None` | 元数据（SQLite 行，含 `name`/`description`/`tags`/`metrics`）+ 内容（JSON 文件）合并重建完整 `Skill`。`metrics` 反序列化为 dict、`tags` 反序列化为 `list[str]`、`few_shots`/`tools` 重建为对应 dataclass 实例。SQLite 行不存在 → 返回 `None`；SQLite 行存在但 JSON 文件缺失 → 上抛 `FileNotFoundError`（内容本体缺失，Skill 不可重建）。 |
| `get_active(skill_id: str) -> Skill \| None` | 返回该 skill 当前 `status="active"` 的版本；无 active → 返回 `None`。 |
| `list(tags: list[str] \| None = None) -> list[Skill]` | 返回**全部 active 版本**（每 `skill_id` 至多一个），完整 `Skill` 对象（含内容）。`tags` 为 `None` 不过滤；否则只返回「tags 与给定列表**有交集**（至少一个匹配）」的 skill。**过滤顺序**：先 `Storage.query` 取 active 行 → Python 中按行内 `tags`（`json.loads` 后）过滤 → 仅对命中的 skill 加载 JSON 内容重建。返回按 `skill_id` 升序（确定性）。 |
| `promote(skill_id: str, version: str) -> None` | 目标 `version` 不存在 → `ValueError`。否则：目标版本 `status` 置 `active`，该 `skill_id` 下**其它**当前 active 版本置 `deprecated`。目标已 active → no-op（不把自己 deprecated）。 |
| `rollback(skill_id: str, to_version: str) -> None` | 同 `promote` 的机械操作（§10「promote 的镜像操作」）：`to_version` 不存在 → `ValueError`；`to_version` 已是当前 active → no-op；否则 `to_version` 置 active、当前 active 转 deprecated。语义上用于「active 指回历史版本」。 |
| `deprecate(skill_id: str) -> None` | 该 `skill_id` 当前 active 转 `deprecated`；无 active → no-op。 |

**持久化映射（§5，与裁定一致）**：

- SQLite `skills` 表：`skill_id, version, name, description, tags, status, parent_version, change_log, metrics, created_at, updated_at`（11 列）。
- JSON 归档 `{skills_dir}/{skill_id}/{version}.json`：**仅 3 个内容字段**（严格 §5）：
  ```json
  { "prompt_template": "...", "few_shots": [ {...}, ... ], "tools": [ {...}, ... ] }
  ```
  `few_shots` 用 `FewShot.to_dict()`、`tools` 用 `ToolSpec.to_dict()` 序列化。`register()` 写文件前 `Path.mkdir(parents=True, exist_ok=True)` 创建父目录。

**状态机（§10）**：`draft → candidate → active → deprecated`，回滚边 `deprecated → active` 仅经 `rollback()`。**不变量：同一 `skill_id` 同一时刻至多一个 `active`**（由 `promote`/`rollback`/`deprecate` 保证）。

**明确不做**：`metrics` 增量回写（使用次数 / 成功率由 traces/evals 聚合，属后续报告层）；`register` 不生成时间戳（`created_at`/`updated_at` 由调用方提供并原样持久化）；不校验 `promote`/`rollback` 的**来源**状态（完整状态机门控 `draft→candidate→active` 属 Evolver/Validator 后续事务，本层只保证「目标置 active + 单 active」机械不变式）。

### 4.4 `TraceStore`（`evoagent/execution/trace.py`）

**为什么存在**：Trace 是「发生了什么」的唯一客观记录，是评估与演化的唯一事实来源（§3.2）。

**构造签名**：

```python
class TraceStore:
    def __init__(self, storage: Storage):
        ...
```

**方法**：

| 方法 | 语义 |
|---|---|
| `save(trace: ExecutionTrace) -> None` | 写 `traces` 表 1 行（`steps` 除外的全部字段）+ `trace_steps` 表 N 行（每个 step 一行）。**非幂等**：`trace_id` 已存在 → `sqlite3.IntegrityError` 上抛（PK 冲突），不做 upsert。顺序：先插 `traces` 行，再逐条插 `trace_steps`。**截断**：每个 step 的 `content` 若 `len(content) > config.TRACE_CONTENT_MAX_CHARS`（4000），只存 `content[:4000]` 且 `truncated=1`；否则存原 `content` 且 `truncated=0`。截断在 TraceStore 侧完成，不污染通用 `Storage.insert`。 |
| `get(trace_id: str) -> ExecutionTrace \| None` | 合并 `traces` + `trace_steps`（按 `step_index` 升序）重建 `ExecutionTrace`；`usage` 反序列化为 dict（NULL → `None`）；`steps` 为 `list[TraceStep]`。`trace_id` 不存在 → 返回 `None`。 |
| `list(skill_id: str \| None = None, status: str \| None = None, since: str \| None = None) -> list[ExecutionTrace]` | 过滤查询：`skill_id` 精确匹配、`status` 精确匹配、`since` 按 `started_at >= since` 过滤（**用 `started_at`，不用 `ended_at`**）。**返回摘要（不含 steps，`steps=[]`）**——加载 steps 属 `get()` 的职责，避免 N+1 查询。返回按 `started_at` 升序（确定性）。 |

**截断验证路径（§2.2 的裁定）**：`truncated` 是**仅存于持久化层**的列（`trace_steps.truncated`），`TraceStep` dataclass 无此字段、`get()` 不返回截断标志。因此测试断言截断时，**不得**用 `get()` 验 `truncated`，而应直查 `trace_steps` 表：`storage.query("trace_steps", where="trace_id = ?", params=(tid,))`，断言返回行的 `content` 长度与 `truncated` 值（见 §10）。

### 4.5 `EvalStore`（`evoagent/eval/store.py`）

**为什么存在**：评估结果与经验需要持久化门面（§3.3「evals / experiences 表门面」）。

**构造签名**：

```python
class EvalStore:
    def __init__(self, storage: Storage):
        ...
```

**方法**：

| 方法 | 语义 |
|---|---|
| `save_eval(result: EvaluationResult) -> None` | 写 `evals` 表。**`passed` 三态转换**（§3.4 钉死）：`True→1`、`False→0`、`None→NULL`。`objective`/`rubric_scores`（dict）由 `Storage.insert` 自动 JSON 序列化。重复 `eval_id` → `sqlite3.IntegrityError`。 |
| `get_eval(eval_id: str) -> EvaluationResult \| None` | 读 `evals` 行，**逆转换**：`passed` `1→True`、`0→False`、`NULL→None`；`objective`/`rubric_scores` `json.loads` 还原为 dict；重建 `EvaluationResult`。不存在 → `None`。 |
| `list_evals(trace_id: str \| None = None) -> list[EvaluationResult]` | 按 `trace_id`（若给）过滤，返回完整 `EvaluationResult` 列表。 |
| `save_experience(exp: Experience) -> None` | 写 `experiences` 表（全标量字段，无 JSON 列）。重复 `experience_id` → `sqlite3.IntegrityError`。 |
| `list_experiences(skill_id: str \| None = None) -> list[Experience]` | 按 `skill_id`（若给）过滤，返回 `Experience` 列表。 |

**重建实现要点**：`Storage.query` 返回的行中 JSON 列是字符串、`passed` 是 int/None。调用 `EvaluationResult.from_dict(...)` / `Experience.from_dict(...)` / `Skill.from_dict(...)` / `ExecutionTrace.from_dict(...)` 之前，必须先手动完成 JSON 反序列化与 `passed` 的 int→bool/None 转换（`from_dict` 不会替你做这些）。此转换逻辑放各门面 `get*` 内。

### 4.6 测试要求

三个新测试文件全部用 `tmp_path` 隔离（SQLite 用 `Storage(tmp_path/"x.db")`、归档用 `tmp_path/"skills"` 注入 `SkillRegistry`）。用例清单见 §10。

## 5. 约束（Constraints）

1. **语言 / 运行时**：Python 3.10+（本机 3.13.9）；类型注解统一 `X | None`（项目既有约定，见 `models.py` 的 `from __future__ import annotations`）。
2. **运行时依赖**：仅标准库（`sqlite3`、`json`、`pathlib`、`dataclasses`、`typing`）。**不得**引入第三方运行时依赖（openai / anthropic / numpy 仍延后）。唯一第三方依赖是开发期 `pytest`。
3. **分层与 SQL 唯一性**：`storage.py` 仍是全项目**唯一** `import sqlite3` / 写 SQL 的模块。三个门面**只调** `Storage` 的通用 CRUD，**不得** `import sqlite3`、不得访问 `storage.conn`、不得自己拼接 SQL。
4. **不改底座契约**：除 §4.2 的 `skills` DDL 加 3 列外，**不改** `Storage` 的方法签名 / 行为；**不改** `config.py` 既有常量；**不改** `models.py` 任何 dataclass 字段（尤其**不得**给 `TraceStep` 加 `truncated` 字段）。
5. **不越界**：不实现检索 / 执行 / 评估 / 演化 / 编排逻辑、不写 `llm.py`、不写 `Task`、不做真实 LLM 调用 / 网络请求、不做任何 git 操作（不 add / commit）。
6. **命名**：类 `PascalCase`；方法 / 函数 `snake_case`；常量 `UPPER_SNAKE_CASE`；dataclass 字段名与 `models.py` 完全一致。
7. **错误处理**：本事务上抛标准异常（`ValueError`、`FileNotFoundError`、`sqlite3.IntegrityError`），**不自定义异常类**（避免无必要抽象）。
8. **确定性**：`list*` 返回顺序用 `Storage.query(..., order_by=...)` 显式指定（§4.3/§4.4 已给排序键）。

## 6. 相关文件 / 模块（Relevant Files / Modules）

**本事务新建：**

| 文件 | 内容 |
|---|---|
| `evoagent/skills/__init__.py` | 空包（docstring） |
| `evoagent/skills/registry.py` | `SkillRegistry`（§4.3） |
| `evoagent/execution/__init__.py` | 空包 |
| `evoagent/execution/trace.py` | `TraceStore`（§4.4） |
| `evoagent/eval/__init__.py` | 空包 |
| `evoagent/eval/store.py` | `EvalStore`（§4.5） |
| `tests/test_registry.py` | §4.6/§10 |
| `tests/test_trace.py` | §4.6/§10 |
| `tests/test_eval_store.py` | §4.6/§10 |

**本事务修改：**

| 文件 | 变更 |
|---|---|
| `evoagent/config.py` | 追加 `SKILLS_DIR`、`TRACE_CONTENT_MAX_CHARS`（§4.1） |
| `evoagent/storage.py` | `_SCHEMA` 的 `skills` 表加 3 列（§4.2） |
| `tests/test_storage.py` | `test_skills_columns` 追加 3 列断言（§4.2） |

**只读参照（不修改）：** `evoagent/models.py`（8 个 dataclass + 序列化）、`evoagent/config.py` 既有常量、`evoagent/storage.py` 既有 CRUD、`docs/system_design.md`、`.agents/transactions/0001/` 全量、`.agents/transactions/0002/` 的 `context.md`/`plan.md`/`review.md`（历史不可改）。

## 7. 推荐的实现策略（Recommended Implementation Strategy）

依赖关系：`config.py`（补常量）→ `storage.py`（加列）→ 三门面（并列，均依赖 `Storage` + `models`）→ 测试。三门面之间无相互依赖。

1. **补常量**：`config.py` 追加两个常量（§4.1）。
2. **加列**：`storage.py` `_SCHEMA` 的 `skills` 表加 3 列（§4.2），并更新 `tests/test_storage.py` 的 `test_skills_columns` 断言；跑既有测试确认 `26 passed` 未回归。
3. **`TraceStore`**（依赖最少，先做，作为「JSON 反序列化 + 截断」样板）：实现 `save`（含截断）/ `get`（`usage` 反序列化）/ `list`（摘要）。
4. **`EvalStore`**：复用同一反序列化模式；实现 `passed` 三态转换。
5. **`SkillRegistry`**（状态机 + JSON 归档，最复杂，最后做）：实现 `register`/`get`/`get_active`/`list`/`promote`/`rollback`/`deprecate`。
6. **测试**：写三个测试文件。
7. **验证**：运行 §10 命令。

**实现要点（供参考，不强制）**：

- 门面内可写一个模块级小 helper（如 `_json_loads_or_none` / `_bool_to_int`）复用 JSON 反序列化与三态转换，避免三处重复。
- 重建 `Skill` 时，先拼好完整 dict（SQLite 元数据已反序列化的 `metrics`/`tags` + JSON 内容 `prompt_template`/`few_shots`/`tools`），再 `Skill.from_dict(d)`（`_coerce` 会按类型提示把 `few_shots`/`tools` 的 dict 重建为 dataclass）。
- `Storage.insert`/`update` 已自动 `json.dumps` dict/list 值，门面无需手动 `json.dumps` 写库；但 `Storage.query` 读回 JSON 列是字符串，门面 `get*` 需手动 `json.loads`。

## 8. 预期变更（Expected Changes）

| 文件 | 变更性质 |
|---|---|
| `evoagent/config.py` | 修改：追加 2 常量（既有常量不动） |
| `evoagent/storage.py` | 修改：`skills` DDL 加 3 列（CRUD 契约不动） |
| `evoagent/skills/__init__.py` | 新建 |
| `evoagent/skills/registry.py` | 新建 `SkillRegistry` |
| `evoagent/execution/__init__.py` | 新建 |
| `evoagent/execution/trace.py` | 新建 `TraceStore` |
| `evoagent/eval/__init__.py` | 新建 |
| `evoagent/eval/store.py` | 新建 `EvalStore` |
| `tests/test_storage.py` | 修改：`test_skills_columns` 追加 3 列断言 |
| `tests/test_registry.py` | 新建 |
| `tests/test_trace.py` | 新建 |
| `tests/test_eval_store.py` | 新建 |

（不修改 `models.py`、`__init__.py`、`pyproject.toml`、`requirements.txt`、`.gitignore`；不产生运行时数据文件到源码树——`data/` 由测试用 `tmp_path` 隔离、生产路径按需创建。）

## 9. 验收标准（Acceptance Criteria）

1. **包结构**：`evoagent/skills/`、`evoagent/execution/`、`evoagent/eval/` 三包存在且可导入（`import evoagent.skills.registry` 等成功）；`evoagent` 根包仍可导入。
2. **分层约束**：`storage.py` 仍是全项目唯一 `import sqlite3` / 写 SQL 的模块；三个门面只调 `Storage`，不 `import sqlite3`（grep 验证）。
3. **`config.py`**：新增 `SKILLS_DIR == "data/skills"`、`TRACE_CONTENT_MAX_CHARS == 4000`；既有常量名 / 值不变。
4. **`skills` 表 schema**：含 `name`/`description`/`tags` 三列（`tags` 默认 `'[]'`）；既有 8 列不变；`test_storage.py` 的 schema 断言覆盖这三列。
5. **`SkillRegistry`**：
   - `register` + `get` 往返：注册一个 `Skill` 后 `get(skill_id, version)` 重建出字段一致、`metrics` 为 dict、`tags` 为 `list[str]`、`few_shots`/`tools` 为 dataclass 实例的 `Skill`；JSON 归档落盘于 `{SKILLS_DIR}/{skill_id}/{version}.json`，内容**仅** `prompt_template`/`few_shots`/`tools` 三字段。
   - `register` 尊重 `status`：`status="draft"` 的版本保存后 `get` 读回 `status=="draft"`（不被强制 active）；`status=""` 时默认 active。
   - `get_active` 返回唯一 active；`promote`/`rollback`/`deprecate` 后**单 active 不变量**成立；`rollback` 能把 active 指回历史版本。
   - `list(tags=...)` 按 tag（交集）过滤正确，返回 active 版本。
   - 不实现 `metrics` 增量回写。
6. **`TraceStore`**：
   - `save` + `get` 往返重建出 `steps` 为 `list[TraceStep]`、`usage` 为 dict（或 None）的 `ExecutionTrace`。
   - `content` 超过 4000 时截断存储且 `truncated=1`，不超过时 `truncated=0`（**直查 `trace_steps` 表**断言）。
   - `list(skill_id=...)` / `list(status=...)` 过滤正确，返回摘要（`steps=[]`）。
7. **`EvalStore`**：
   - `save_eval` + `get_eval` 往返：`objective`/`rubric_scores` 为 dict，`passed` 的 `True`/`False`/`None` 三态精确保留。
   - `save_experience` + `list_experiences(skill_id=...)` 往返正确。
8. **测试**：`test_registry.py`/`test_trace.py`/`test_eval_store.py` 全部 PASSED，且既有 `test_models.py`/`test_storage.py` 无回归（全量 `python -m pytest` 全绿），无失败、无跳过掩盖。
9. **无越界**：不含检索 / 执行 / 评估 / 演化 / 编排逻辑、`llm.py`、`Task`、真实 LLM 调用 / 网络请求、新增第三方运行时依赖、git 提交操作。

## 10. 验证策略（Verification Strategy）

在项目根目录运行：

```
python -m pytest tests/test_registry.py tests/test_trace.py tests/test_eval_store.py -v
```

并确认全量回归：

```
python -m pytest -v
```

**用例要求：**

- `test_registry.py`（`tmp_path` 注入 `Storage` 与 `skills_dir`）：
  - `register`/`get` 往返（`metrics` 为 dict、`tags` 为 list、`few_shots`/`tools` 为 dataclass 实例）。
  - JSON 归档落盘 `{skills_dir}/{skill_id}/{version}.json`，且内容仅 3 字段。
  - `register` 尊重 status（`status="draft"` 保存后 `get` 读回 draft；`status=""` 默认 active）。
  - 单 active 不变量：连续 `promote` 两个版本后旧版 `deprecated`、`get_active` 返回新版、同 skill 仅一个 active。
  - `rollback` 指回历史版本（active 回到旧版）。
  - `deprecate` 使 `get_active` 返回 `None`。
  - `list(tags=...)` 交集过滤（含多 tag 用例）。
  - 边界：`promote`/`rollback` 目标不存在 → `ValueError`；`get` 不存在 → `None`；`get_active` 无 active → `None`。
- `test_trace.py`（`tmp_path`）：
  - `save`/`get` 往返（`steps` 顺序与 `step_index`、`usage` 为 dict 与 None 两种）。
  - 截断：`content` 恰好 4000 不截断（`truncated=0`）、> 4000 截断（`truncated=1` 且长度为 4000，**直查 `trace_steps` 表**断言）。
  - `list` 按 `skill_id`/`status`/`since`（`started_at`）过滤，返回摘要（`steps=[]`）。
- `test_eval_store.py`（`tmp_path`）：
  - `save_eval`/`get_eval` 往返：`objective`/`rubric_scores` 为 dict；`passed` 三态 `True`/`False`/`None` 精确保留（参数化）。
  - `save_experience`/`list_experiences(skill_id=...)` 往返。

**额外人工复核（非 pytest，编码者确认并记入 `execution.md`）：**

```
grep -rn "import sqlite3" evoagent/
```

真实 `import sqlite3` 语句**只**应出现在 `evoagent/storage.py`；三个门面文件不得出现（门面也不得访问 `storage.conn`）。

## 11. 明确的非目标（Explicit Non-Goals）

本任务**不做**以下任何事（防止范围蔓延）：

1. **`evoagent/llm.py`** 及任何 LLM provider/model/key 配置（需 SDK 依赖与 provider 选型）。
2. **上层模块**：`SkillRetriever` / `AgentExecutor` / `Evaluator` / `ExperienceExtractor` / `Benchmark` / `SkillEvolver` / `Validator` / `EvolutionLoop` / `cli.py` / `tools.py`。
3. **`Task` dataclass 及设计回补**：本事务领域对象不含 `Task`（`ExecutionTrace.task_id`/`task_source` 仅为字符串字段）；`Task` 字段定义缺口留待执行层事务前回补设计。
4. **`metrics` 增量回写**：使用次数 / 成功率由 traces/evals 聚合查询（§3.1），本事务只存 benchmark 快照。
5. **检索 / embedding / TF-IDF**、benchmark 运行、任何真实 LLM 调用 / 网络请求。
6. **完整状态机门控**：不校验 `promote`/`rollback` 的**来源**状态（`draft→candidate→active` 的严格门控属 Evolver/Validator 后续事务）；本事务只保证「目标置 active + 单 active」机械不变式。
7. **给 `TraceStep` 加 `truncated` 字段**（`truncated` 仅 DB 层，不进入数据契约）。
8. **`Storage` 通用契约变更**（不加事务 API / upsert / 批量方法等）；门面保存的原子性不单独保证（顺序插入，详见 §4.4）。
9. **`pyproject.toml` 的 `packages` 更新**：当前 `packages=["evoagent"]` 不含子包，`pip install .` 不会打包子包。本事务不修（不在范围；`0001` 也未实测 pip 安装）。测试从源码树运行（`python -m pytest`，cwd 在 `sys.path`），不受影响。**编码者不得**顺手改 `pyproject.toml`；此问题登记为已知局限，留待引入 `cli.py` / 真实安装时统一处理。
10. **任何 git 操作**：不 `git add` / `git commit`。`data/skills/*.json` 落盘后出现在 `git status` 未跟踪清单属预期（`.gitignore` 不忽略 `data/`），非本事务范围。
11. **新第三方运行时依赖**（openai / anthropic / numpy 等）。

---

### 已裁定决定（记录以备查，无「实现前需确认」的开放问题）

> 本任务所有需求均已由设计 + 实仓源码钉死。以下为优化者裁定、编码者**不得再重新决定**的事项：

| 裁定点 | 结论 |
|---|---|
| `name`/`description`/`tags` 归属 | **SQLite `skills` 表加 3 列**（带默认值）；JSON 归档仅 3 内容字段（严格 §5） |
| `truncated` 验证路径 | 仅 DB 层；`get()` 不返回；测试**直查 `trace_steps` 表**断言 |
| `register()` 状态语义 | 尊重 `skill.status`，`""`/`None` 才默认 `active` |
| `list()` 返回粒度 | `SkillRegistry.list`=active 版本完整对象；`TraceStore.list`=摘要（`steps=[]`） |
| 状态机边界 | `promote`/`rollback` 目标不存在→`ValueError`、目标已 active→no-op；`deprecate` 无 active→no-op；`get_active` 无 active→`None` |
| `passed` 三态转换 | 门面 `save_eval`/`get_eval` 做 `True→1`/`False→0`/`None→NULL` 及逆转换 |
| `list(since=...)` 时间列 | 用 `started_at` |
| `save()` 幂等性 | 非幂等，重复 `trace_id` → `IntegrityError` |
| JSON 归档缺失 | `get*` 上抛 `FileNotFoundError` |
| 门面构造签名 | 注入 `Storage`；`SkillRegistry` 额外注入 `skills_dir`（默认 `config.SKILLS_DIR`） |
