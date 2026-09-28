# 事务 0001 最终任务规格说明（Task）

> 优化者（Optimizer）产出。本文件是编码者实现的**唯一依据**，自包含：编码者无需阅读 `plan.md` / `review.md` 即可执行。
> 依据：`plan.md` + `review.md` + `docs/system_design.md` + 实仓核实。
>
> 说明：本仓库事务文件实际位于 `.agents/transactions/0001/`（顶层 `transactions/0001/` 不存在）。下文路径均以 `.agents/transactions/0001/` 为准。

---

## 1. 目标（Objective）

建立 EvoAgent 项目的**可安装 / 可导入包骨架**，并落地系统设计（`docs/system_design.md`）的**底座层**：

- 项目元信息与依赖声明（`pyproject.toml`、`requirements.txt`）
- 全部数据契约（`evoagent/models.py`：设计的 **8 个** dataclass，含递归序列化辅助）
- 集中配置（`evoagent/config.py`：路径 + 纯数值阈值 / 权重）
- SQLite 存储底座（`evoagent/storage.py`：连接 / 建表 / 通用 CRUD，全项目唯一写 SQL 处）
- 对应单元测试（`tests/test_models.py`、`tests/test_storage.py`）

成果须通过 `pytest` 验证，且**不引入任何第三方运行时依赖、不进行任何真实 LLM 调用或网络请求**。

## 2. 上下文（Context）

- 仓库当前为**纯文档仓库**，业务代码为零：经核实，无任何 `.py`、`pyproject.toml`、`requirements.txt`、`tests/`（`find` 结果为 0 个 `.py` 文件）。
- 本事务是**首个开发事务**，落地系统设计 §2 分层视图中的**底座层**（`models.py` 数据结构 · `config.py` 配置 · `storage.py` 存储底座），是上层存储门面（`SkillRegistry` / `TraceStore` / `EvalStore`）与执行 / 评估 / 演化层共同依赖的地基。
- 设计 §2 的依赖约束：**上层只能调下层（或同层）**；`storage.py` 是全项目**唯一写 SQL** 的地方（连接 / 建表 / 通用 CRUD）。上层领域门面只调 `storage.py`，不直接 `import sqlite3`。
- 数据对象（`models.py` 的 dataclass）是跨层的「合同」，模块之间只传对象、不传内部实现。
- **技术选型（设计 §14）**：Python 3.10+；`dataclasses`；标准库 `sqlite3`；测试 `pytest`；并发模型单进程单写者（SQLite 开 WAL）。
- **环境已核实**：`python` = 3.13.9（≥3.10）、`python -m pytest` = 8.4.2，均可直接使用。
- **仓库非 git 仓库**（已核实）。本事务不涉及 git 依赖（不产生 Skill 内容 JSON 文件），不阻塞；但编码者知悉：设计 §10/§11/§13 依赖的「git 追踪 JSON diff」是**未满足的设计前提**，属后续事务（SkillRegistry / 版本化）范畴，本事务不得因此 `git init` 或引入 git 相关行为。

## 3. 范围（Scope）

**做（In scope）**

1. `pyproject.toml` —— 包元信息（PEP 621：`name="evoagent"`、`version`、`requires-python = ">=3.10"`），**无运行时第三方依赖**；使 `evoagent` 可安装、`pytest` 可收集。
2. `requirements.txt` —— 仅开发依赖 `pytest`。
3. `evoagent/__init__.py` —— 包初始化，暴露 `__version__`。
4. `evoagent/models.py` —— 设计 §5–§11 的 **8 个 dataclass** + 递归序列化辅助（见 §4.1、§7）。
5. `evoagent/config.py` —— 路径常量 + 纯数值阈值 / 权重（见 §4.2）。
6. `evoagent/storage.py` —— `Storage` 类：连接（WAL）、建表（5 表）、通用 CRUD（见 §4.3）。
7. `tests/test_models.py`、`tests/test_storage.py` —— 见 §4.4。

**不做（Out of scope，明确非目标）** —— 详见 §11。

## 4. 需求（Requirements）

### 4.1 `evoagent/models.py` —— 8 个 dataclass + 递归序列化

