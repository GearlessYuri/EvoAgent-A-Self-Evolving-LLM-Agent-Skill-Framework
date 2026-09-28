# 事务 0002 计划（Plan）

> 规划者（Planner）产出。按 `roles/planner.md` 要求的小节组织。

---

## 1. 当前状态（Current State）

仓库为 git 仓库（`main`，HEAD `78d505e`，工作树干净）。事务 `0001` 已落地**底座层**并经 26 项测试验证：

- `evoagent/models.py` —— 8 个 dataclass（`FewShot` / `ToolSpec` / `Skill` / `TraceStep` / `ExecutionTrace` / `EvaluationResult` / `Experience` / `BenchmarkTask`）+ 递归 `to_dict` / `from_dict`。
- `evoagent/config.py` —— `DATA_DIR` / `DB_PATH` + `RETRIEVAL_FALLBACK_THRESHOLD` / `OBJECTIVE_WEIGHT` / `JUDGE_WEIGHT` / `PASS_THRESHOLD` / `SQLITE_WAL_ENABLED`。
- `evoagent/storage.py` —— `Storage`：`connect()`（WAL + mkdir -p）、`init_schema()`（5 表）、通用参数化 `insert` / `query` / `update` / `delete`。

**尚缺存储领域门面层**：`evoagent/` 下不存在 `skills/`、`execution/`、`eval/` 包，也没有 `SkillRegistry` / `TraceStore` / `EvalStore` 任何实现。设计 §2 的存储层（§3.1–§3.3）尚未落地。

两处被 `0001` 显式后置的逻辑仍悬空：
- `Storage.query()` 对 JSON 列（`metrics` / `usage` / `objective` / `rubric_scores`）返回原始 TEXT，未反序列化；
- `trace_steps.content` 超 4000 字符截断 + `truncated=True` 未实现（`truncated` 列已在，逻辑未写）。

## 2. 问题（Problem）

**存储层只有通用底座，没有领域门面**，导致上层的执行 / 评估 / 演化层没有可用的持久化接口。具体证据：

1. `Skill` / `ExecutionTrace` / `EvaluationResult` / `Experience` 目前**只能通过裸 `Storage.insert/query` 落库**，调用方需自行处理 JSON 序列化 / 反序列化与表结构细节——这违反了 §2「模块之间只传对象，不传内部实现」的合同约定。
2. **JSON 反序列化缺失**（`0001/execution.md` §2.5、`result.md` §4 已记录为已知局限）：`get()` 回读的 `metrics` / `usage` / `objective` / `rubric_scores` 是字符串，无法直接当 dict 用。
3. **截断逻辑缺失**（`0001/result.md` §5.1）：设计 §6 要求 `content` 超 4000 字符截断并置 `truncated=True`，否则单步超大工具输出会撑爆数据库。
4. **技能版本状态机缺失**（设计 §10）：`draft → candidate → active → deprecated`、active 指针、`promote` / `rollback` / `deprecate`、单 active 不变量均未实现，Skill 无法沉淀、切换、回滚。
5. **Skill 内容归档缺失**（设计 §5）：内容本体（`prompt_template` / `few_shots` / `tools`）无 JSON 文件归档，无法人工 review / git diff。

这些缺失共同阻塞了后续执行层（`SkillRetriever` / `AgentExecutor`）与评估 / 演化层的落地。

## 3. 目标（Objective）

落地系统设计 §2 的**存储领域门面层**，使上层模块能以**领域对象**完成持久化，并闭合 `0001` 后置的两处逻辑：

- `evoagent/skills/registry.py` —— `SkillRegistry`：技能版本 CRUD + 状态机 + active 指针 + 内容 JSON 归档
- `evoagent/execution/trace.py` —— `TraceStore`：Trace 写入 / 查询 + 4000 字符截断
- `evoagent/eval/store.py` —— `EvalStore`：评估结果 / 经验读写
- 配套单元测试（`test_registry.py` / `test_trace.py` / `test_eval_store.py`）

三个门面共享同一 `Storage` 底座与数据契约，共同闭合「JSON 反序列化 + 截断」这两处后置逻辑，是一个连贯的存储层目标，而非互不相关的多个任务。

## 4. 范围（Scope）

**做（In scope）**

