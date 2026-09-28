# 事务 0001 执行报告（Execution）

> 编码者（Coder）产出。记录实际执行的步骤、重要实现决策及理由、与 `task.md` 的偏差、遇到的问题。

---

## 1. 实际执行的步骤

1. **阅读依据与核实环境**：阅读 `coder.md`、`protocol.md`、`transaction_protocol.md`、`task.md`（完整）、`project_state.md`、`active_transaction.md`、`docs/system_design.md`（相关章节）。实仓核实：
   - `python` = 3.13.9（≥3.10），`python -m pytest` = 8.4.2，与 task.md §2 一致；
   - 仓库当前仅含 `.agents/` 与 `docs/`，`find` 无任何 `.py` / `pyproject.toml` / `requirements.txt` / `tests/`，与 task.md「纯文档仓库」一致；
   - 事务文件实际位于 `.agents/transactions/0001/`（顶层 `transactions/` 不存在），与 task.md 开篇说明一致。
2. **实现顺序**（依赖关系 models → config → storage → tests）：
   - `pyproject.toml`、`requirements.txt`、`evoagent/__init__.py`
   - `evoagent/models.py`（8 个 dataclass + 递归序列化）
   - `evoagent/config.py`（路径 + 纯数值常量，无 LLM 参数）
   - `evoagent/storage.py`（`Storage`：连接 / 建表 / 通用 CRUD）
   - `tests/test_models.py`、`tests/test_storage.py`
3. **验证**：运行 `python -c "import evoagent"`（成功）、`python -m pytest tests/test_models.py tests/test_storage.py -v`（26 项全部 PASSED）、`grep -rn "import sqlite3" evoagent/`（真实 import 语句仅出现在 `storage.py`）。
4. **清理**：删除 pytest/pycache 生成物（`.pytest_cache/`、`__pycache__/`），保持源码树只含本事务批准的 8 个源文件（无 `data/`、无 egg-info）。

## 2. 重要的实现决策及理由

### 2.1 序列化用通用递归 helper + `_Serializable` 基类
采纳 task.md §7 的推荐策略：模块级 `_to_dict` / `_coerce` / `_from_dict` 三个函数做递归转换，所有 dataclass 继承 `_Serializable` 获得 `to_dict()` / `from_dict()`（`@classmethod`）。避免 8 处手写重复逻辑；`_coerce` 依据 `typing.get_type_hints` 的字段类型把内层 dict 重建为对应 dataclass（`list[FewShot]` → `list[FewShot 实例]`、`bool | None` 三态、`None` 与空列表区分）。

### 2.2 类型注解统一用 `X | None`（不用 `Optional`）
task.md §4.1 允许二者择一。统一采用 `dict | None` / `bool | None`（3.10+ 语法），并加 `from __future__ import annotations`；全项目无 `Optional` 引入，保持一致性。

### 2.3 `BenchmarkTask.reference_answer` 字段位置调整
`task.md` §4.1 字段表中 `reference_answer: str = ""` 排在 `rubric` 之前，但这违反 dataclass「无默认值字段在前、有默认值字段在后」的语法要求（否则 `TypeError`）。task.md §4.1 已注明该语法要求，因此将 `reference_answer` 移到末尾（`task_id, task, rubric, objective_check, tags, difficulty, reference_answer`）。字段名与类型不变、无增删。

### 2.4 `Storage.__init__` 给 `db_path` 提供默认值 `config.DB_PATH`
task.md §4.3 同时写了 `__init__(self, db_path: str | Path)` 与「默认连接路径为 `config.DB_PATH`」。为落实默认路径，签名实现为 `__init__(self, db_path: str | Path = config.DB_PATH)`，使 `Storage()` 直接可用、`connect()` 落到 `data/evoagent.db`。

### 2.5 JSON 字段的处理边界（关键裁定）
- `insert` / `update`：对任何 `dict` / `list` 值用标准库 `json.dumps` 序列化为 TEXT 后绑定（SQLite 无法绑定原生 dict/list，否则报错；这是「storage.py 用 json 序列化」的落点）。该规则按「值类型」判定，**不区分表**，因此不违反 §4.3「不得在通用 insert 硬编码 trace_steps 特殊逻辑」。
- `query`：返回原始值（`sqlite3.Row` → dict），JSON 列以 TEXT（JSON 字符串）返回，**不做自动反序列化**。理由：通用 `query` 无法判断哪些 TEXT 列是 JSON（需按表维护 schema 映射，违背「通用 CRUD」契约）；自动解析 JSON 字符串也易误伤普通文本列。因此「反序列化」交由后续领域门面层（TraceStore / EvalStore，各自知晓自己的 schema）在读取时完成。

> 这是对 task.md §4.5「由 storage.py 用 json 序列化 / 反序列化」与 §4.3 通用 CRUD 契约之间张力的显式取舍：序列化侧已落地（`insert`/`update`），反序列化侧记录为**已知局限**（见 `result.md`），不影响本事务验收（§9 无「query 自动反序列化 JSON」的验收项）。

### 2.6 SQL 安全：值一律参数化，结构件字符串拼接
`insert`/`update`/`delete`/`query` 的**值**全部经 `?` 占位符绑定（`params` 元组）；表名 / 列名 / where 子句 / order_by 作为结构件由调用方以字符串传入（SQLite 无法参数化标识符）。这符合 task.md §4.3「参数化 SQL、禁止拼接 SQL 注入」的本意（用户值参数化），并在 §5 约束 7 的边界内。

### 2.7 表结构逐列对照 §4.5
5 张表（`skills` / `traces` / `trace_steps` / `evals` / `experiences`）列名、类型、约束、主键、外键严格按 §4.5 落地；`trace_steps` 含 `truncated INTEGER NOT NULL DEFAULT 0` 列；`evals.passed` 为可空 `INTEGER`（三态）；`skills.metrics` / `traces.usage` / `evals.objective` / `evals.rubric_scores` 为 JSON TEXT 列。

## 3. 与 task.md 的偏差

| 项 | 说明 | 是否范围外 |
|---|---|---|
| `BenchmarkTask` 字段顺序 | `reference_answer` 后置（满足 dataclass 语法） | 否（task.md §4.1 已要求） |
| `Storage.__init__` 默认值 | `db_path` 默认 `config.DB_PATH` | 否（落实「默认连接路径」） |
| `query` 不自动反序列化 JSON | 见 §2.5，属「反序列化侧」后置 | 否（§4.3 CRUD 契约未要求） |
| `from __future__ import annotations` | 注解惰性求值，标准做法 | 否 |

无功能性范围越界；未创建任何 task.md 未列出的源码文件；未引入第三方运行时依赖；未做真实 LLM 调用 / 网络请求 / `git init`。

## 4. 遇到的问题

- 无阻塞性问题。
- `task.md` §4.5 的「序列化 / 反序列化」与 §4.3「通用 CRUD 如实存储」存在张力，已按 §2.5 裁定并在 `result.md` 记录为已知局限。
- 运行 pytest 会产生 `.pytest_cache/`、`__pycache__/` 生成物，已清理（非源码改动，不影响验证结论）。