**字段严格对照设计原文，不得增删字段。** 8 个 dataclass 及字段（类型 = 设计 §5–§11 原文）：

| dataclass | 字段（`: 类型`，带 `=` 者为设计给出的默认值） |
|---|---|
| `FewShot`（§5） | `input: str`、`output: str` |
| `ToolSpec`（§5） | `name: str`、`description: str`、`parameters: dict` |
| `Skill`（§5） | `skill_id: str`、`name: str`、`description: str`、`version: str`、`tags: list[str]`、`prompt_template: str`、`few_shots: list[FewShot]`、`tools: list[ToolSpec]`、`status: str`、`parent_version: str`、`change_log: str`、`metrics: dict`、`created_at: str`、`updated_at: str` |
| `TraceStep`（§6） | `step_index: int`、`type: str`、`content: str`、`tool_name: str = ""`、`tokens: int = 0`、`latency_ms: int = 0` |
| `ExecutionTrace`（§6） | `trace_id: str`、`task_id: str`、`task_source: str`、`skill_id: str`、`skill_version: str`、`started_at: str`、`ended_at: str`、`steps: list[TraceStep]`、`final_output: str`、`status: str`、`error: str = ""`、`error_type: str = ""`、`retrieval_fallback: bool = False`、`usage: dict \| None = None` |
| `EvaluationResult`（§7） | `eval_id: str`、`trace_id: str`、`eval_basis: str`、`passed: bool \| None`、`total_score: float`、`objective: dict`、`judge_score: float`、`rubric_scores: dict`、`judge_reason: str`、`evaluated_at: str` |
| `Experience`（§8） | `experience_id: str`、`trace_id: str`、`skill_id: str`、`category: str`、`summary: str`、`target_section: str`、`suggestion: str`、`confidence: float` |
| `BenchmarkTask`（§11） | `task_id: str`、`task: str`、`reference_answer: str = ""`、`rubric: list[str]`、`objective_check: dict`、`tags: list[str]`、`difficulty: str` |

**序列化辅助（每个 dataclass 必须支持双向 round-trip）**

- 每个 dataclass 提供 `to_dict() -> dict` 与 `from_dict(d: dict) -> 同类实例`（类方法）。
- **递归**：嵌套 dataclass 必须递归转换。`to_dict` 将嵌套 dataclass 转 dict、`list[dataclass]` 转 `list[dict]`；`from_dict` 必须把内层 dict 重建为对应 dataclass（例如 `Skill.few_shots` 里的 dict 必须重建为 `FewShot` 实例，`ExecutionTrace.steps` 里的 dict 必须重建为 `TraceStep` 实例）。禁止「浅层 `to_dict` 后 round-trip 退化为 dict」。
- **`None` 与空集必须区分**：字段值 `None` round-trip 后仍为 `None`；空列表 `[]` round-trip 后仍为 `[]`（不得被当成 `None`）。
- **联合类型 `bool | None`**：`EvaluationResult.passed` 的 `True` / `False` / `None` 三态必须精确保留（`from_dict` 不得把 `None` 误判为 `False`、也不得把 `False` 误判为缺失）。
- **dict 字段**（`parameters` / `metrics` / `usage` / `objective` / `rubric_scores` / `objective_check`）原样保留其 dict 内容（`usage` 为 `None` 时保持 `None`）。

**dataclass 实现约束**

- 可变默认值（`list` / `dict` 字段）**必须**用 `field(default_factory=list)` / `field(default_factory=dict)`，禁止用共享可变默认值（如 `tags: list[str] = []`）。
- 无默认值的字段在前、有默认值的字段在后（dataclass 语法要求）；`dict | None` 用 `from typing import Optional` 表达（`Optional[dict]`）或直接 `dict | None`（3.10+ 可用），二者择一、保持一致。

### 4.2 `evoagent/config.py` —— 路径 + 纯数值常量

集中以下常量（全部为模块级 `UPPER_SNAKE_CASE`）：