1. `evoagent/config.py`（**追加常量**，不改动现有常量）：新增 `SKILLS_DIR = "data/skills"`（§5/§13）、`TRACE_CONTENT_MAX_CHARS = 4000`（§6 截断阈值）。
2. `evoagent/skills/__init__.py`、`evoagent/execution/__init__.py`、`evoagent/eval/__init__.py`（新建包）。
3. `SkillRegistry`（§3.1）：见 §5.1。
4. `TraceStore`（§3.2）：见 §5.2。
5. `EvalStore`（§3.3）：见 §5.3。
6. `tests/test_registry.py`、`tests/test_trace.py`、`tests/test_eval_store.py`。

**不做（Out of scope，明确非目标）**

- `evoagent/llm.py`（LLM 封装，需 provider 选型与 SDK 依赖）。
- 执行层 / 评估层 / 演化层 / 编排层的其余模块：`SkillRetriever` / `AgentExecutor` / `Evaluator` / `ExperienceExtractor` / `Benchmark` / `SkillEvolver` / `Validator` / `EvolutionLoop` / `cli.py` / `tools.py`。
- **`Task` dataclass 及设计回补**——本事务的领域对象不含 `Task`（`ExecutionTrace.task_id` / `task_source` 仅为字符串字段），不涉及；登记为风险与后续建议。
- `metrics` 的**增量回写**（使用次数 / 成功率）——§3.1 明确由 traces / evals 聚合查询得出，门面只存 benchmark 快照，不做计数。
- 检索（TF-IDF / embedding）、benchmark 运行、真实 LLM 调用 / 网络请求。
- 任何 git 提交操作（JSON 归档文件仅落盘，是否提交由后续人工决定）。
- 新第三方运行时依赖（继续仅标准库 + 开发期 `pytest`）。

## 5. 拟议变更（Proposed Changes）

| 文件 | 变更性质 |
|---|---|
| `evoagent/config.py` | 追加 `SKILLS_DIR`、`TRACE_CONTENT_MAX_CHARS` 两常量（其余不动） |
| `evoagent/skills/__init__.py` | 新建包 |
| `evoagent/skills/registry.py` | 新建 `SkillRegistry`（§5.1） |
| `evoagent/execution/__init__.py` | 新建包 |
| `evoagent/execution/trace.py` | 新建 `TraceStore`（§5.2） |
| `evoagent/eval/__init__.py` | 新建包 |
| `evoagent/eval/store.py` | 新建 `EvalStore`（§5.3） |
| `tests/test_registry.py` | 新建（§9/§10） |
| `tests/test_trace.py` | 新建（§9/§10） |
| `tests/test_eval_store.py` | 新建（§9/§10） |

### 5.1 `SkillRegistry`（`skills/registry.py`）

**为什么存在**：技能需要一个「唯一可信来源」，否则无法沉淀、版本切换、回滚（§3.1）。

**职责与接口**（对应 §3.1）：
- `register(skill: Skill)` —— 元数据写 `skills` 表，内容本体写 JSON 归档；首个版本默认 active。
- `get(skill_id, version) -> Skill` —— 元数据（SQLite）+ 内容（JSON）合并重建完整 `Skill`；`metrics` 反序列化为 dict。
- `get_active(skill_id) -> Skill` —— 返回该 skill 当前 active 版本。
- `list(tags: list[str] | None = None) -> list[Skill]` —— 列出 skill；按 tags 过滤。
- `promote(skill_id, version)` —— 目标版本置 active，原 active 转 deprecated（§10）。
- `rollback(skill_id, to_version)` —— active 指回历史版本，当前 active 转 deprecated（§10 回滚边）。
- `deprecate(skill_id)` —— 当前 active 转 deprecated（无新 active）。

**持久化与状态机（§5 / §10）**：
- SQLite `skills` 表：仅元数据（沿用 0001 锁定的列，**不改表结构**）。
- JSON 归档 `data/skills/{skill_id}/{version}.json`：内容本体（`prompt_template` / `few_shots` / `tools`）。
- 状态机 `draft → candidate → active → deprecated`，回滚边 `deprecated → active` 仅经 `rollback()`；**不变量：同一 `skill_id` 同一时刻至多一个 active**。
- `metrics`：只存 benchmark 得分快照，**不做增量回写**（使用次数 / 成功率由 traces / evals 聚合，属后续报告层）。
- 只调 `storage.py`，**不 `import sqlite3`**。