- **路径**：`DATA_DIR = "data"`、`DB_PATH = "data/evoagent.db"`（其余子目录 `data/skills`、`data/benchmarks`、`data/workspace` 属后续事务，本事务**不定义**）。
- **阈值 / 权重（设计已钉死的纯数值，非 LLM 参数）**：
  - `RETRIEVAL_FALLBACK_THRESHOLD = 0.3`（§3.2 检索兜底阈值）
  - `OBJECTIVE_WEIGHT = 0.7`、`JUDGE_WEIGHT = 0.3`（§7 评估融合权重）
  - `PASS_THRESHOLD = 0.6`（§7 `passed` 判定阈值）
- **WAL 开关**：`SQLITE_WAL_ENABLED = True`（§12/§14）。

**LLM 参数取舍（裁定）**：本事务**不定义**任何 LLM provider / model / API key / temperature 等常量。理由：`llm.py` 与 `Evaluator` 均未落地、本事务无任何 LLM 调用，现在定义属过早；这些常量随 `llm.py` / `evaluator` 事务引入。编码者**不得**在 `config.py` 中预置 LLM 参数。

### 4.3 `evoagent/storage.py` —— `Storage` 底座

`Storage` 类接口（最小可判定契约）：

- `__init__(self, db_path: str | Path)`：记录路径。
- `connect()`：建立连接，**启用 WAL**（`PRAGMA journal_mode=WAL`）；**自动创建父目录**（`Path(db_path).parent.mkdir(parents=True, exist_ok=True)` 语义，即「mkdir -p」）。默认连接路径为 `config.DB_PATH`（`data/evoagent.db`），连接后应确保 `data/` 目录被创建。
- `init_schema()`：`CREATE TABLE IF NOT EXISTS` 建齐 **5 张表**（幂等，可重复调用）。表结构见 §4.5。
- 通用 CRUD（4 个方法，全部**参数化 SQL**，禁止字符串拼接 SQL，防止注入）：
  - `insert(table: str, row: dict) -> int`：返回 `lastrowid`。
  - `query(table: str, where: str = "", params: tuple = (), order_by: str = "") -> list[dict]`：返回行列表（`sqlite3.Row` 转 dict）。
  - `update(table: str, set_values: dict, where: str, params: tuple) -> int`：返回受影响行数（`rowcount`）。
  - `delete(table: str, where: str, params: tuple) -> int`：返回受影响行数。

**分层约束（必须满足）**：`storage.py` 是**全项目唯一写 SQL** 的模块。除 `storage.py` 外，任何模块不得 `import sqlite3`（本事务范围内即 `models.py` / `config.py` / `__init__.py` 均不得 `import sqlite3`）。见 §9 的 grep 验证。

**截断规则归属（裁定）**：`trace_steps.content` 超过 4000 字符截断并置 `truncated=True` 是设计 §6 的持久化规则，但其**执行归属 TraceStore**（`execution/trace.py`，后续事务）。`storage.py` 的 `trace_steps` 表**必须包含 `truncated` 列**（§4.5），但 `storage.py` 的通用 `insert` **不**做截断——它如实存储传入值；4000 字符截断 + `truncated=True` 的**具体逻辑**由后续 TraceStore 在调用 `insert` 前完成。编码者不得在通用 `insert` 中硬编码任何与 `trace_steps` 相关的特殊逻辑。

### 4.4 测试要求

- `tests/test_models.py`：见 §9 验收标准 3 与 §10。
- `tests/test_storage.py`：见 §9 验收标准 4、5 与 §10。

### 4.5 表结构（Schema，逐列锁定）

> 布尔存 `INTEGER`（0/1）；`passed` 为三态，存可空 `INTEGER`（`None`→NULL、`True`→1、`False`→0）；JSON 字段（`metrics` / `usage` / `objective` / `rubric_scores`）存 `TEXT`，由 `storage.py` 用标准库 `json` 序列化 / 反序列化。列名与约束如下，编码者不得改名。

**`skills`**（§5 持久化映射：仅元数据；内容本体在 JSON 文件，属 SkillRegistry 后续事务）

| 列 | 类型 | 约束 |
|---|---|---|
| `skill_id` | TEXT | NOT NULL，主键之一 |
| `version` | TEXT | NOT NULL，主键之一 |
| `status` | TEXT | NOT NULL |
| `parent_version` | TEXT | NOT NULL DEFAULT '' |
| `change_log` | TEXT | NOT NULL DEFAULT '' |
| `metrics` | TEXT | NOT NULL DEFAULT '{}'（JSON） |
| `created_at` | TEXT | NOT NULL |
| `updated_at` | TEXT | NOT NULL |

`PRIMARY KEY (skill_id, version)`

**`traces`**（§6：一行一次执行，汇总字段；不含 `steps`）

| 列 | 类型 | 约束 |
|---|---|---|
| `trace_id` | TEXT | PRIMARY KEY |
| `task_id` | TEXT | NOT NULL |
| `task_source` | TEXT | NOT NULL |
| `skill_id` | TEXT | NOT NULL |
| `skill_version` | TEXT | NOT NULL |
| `started_at` | TEXT | NOT NULL |
| `ended_at` | TEXT | NOT NULL |
| `final_output` | TEXT | NOT NULL DEFAULT '' |
| `status` | TEXT | NOT NULL |
| `error` | TEXT | NOT NULL DEFAULT '' |
| `error_type` | TEXT | NOT NULL DEFAULT '' |
| `retrieval_fallback` | INTEGER | NOT NULL DEFAULT 0（bool） |
| `usage` | TEXT | 可空（NULL），JSON |

**`trace_steps`**（§6：一行一步；外键 `trace_id`）

| 列 | 类型 | 约束 |
|---|---|---|
| `trace_id` | TEXT | NOT NULL，主键之一，REFERENCES `traces(trace_id)` |
| `step_index` | INTEGER | NOT NULL，主键之一 |
| `type` | TEXT | NOT NULL |
| `content` | TEXT | NOT NULL DEFAULT '' |
| `tool_name` | TEXT | NOT NULL DEFAULT '' |
| `tokens` | INTEGER | NOT NULL DEFAULT 0 |
| `latency_ms` | INTEGER | NOT NULL DEFAULT 0 |
| `truncated` | INTEGER | NOT NULL DEFAULT 0（bool，§6 截断标记） |

`PRIMARY KEY (trace_id, step_index)`

**`evals`**（§7 `EvaluationResult`）

| 列 | 类型 | 约束 |
|---|---|---|
| `eval_id` | TEXT | PRIMARY KEY |
| `trace_id` | TEXT | NOT NULL |
| `eval_basis` | TEXT | NOT NULL |
| `passed` | INTEGER | 可空（NULL/1/0，三态） |
| `total_score` | REAL | NOT NULL |
| `objective` | TEXT | NOT NULL DEFAULT '{}'（JSON） |
| `judge_score` | REAL | NOT NULL DEFAULT 0 |
| `rubric_scores` | TEXT | NOT NULL DEFAULT '{}'（JSON） |
| `judge_reason` | TEXT | NOT NULL DEFAULT '' |
| `evaluated_at` | TEXT | NOT NULL |

**`experiences`**（§8 `Experience`；§3.3 EvalStore 门面之 `experiences` 表）

| 列 | 类型 | 约束 |
|---|---|---|
| `experience_id` | TEXT | PRIMARY KEY |
| `trace_id` | TEXT | NOT NULL |
| `skill_id` | TEXT | NOT NULL |
| `category` | TEXT | NOT NULL |
| `summary` | TEXT | NOT NULL DEFAULT '' |
| `target_section` | TEXT | NOT NULL DEFAULT '' |
| `suggestion` | TEXT | NOT NULL DEFAULT '' |
| `confidence` | REAL | NOT NULL |

> **裁定记录（表数量）**：设计内部在表清单上不一致（§13 `evoagent.db` 注记只列 4 表，§3.3 与 §13 文件表写「evals / experiences」、§8 定义 `Experience`、§9 要求写失败演化 Experience）。以 §3.3 + §8 + §9 为准，**裁定为 5 表**（含 `experiences`）。`Experience` 必须持久化，否则失败演化无法复盘。

## 5. 约束（Constraints）