**需落定的设计缺口（见 §7 风险 1）**：`Skill` 的 `name` / `description` / `tags` 在 §5 的 SQLite 元数据清单与 JSON 内容清单中均未列出，且 0001 的 `skills` 表无这三列。本计划**默认裁定**：三者作为「内容」写入 JSON 归档（与 `prompt_template` / `few_shots` / `tools` 同文件），使 JSON 文件自足、SQLite 表保持不动、避免 schema 迁移；`list(tags=...)` 据此加载内容过滤（v1 种子规模可接受）。评审者可在此处给出相反裁定（如改为 SQLite 列），由优化者综合。

### 5.2 `TraceStore`（`execution/trace.py`）

**为什么存在**：Trace 是「发生了什么」的唯一客观记录，是评估与演化的唯一事实来源（§3.2）。

**职责与接口**：
- `save(trace: ExecutionTrace)` —— 写 `traces` 表 + `trace_steps` 表（多行）。
- `get(trace_id) -> ExecutionTrace` —— 合并两表重建 Trace；`usage` 反序列化为 dict。
- `list(skill_id=None, status=None, since=None) -> list[ExecutionTrace]` —— 按 skill / 状态 / 时间过滤。
- 只调 `storage.py`。

**截断逻辑（闭合 0001 后置）**：写入 `trace_steps` 前，若 `content` 超过 `config.TRACE_CONTENT_MAX_CHARS`（4000），截断存储并置 `truncated=1`（True）；否则 `truncated=0`。截断在 TraceStore 侧完成，不污染通用 `Storage.insert`。

### 5.3 `EvalStore`（`eval/store.py`）

**为什么存在**：评估结果与经验需要持久化门面（§3.3「evals / experiences 表门面」）。

**职责与接口**：
- `save_eval(result: EvaluationResult)` / `get_eval(eval_id)` / `list_evals(trace_id=None)`。
- `save_experience(exp: Experience)` / `list_experiences(skill_id=None)`。
- 反序列化 `objective` / `rubric_scores`（dict）；`passed` 三态（NULL / 1 / 0）精确保留。
- 只调 `storage.py`。

## 6. 依赖（Dependencies）

- **运行时依赖**：仅标准库（`sqlite3` 只经 `storage.py`、`json`、`pathlib`、`dataclasses`）。无新增第三方。
- **测试依赖**：`pytest`（已具备）。
- **顺序依赖**：`config.py`（补常量）→ `SkillRegistry` / `TraceStore` / `EvalStore`（并列，均依赖 `Storage` + `models`）→ 测试。三者之间无相互依赖。
- **前置条件**：`Storage` / `models.py` / `config.py` 已就绪（0001 已交付）；git 已初始化（JSON 归档前提成立）；本机 Python 3.13.9 + pytest 8.4.2 可用。
- **对 `0001` 的依赖**：门面调用 `Storage` 的既有 CRUD 接口；不得改动 `storage.py` 的通用契约（截断、反序列化在门面侧完成）。

## 7. 风险（Risks）

| 风险 | 缓解 |
|---|---|
| 1. **`name`/`description`/`tags` 持久化位置是设计缺口**（§5 清单未列、0001 表无此列），若选错，后续检索 / 过滤会返工 | 已核实为事实缺口；默认裁定放 JSON 归档（零 schema 迁移），并在 `list(tags=...)` 加载内容过滤；**交评审者裁定**，优化者钉死 |
| 2. **JSON 字段反序列化漏做 / 做错**（`metrics`/`usage`/`objective`/`rubric_scores` 回读仍是字符串） | 每个门面的 `get*` 用 `json.loads` 还原 dict，并有对应测试断言「回读后为 dict 类型」 |
| 3. **截断边界错误**（恰好 4000 字符、多字节字符、`truncated` 置位缺失） | 测试覆盖「> 4000 截断 + 置位、≤ 4000 不截断不置位、边界值」；阈值走 `config.TRACE_CONTENT_MAX_CHARS` |
| 4. **状态机不变量被破坏**（同 skill 出现多个 active、promote 目标不存在、rollback 指向非历史版本） | 测试断言「promote/rollback/deprecate 后单 active 不变量」；目标不存在时抛异常；评审者核对 §10 状态机 |
| 5. **范围蔓延**：把检索 / 演化 / `llm.py` / `Task` 顺手带进本事务 | §4「明确非目标」逐条列出；编码者不得越界 |
| 6. **JSON 归档路径 / 文件布局与 §13 不一致**（`data/skills/{id}/{version}.json`） | `SKILLS_DIR` 集中到 `config.py`；测试用 `tmp_path` 覆盖归档路径 |
| 7. **`Task` 设计缺口遗留**（本事务不涉及，但执行层事务前必须回补） | 登记为后续建议；不在本事务处理 |