1. **语言 / 运行时**：Python 3.10+（已核实本机 3.13.9）。类型注解用 3.10 可用语法（`X | None` 或 `Optional[X]`，全项目一致）。
2. **运行时依赖**：仅标准库（`sqlite3`、`dataclasses`、`typing`、`json`、`pathlib`）。**不得**引入任何第三方运行时依赖（openai / anthropic / numpy 均延后到后续事务，见 §11）。唯一第三方依赖是开发期 `pytest`。
3. **分层与 SQL 唯一性**：`storage.py` 是唯一写 SQL / `import sqlite3` 的模块；`models.py` / `config.py` 不得 `import sqlite3`。
4. **不越界**：本事务不产生任何上层模块（门面、执行 / 评估 / 演化 / 编排、`cli.py`）、不做真实 LLM 调用 / 网络请求、不 `git init`、不预建 `data/` 目录到源码树（`data/` 由 `storage.py` 连接时按需创建）。
5. **命名**：模块级常量 `UPPER_SNAKE_CASE`；类 `PascalCase`；方法 / 函数 `snake_case`；dataclass 字段名与设计原文完全一致（snake_case）。
6. **可变默认值**：dataclass 的 `list`/`dict` 字段用 `default_factory`（见 §4.1）。
7. **SQL 安全**：CRUD 一律参数化查询（`?` 占位符），禁止 f-string / `%` 拼接 SQL。
8. **包结构**：本事务仅创建 §9 列出的文件，目录结构对齐设计 §13 的底座层子集，不得创建 `evoagent/skills/`、`execution/`、`eval/`、`evolution/`、`llm.py`、`cli.py` 等文件。

## 6. 相关文件 / 模块（Relevant Files / Modules）

**本事务新建（唯一需要写入的文件）：**

| 文件 | 内容 | 对应设计 |
|---|---|---|
| `pyproject.toml` | PEP 621 元信息 + `requires-python>=3.10`，无运行时依赖 | §13/§14 |
| `requirements.txt` | 仅 `pytest` | §13/§14 |
| `evoagent/__init__.py` | `__version__` 导出 | §13 |
| `evoagent/models.py` | 8 个 dataclass + 递归序列化 | §5/§6/§7/§8/§11 |
| `evoagent/config.py` | 路径 + 阈值 / 权重 / WAL 常量 | §3.2/§7/§12/§13 |
| `evoagent/storage.py` | `Storage`：连接 / 建表 / CRUD | §2/§5/§6/§7/§8 |
| `tests/test_models.py` | 序列化 round-trip 测试 | §9/§10 |
| `tests/test_storage.py` | 建表 + CRUD + schema 锁定测试 | §9/§10 |

**只读参照（不修改）：** `docs/system_design.md`（§2 分层、§5–§8/§11 数据结构、§13 目录、§14 选型）；`.agents/transactions/0001/` 下的 `context.md` / `plan.md` / `review.md`（历史，不可改写）。

**后续事务才会出现（本事务不建）：** `evoagent/llm.py`、`evoagent/skills/{registry,retriever}.py`、`evoagent/execution/{executor,trace,tools}.py`、`evoagent/eval/{store,evaluator,experience,benchmark}.py`、`evoagent/evolution/{evolver,validator,loop}.py`、`evoagent/cli.py`。

## 7. 推荐的实现策略（Recommended Implementation Strategy）

按顺序（依赖关系：models → config → storage → tests）：

1. **元信息**：写 `pyproject.toml`（name/version/requires-python，不声明任何 `dependencies`）、`requirements.txt`（一行 `pytest`）。
2. **`models.py`**：先定义 8 个 dataclass（严格字段 + `default_factory`），再实现序列化。建议用 `dataclasses.fields()` + `dataclasses.is_dataclass()` 内省写一个**通用递归 helper**（如模块级 `_to_dict(obj)` / `_from_dict(cls, d)`），再由各 dataclass 的 `to_dict` / `from_dict` 调用它——可避免 8 处手写重复逻辑；只要 §9 验收标准 3 的 round-trip 测试通过即可，具体实现方式（通用 helper 或逐类显式实现）不强求。
3. **`config.py`**：按 §4.2 写常量；不写 LLM 参数。
4. **`storage.py`**：按 §4.3 / §4.5 实现。`connect()` 内 `mkdir(parents=True, exist_ok=True)` + `PRAGMA journal_mode=WAL`；`init_schema()` 用 `executescript` 或逐个 `CREATE TABLE IF NOT EXISTS`，列名 / 约束严格按 §4.5；CRUD 参数化。
5. **`tests/test_models.py`**：见 §10 用例清单。
6. **`tests/test_storage.py`**：用 `tmp_path` 临时库；`PRAGMA table_info(...)` 断言关键列（锁定 schema，避免「测试与实现共用同一 schema 的循环论证」）。
7. **验证**：运行 §10 命令，确认全绿。

## 8. 预期变更（Expected Changes）

| 文件（新建） | 变更性质 |
|---|---|
| `pyproject.toml` | 新增，包元信息 + `requires-python` |
| `requirements.txt` | 新增，`pytest` |
| `evoagent/__init__.py` | 新增，暴露 `__version__` |
| `evoagent/models.py` | 新增，8 个 dataclass + 递归序列化 |
| `evoagent/config.py` | 新增，路径 / 阈值 / 权重 / WAL 常量 |
| `evoagent/storage.py` | 新增，`Storage` 连接 / 建表 / CRUD |
| `tests/test_models.py` | 新增，round-trip 测试 |
| `tests/test_storage.py` | 新增，schema + CRUD 测试 |

（不修改任何已存在的文件；不产生运行时数据文件——`data/` 目录由测试用 `tmp_path` 隔离、由生产路径在连接时按需创建，不提交到源码树。）

## 9. 验收标准（Acceptance Criteria）

1. `evoagent` 包可导入（`python -c "import evoagent"` 成功），`pyproject.toml` 定义完整，`pytest` 可收集 `tests/` 下的测试。
2. `models.py` 完整定义设计 §5–§11 的 **8 个** dataclass（`FewShot` `ToolSpec` `Skill` `TraceStep` `ExecutionTrace` `EvaluationResult` `Experience` `BenchmarkTask`），字段名与类型与 §4.1 一致，无增删字段。
3. 每个 dataclass 的 `to_dict` / `from_dict` **递归 round-trip**：序列化再反序列化后字段值不丢、嵌套 dataclass 类型正确、`None` 与空列表可区分、`EvaluationResult.passed` 的 `True`/`False`/`None` 三态保留。
4. `storage.py` 能对任意路径（含 `tmp_path`）创建 SQLite 数据库并建齐 **5 张表**（`skills` / `traces` / `trace_steps` / `evals` / `experiences`），且 `storage.py` 是全项目唯一 `import sqlite3` 的模块。
5. `trace_steps` 表含 `truncated` 列（INTEGER 默认 0）；各表关键列与 §4.5 一致（用 `PRAGMA table_info` 断言锁定）。
6. `config.py` 定义了 `DATA_DIR` / `DB_PATH` / `RETRIEVAL_FALLBACK_THRESHOLD=0.3` / `OBJECTIVE_WEIGHT=0.7` / `JUDGE_WEIGHT=0.3` / `PASS_THRESHOLD=0.6` / `SQLITE_WAL_ENABLED`，且**不含**任何 LLM provider/model/key 常量。
7. `requirements.txt` 仅含 `pytest`；`pyproject.toml` 无运行时第三方依赖；未引入 openai / anthropic / numpy。
8. `tests/test_models.py` 与 `tests/test_storage.py` **全部 PASSED**，无失败、无被跳过掩盖的用例。
9. 未包含任何上层业务逻辑（门面 / 执行 / 评估 / 演化 / 编排 / `cli.py`）、未进行任何真实 LLM 调用或网络请求、未 `git init`。

## 10. 验证策略（Verification Strategy）

在项目根目录运行：

```
python -m pytest tests/test_models.py tests/test_storage.py -v
```

（若环境无 pytest，先 `pip install -r requirements.txt`；本机已核实 pytest 8.4.2 可用。）

**测试用例要求：**

- `test_models.py`：
  - 8 个 dataclass 各一个 round-trip 用例。
  - 嵌套 round-trip：`Skill` 含 1+ 条 `FewShot` 与 `ToolSpec`；`ExecutionTrace` 含 1+ 条 `TraceStep` 与 `usage=None` 及 `usage={"total_tokens": 1}` 两种情况。
  - 区分性用例：`tags=[]` 与 `usage=None` 分别在 round-trip 后仍为 `[]` 与 `None`；`passed` 三个值 `True`/`False`/`None` 分别 round-trip 精确。
  - 默认值用例：`ExecutionTrace.error_type==""`、`retrieval_fallback==False`、`TraceStep.tool_name==""`。