## 8. 实施顺序（Implementation Order）

1. 补 `evoagent/config.py`：新增 `SKILLS_DIR`、`TRACE_CONTENT_MAX_CHARS`。
2. 建 `skills/` / `execution/` / `eval/` 三个包（`__init__.py`）。
3. 实现 `TraceStore`（依赖最少，先闭合截断 + 反序列化，为后续做样板）。
4. 实现 `EvalStore`（复用同一反序列化模式）。
5. 实现 `SkillRegistry`（状态机 + JSON 归档，最复杂，最后做）。
6. 编写三个测试文件。
7. 运行验证命令（§10），确认全绿。

## 9. 验收标准（Acceptance Criteria）

1. **包结构**：`evoagent/skills/`、`evoagent/execution/`、`evoagent/eval/` 三包存在且可导入；`evoagent` 根包仍可导入。
2. **分层约束**：`storage.py` 仍是全项目唯一 `import sqlite3` / 写 SQL 的模块；三个门面只调 `storage.py`，不直接 `import sqlite3`（grep 验证）。
3. **`SkillRegistry`**：
   - `register` + `get` 往返：注册一个 `Skill` 后 `get(skill_id, version)` 重建出字段一致、`metrics` 为 dict、`few_shots`/`tools` 为对应 dataclass 实例的 `Skill`；
   - JSON 归档落盘于 `{SKILLS_DIR}/{skill_id}/{version}.json`，内容含 `prompt_template` / `few_shots` / `tools`（及裁定后的 `name`/`description`/`tags`）；
   - `get_active` 返回唯一 active 版本；`promote` / `rollback` / `deprecate` 后**单 active 不变量成立**；`rollback` 能把 active 指回历史版本；
   - `list(tags=...)` 按 tag 过滤正确；
   - 不实现 `metrics` 增量回写。
4. **`TraceStore`**：
   - `save` + `get` 往返重建出 `steps` 为 `list[TraceStep]`、`usage` 为 dict（或 None）的 `ExecutionTrace`；
   - `content` 超过 `TRACE_CONTENT_MAX_CHARS` 时截断存储且 `truncated=1`，不超过时 `truncated=0`；
   - `list(skill_id=...)` / `list(status=...)` 过滤正确。
5. **`EvalStore`**：
   - `save_eval` + `get_eval` 往返：`objective` / `rubric_scores` 为 dict，`passed` 的 `True`/`False`/`None` 三态精确保留；
   - `save_experience` + `list_experiences(skill_id=...)` 往返正确。
6. **测试**：`test_registry.py` / `test_trace.py` / `test_eval_store.py` 全部 PASSED，无失败、无跳过掩盖。
7. **无越界**：不含任何检索 / 执行 / 评估 / 演化 / 编排逻辑、`llm.py`、`Task`、真实 LLM 调用、网络请求、新增第三方运行时依赖、git 提交操作。

## 10. 验证策略（Verification Strategy）

在项目根目录运行：

```
python -m pytest tests/test_registry.py tests/test_trace.py tests/test_eval_store.py -v
```

并确认既有测试仍通过：

```
python -m pytest -v
```

验证要点：

- 三个测试文件全部用 `tmp_path` 隔离：SQLite 库用 `Storage(tmp_path/"x.db")`，JSON 归档用 `tmp_path` 下的 `SKILLS_DIR` 语义（SkillRegistry 需支持注入归档根目录，以便测试隔离——建议构造参数化归档路径，默认 `config.SKILLS_DIR`）。
- `test_trace.py` 覆盖：≤4000 不截断、>4000 截断 + `truncated=1`、恰好边界、多步 trace 的 step 顺序与 `step_index`。
- `test_registry.py` 覆盖：register/get 往返、JSON 归档落盘、单 active 不变量（连续 promote 两版本后旧版本 deprecated、`get_active` 返回新版）、rollback 指回历史版本、`list(tags=...)` 过滤、目标版本不存在时抛异常。
- `test_eval_store.py` 覆盖：eval/experience 往返、`objective`/`rubric_scores` 反序列化为 dict、`passed` 三态保留。

**额外人工复核（非 pytest）**：

```
grep -rn "import sqlite3" evoagent/
```

结果中 `import sqlite3` 只应出现在 `evoagent/storage.py`；三个门面不得出现。