- `test_storage.py`（全部用 `tmp_path` 隔离）：
  - `connect()` 自动创建父目录（指向 `tmp_path/"nested"/"x.db"`，断言目录与文件存在）。
  - `init_schema()` 后断言存在 5 张表（查 `sqlite_master`）。
  - `PRAGMA table_info(<每张表>)` 断言关键列（至少：`skills` 的 `skill_id`/`version`/`status`；`traces` 的 `trace_id`/`task_source`/`status`/`error_type`/`retrieval_fallback`/`usage`；`trace_steps` 的 `trace_id`/`step_index`/`content`/`truncated`；`evals` 的 `eval_id`/`passed`/`total_score`；`experiences` 的 `experience_id`/`confidence`）。
  - CRUD round-trip：向 `skills`（或 `experiences`）`insert` 一条 → `query` 回来字段一致 → `update` 一个字段 → `query` 确认变更 → `delete` → `query` 确认为空。
  - WAL：连接后 `PRAGMA journal_mode` 返回 `wal`。

**额外人工复核（非 pytest，编码者自行确认并记入 `execution.md`）：**

```
grep -rn "import sqlite3" evoagent/
```

结果中 `import sqlite3` **只**出现在 `evoagent/storage.py`；`models.py` / `config.py` / `__init__.py` 不得出现。

## 11. 明确的非目标（Explicit Non-Goals）

本任务**不做**以下任何事（防止范围蔓延）：

1. **`evoagent/llm.py`**（LLM 薄封装）—— 需引入 openai / anthropic SDK 与 provider 决策，留待后续事务。
2. **存储领域门面** `SkillRegistry` / `TraceStore` / `EvalStore`（`skills/registry.py`、`execution/trace.py`、`eval/store.py`）。
3. **任何上层模块**：执行 / 评估 / 演化 / 编排层、`cli.py`、`SkillRetriever` / `AgentExecutor` / `Evaluator` / `ExperienceExtractor` / `Benchmark` / `SkillEvolver` / `Validator` / `EvolutionLoop`、`tools.py`。
4. **`Task` dataclass** —— 设计全文引用 `Task` 却未给出其字段定义（仅 `BenchmarkTask` 有定义）。本事务**不**捏造 `Task` 结构；后续 executor/retriever 事务需要时，应先回补设计再实现。
5. **任何真实 LLM 调用或网络请求**；不配置任何 API key / provider。
6. **第三方运行时依赖**（openai / anthropic / numpy 等）——延后到 `llm.py` / 检索事务再引入，届时更新 `pyproject.toml` / `requirements.txt`。
7. **`data/` 目录预建到源码树**、**种子技能 / benchmark JSON 内容文件**、**Skill 内容 JSON 归档**（`data/skills/{id}/{version}.json` 属 SkillRegistry 事务）。
8. **`git init` 或任何 git 操作**（仓库当前非 git，本事务不依赖 git）。
9. **4000 字符截断逻辑的实现** —— `truncated` 列本事务建好，但截断 + 置位逻辑归属后续 TraceStore。
10. **工作区文档路径不一致的修复**（`.agents/transactions/0001/` vs 顶层 `transactions/0001/` 的跨文档口径问题）—— 属工作区文档层事务，不在本代码事务范围内，此处仅作记录以免遗失。

---

### 实现前需确认（若无，则按默认处理）

> 本任务所有需求均已由设计 + 实仓核实钉死，**无**需编码者临场猜测的开放问题。以下为已裁定、无需再确认的决定（记录以备查）：

- **dataclass 数量 = 8**（计划中的「9」为笔误，已更正）。
- **表数量 = 5**（含 `experiences`），已裁定。
- **`config.py` 不定义 LLM 参数**，已裁定延后。
- **`requirements.txt` 仅 `pytest`**，openai/anthropic/numpy 延后，已裁定。
- **截断逻辑归属 TraceStore**，`storage.py` 仅提供 `truncated` 列，已裁定。
