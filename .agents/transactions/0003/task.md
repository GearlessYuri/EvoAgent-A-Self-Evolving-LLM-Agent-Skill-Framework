# 事务 0003 最终任务规格说明（Task）

> 优化者（Optimizer）产出。本文件是编码者实现的**唯一依据**，自包含：编码者无需阅读 `plan.md` / `review.md` 即可执行。
> 依据：`plan.md` + `review.md` + `docs/system_design.md` + 事务 `0001`/`0002` 落地后的实仓源码 + 实仓核实 + 用户特别裁定。
>
> 说明：本仓库事务文件实际位于 `.agents/transactions/0003/`（顶层 `transactions/` 不存在）。下文路径均以 `.agents/transactions/0003/` 为准。

---

## 1. 目标（Objective）

回补 `Task` dataclass 设计缺口，并落地执行层第一步 `SkillRetriever`（**简单版**）：

- `evoagent/models.py`：新增 `Task` dataclass（闭合设计缺口）
- `evoagent/skills/retriever.py`：新增 `SkillRetriever`（关键词 / 余弦相似度 + tag 过滤 + 无匹配兜底）
- `tests/test_retriever.py`：检索正确性 + 兜底阈值 + tag 过滤 + 边界测试
- 同步更新 `tests/test_models.py`（`Task` 入 `ALL_DATACLASSES`、测试改名、`Task` round-trip 移入）与 `models.py` docstring

成果须通过 `pytest` 验证；不引入任何第三方运行时依赖、不做真实 LLM 调用 / 网络请求；除收尾提交（见 §10）外不做任何 git 操作。

## 2. 上下文（Context）

- 事务 `0001`（底座层）与 `0002`（存储领域门面层）已落地，全量 52 项测试通过，git `main`@`810b9d1`。
- 系统**存储层完整、执行层为零**：正向闭环 `Task → Skill Retrieval → Agent Execution → …` 缺检索入口。
- **实仓现状（已核实）**：
  - `models.py` 含 **8 个** dataclass（`FewShot`/`ToolSpec`/`Skill`/`TraceStep`/`ExecutionTrace`/`EvaluationResult`/`Experience`/`BenchmarkTask`），**无 `Task`**；模块 docstring 写「§5–§11 的 8 个 dataclass」。
  - `evoagent/skills/` 下只有 `__init__.py` 与 `registry.py`，**无 `retriever.py`**。
  - `SkillRegistry.list(tags=None) -> list[Skill]`（返回全部 active 版本、按 `skill_id` 升序、完整 `Skill` 含 `name`/`description`/`tags`/`prompt_template`/`few_shots`/`tools`；`tags` 非空时按**交集**过滤）；`get_active(skill_id) -> Skill | None`；`get(skill_id, version) -> Skill | None`。这三者是检索器的现成数据源。
  - `config.RETRIEVAL_FALLBACK_THRESHOLD = 0.3` 已存在，本事务直接复用，**不新增配置常量**。
  - `llm.py` 未实现；简单版检索纯标准库、**不需要 LLM**。
- **设计分层约束（§2）**：上层只调下层；`storage.py` 是全项目唯一 `import sqlite3`/写 SQL 处。`SkillRetriever` 只读 `SkillRegistry`，**不得** `import sqlite3`、**不得**直接操作 `Storage`。
- **环境**：Python 3.13.9（≥3.10）、pytest 8.4.2。

## 3. 范围（Scope）

**做（In scope）**

1. `evoagent/models.py`：**仅追加** `Task` dataclass（§4.1），并更新模块 docstring（§4.1）。既有 8 个 dataclass 及 `_Serializable` 机制不动。
2. `evoagent/skills/retriever.py`：`SkillRetriever`（§4.2）。
3. `tests/test_retriever.py`（§4.3）。
4. `tests/test_models.py`：`Task` 加入 `ALL_DATACLASSES`、`test_eight_dataclasses_defined` 改名、`Task` round-trip 移入（§4.3）。

**不做（Out of scope，明确非目标）** —— 详见 §11。

## 4. 需求（Requirements）

### 4.1 「已确认的 Task 定义」（用户拍板，编码者不得再改）

`evoagent/models.py` 追加如下 dataclass（置于 `Skill` 数据结构定义之前，加注释 `# ── §4 Task 数据结构（设计缺口回补） ──`）：

```python
@dataclasses.dataclass
class Task(_Serializable):
    task: str          # 任务描述（文本，供检索与执行）
    task_source: str   # "real"（真实任务）| "benchmark"（跑分）——§4 防污染标签
```

**理由（已确认裁定）**：

- `task`、`task_source` 有设计依据：§4 正向流步骤 1（任务文本 + `task_source` 来源标签，`real`/`benchmark`）、§6 `ExecutionTrace.task_source`、§11 `BenchmarkTask.task` 类比。
- **`Task` 不含 `task_id` 字段**（评审 §4.1 方案 (b)，用户拍板）：设计 §4 只给 `Task` 打 `task_source` 标签、从未说 `Task` 携带 id；`ExecutionTrace.task_id` 由 `AgentExecutor` 在写 trace 时生成。**本事务不实现该生成逻辑**，只锁定「`Task` 定义不含 `task_id`」这一事实，避免后续事务再翻案。
- `Task` 继承 `_Serializable`，天然获得 `to_dict`/`from_dict` 双向递归序列化（字段为两个 `str`，无嵌套，round-trip 直通）。

**`models.py` docstring 更新（消除「8 个」失准）**：将模块 docstring 首段中「系统设计 §5–§11 的 8 个 dataclass」改为「9 个 dataclass：`Task`（§4 回补，设计文档尚未补字段定义）+ 系统设计 §5–§11 的 8 个」，其余措辞保持原意。

### 4.2 `SkillRetriever`（`evoagent/skills/retriever.py`）

**为什么存在**：任务千变万化，需按语义挑最相关 Skill；检索质量是执行质量的上限（§3.2）。

**模块级常量（内置兜底技能，不写库）**：

```python
DEFAULT_SKILL: Skill = Skill(
    skill_id="_default",
    name="Default",
    description="通用任务兜底技能",
    version="0.0.0",
    tags=[],
    prompt_template="你是一个通用助手，请完成以下任务：{task}",
    few_shots=[],
    tools=[],
    status="active",
    parent_version="",
    change_log="",
    metrics={},
    created_at="",
    updated_at="",
)
```

> 仅作为检索器内置常量；**不**写入注册表、**不**落 JSON 归档（种子技能 / 冷启动写库属 §12，后续事务）。

**轻量结果类型（`retrieval.py` 内 `typing.NamedTuple`，不进 `models.py`）**：

```python
class RetrievalHit(typing.NamedTuple):
    skill_id: str
    version: str
    score: float        # 余弦相似度，0~1

class RetrievalResult(typing.NamedTuple):
    skill: Skill        # 命中技能 或 DEFAULT_SKILL（兜底时）
    score: float        # 命中为其余弦分数；兜底为 0.0
    fallback: bool      # True=走 default 兜底；False=正常命中
```

> 这两个类型是检索的**瞬时返回载体**，不是跨层持久化「合同」，故放 `retriever.py` 而非 `models.py`（避免引入第 10/11 个 dataclass）。

**构造签名**：

```python
class SkillRetriever:
    def __init__(self, registry: SkillRegistry):
        self.registry = registry
```

**方法（签名 + 语义）**：

| 方法 | 语义 |
|---|---|
| `retrieve(task: Task, k: int = 1, tags: list[str] \| None = None) -> list[RetrievalHit]` | 对候选 active Skill 按与 `task.task` 的余弦相似度**降序**排序，返回 top-k。**无兜底**、**不返回 default skill**。候选来源 `self.registry.list(tags=tags)`（`tags` 非空时即按交集过滤，复用 `0002` 语义）。`k < 1` → 抛 `ValueError`；`k` 大于候选数 → 返回全部候选；空注册表/无匹配 → 返回 `[]`。排序键 `(-score, skill_id)`（确定性）。 |
| `retrieve_top1(task: Task) -> RetrievalResult` | 取 top-1 + 兜底。内部调用 `retrieve(task, k=1)`；若命中且 `score >= config.RETRIEVAL_FALLBACK_THRESHOLD`，用 `registry.get(skill_id, version)` 取回完整 `Skill`，返回 `RetrievalResult(skill, score, fallback=False)`；否则返回 `RetrievalResult(DEFAULT_SKILL, 0.0, fallback=True)`（含空注册表、无匹配、score 低于阈值三种情况）。 |

**评分算法（简单版，纯标准库、确定性；已裁定）**：

- **词元化**：`re.findall(r"\w+", text.lower())`（小写 + 按非字母数字切分；`\w` 含 Unicode，中英文均可）。模块级 helper `_tokenize(text) -> list[str]`。
- **词频向量**：`_term_frequency(tokens) -> dict[str, int]`（`collections.Counter`）。
- **余弦相似度** `_cosine_similarity(a, b) -> float`：
  - `dot = sum(a[t] * b[t] for t in a if t in b)`；`norm = sqrt(sum(v*v for v in d.values()))`。
  - **除零边界（已裁定）**：`norm_a == 0` 或 `norm_b == 0`（任务文本为空、skill `description` 为空、或二者无共享 token）→ 返回 **`0.0`**，不抛异常。
- **评分信号（已裁定）**：仅用 `skill.description` 与 `task.task` 计算余弦；**不**纳入 `name`/`tags`（设计 §3.2 只写「description 供检索」）。**词频 + 余弦，不做 TF-IDF**（简单版，符合 §14 最小依赖）。
- 对每个候选 `Skill` 计算 `score = _cosine_similarity(_term_frequency(_tokenize(task.task)), _term_frequency(_tokenize(skill.description)))`，产出 `RetrievalHit(skill.skill_id, skill.version, score)`。

**分层约束**：只 `import` 并调用 `SkillRegistry`（读）；**不** `import sqlite3`、**不** `import Storage`、**不**访问 `storage.conn`。

### 4.3 测试要求

- `tests/test_models.py`（**修改**，锁定「9 个 dataclass」）：
  - 在 `ALL_DATACLASSES` 末尾追加 `Task`（导入 `Task`）。
  - 将 `test_eight_dataclasses_defined` **改名**为 `test_all_dataclasses_defined`，断言 `len(ALL_DATACLASSES) == 9`。
  - 新增 `test_task_roundtrip`：构造 `Task(task="...", task_source="real")`，断言 `Task.from_dict(obj.to_dict()) == obj` 且 `task`/`task_source` 字段保留。（`Task` round-trip **移入** `test_models.py`，与其余 8 个 dataclass 的约定一致，不放 `test_retriever.py`。）
- `tests/test_retriever.py`（**新建**）：见 §10。

## 5. 约束（Constraints）

1. **语言 / 运行时**：Python 3.10+（本机 3.13.9）；类型注解统一 `X | None`（项目既有约定）。
2. **运行时依赖**：仅标准库（`re`/`math`/`collections`/`dataclasses`/`typing`）。**不得**引入第三方运行时依赖。唯一第三方依赖是开发期 `pytest`。
3. **分层与 SQL 唯一性**：`storage.py` 仍是全项目唯一 `import sqlite3`/写 SQL 的模块；`SkillRetriever` 只读 `SkillRegistry`，不 `import sqlite3`、不直接 `Storage`。
4. **不改既有**：`models.py` 仅追加 `Task` + 改 docstring（8 个 dataclass 与 `_Serializable` 不动）；**不改** `config.py`（复用既有 `RETRIEVAL_FALLBACK_THRESHOLD`，不加常量）；**不改** `registry.py`/`storage.py`/`trace.py`/`store.py`。
5. **不越界**：不实现 `llm.py`、`AgentExecutor`、`tools.py`、检索进阶版（embedding）、检索质量度量 harness、种子技能写库、真实 LLM 调用 / 网络请求、新第三方运行时依赖。
6. **命名**：类 `PascalCase`、方法/函数 `snake_case`、常量 `UPPER_SNAKE_CASE`；`Task` 字段名与 §4.1 完全一致。
7. **确定性**：`retrieve` 排序键 `(-score, skill_id)`；词元化 / 词频 / 余弦均为纯函数，同输入必同输出。
8. **错误处理**：本事务仅抛标准异常（`ValueError`），不自定义异常类。

## 6. 相关文件 / 模块（Relevant Files / Modules）

**本事务新建：**

| 文件 | 内容 |
|---|---|
| `evoagent/skills/retriever.py` | `SkillRetriever` + `DEFAULT_SKILL` + `RetrievalHit`/`RetrievalResult`（§4.2） |
| `tests/test_retriever.py` | §4.3/§10 |

**本事务修改：**

| 文件 | 变更 |
|---|---|
| `evoagent/models.py` | 追加 `Task` dataclass + 更新 docstring（§4.1） |
| `tests/test_models.py` | `Task` 入 `ALL_DATACLASSES`、测试改名、`Task` round-trip 移入（§4.3） |

**只读参照（不修改）：** `evoagent/config.py`、`evoagent/storage.py`、`evoagent/skills/registry.py`、`evoagent/execution/trace.py`、`evoagent/eval/store.py`、`docs/system_design.md`（**本事务不修改，见 §9.10**）、`.agents/transactions/0001/`、`.agents/transactions/0002/`、`.agents/transactions/0003/` 的 `context.md`/`plan.md`/`review.md`（历史不可改）。

## 7. 推荐的实现策略（Recommended Implementation Strategy）

依赖关系：`models.py`（加 `Task` + docstring）→ `retriever.py`（依赖 `Task` + `SkillRegistry` + `config.RETRIEVAL_FALLBACK_THRESHOLD`）→ `test_models.py`（更新）→ `test_retriever.py` → 验证 → 收尾提交。

1. **`models.py`**：追加 `Task` dataclass（§4.1），更新 docstring「8 个」→「9 个」。
2. **`retriever.py`**：先写 `_tokenize` / `_term_frequency` / `_cosine_similarity` 三个纯函数，再写 `DEFAULT_SKILL`、`RetrievalHit`、`RetrievalResult`，最后 `SkillRetriever.retrieve` → `retrieve_top1`。
3. **`test_models.py`**：`Task` 入 `ALL_DATACLASSES`、改名 `test_all_dataclasses_defined`（`len == 9`）、加 `test_task_roundtrip`。
4. **`test_retriever.py`**：按 §10 用例清单写。
5. **验证**：运行 §10 命令，确认全绿。
6. **收尾提交**：按 §10 末尾执行 git 提交。

**实现要点**：`retrieve` 直接 `registry.list(tags=tags)` 拿候选（已按 `skill_id` 排序），逐个算 `description` 余弦分数，`sort(key=lambda h: (-h.score, h.skill_id))` 后截取 `[:k]`；`retrieve_top1` 复用 `retrieve(task, k=1)` 再判断阈值。

## 8. 预期变更（Expected Changes）

| 文件 | 变更性质 |
|---|---|
| `evoagent/models.py` | 修改：追加 `Task` + docstring 更新（既有 8 个 dataclass 不动） |
| `evoagent/skills/retriever.py` | 新建 |
| `tests/test_models.py` | 修改：`Task` 入 `ALL_DATACLASSES` + 测试改名 + 加 `test_task_roundtrip` |
| `tests/test_retriever.py` | 新建 |

（不修改 `config.py`、`storage.py`、`registry.py`、`trace.py`、`store.py`、`__init__.py`、`pyproject.toml`、`requirements.txt`、`.gitignore`、`docs/system_design.md`；不产生 `data/` 运行时文件到源码树。）

## 9. 验收标准（Acceptance Criteria）

1. **`Task`**：`models.py` 新增 `Task` dataclass，字段恰为 `task: str`、`task_source: str`（**无 `task_id`**），继承 `_Serializable`；`to_dict`/`from_dict` round-trip 字段不丢；既有 8 个 dataclass 不动。
2. **dataclass 计数**：`models.py` 全模块共 **9 个** dataclass；`test_models.py` 的 `test_all_dataclasses_defined` 断言 `len == 9`，`Task` round-trip 在 `test_models.py` 内且通过。
3. **docstring**：`models.py` 模块 docstring 已更新为「9 个 dataclass（`Task` + §5–§11 的 8 个）」，不再声称「8 个」。
4. **包结构**：`evoagent/skills/retriever.py` 存在，`import evoagent.skills.retriever` 成功；`SkillRetriever`/`DEFAULT_SKILL`/`RetrievalHit`/`RetrievalResult` 均在 `retriever.py` 内（`models.py` 只新增 `Task`，无 `RetrievalHit`/`RetrievalResult`）。
5. **分层约束**：`SkillRetriever` 只读 `SkillRegistry`，不 `import sqlite3`、不直接操作 `Storage`（grep 验证：真实 `import sqlite3` 语句仍只出现在 `storage.py`）。
6. **检索正确性**：注册若干 `description` 明显不同的 active Skill 后，`retrieve` 能把语义最相关的排第一，返回 `RetrievalHit`（`skill_id`/`version`/`score`）且分数降序、确定可复现。
7. **兜底**：`retrieve_top1` 在 top-1 `score < RETRIEVAL_FALLBACK_THRESHOLD`、或空注册表/无 active 时，返回 `DEFAULT_SKILL` 且 `fallback=True`、`score==0.0`；相关任务返回命中 skill 且 `fallback=False`。
8. **tag 过滤**：`retrieve(tags=...)` 只对与给定 tag 有**交集**（至少一个匹配）的 skill 评分返回。
9. **边界**：`k < 1` 抛 `ValueError`；`k` 大于候选数返回全部；空 `description`/零共享 token 不崩溃（分数按 0.0 计）。
10. **docs 不修改 + 登记**：`docs/system_design.md` **未被修改**；「设计文档仍缺 `Task` 字段定义，已由事务 0003 的 `Task` 实现补齐，文档回补待后续事务」已登记进 `project_state.md` 的已知局限（优化者在优化阶段已完成，见 §10）。
11. **测试**：`tests/test_retriever.py` 与更新后的 `test_models.py` 全部 PASSED，全量 `python -m pytest` 全绿（既有测试无回归），无失败、无跳过掩盖。
12. **无越界**：不含 `llm.py`、`AgentExecutor`、`tools.py`、embedding 检索、检索质量度量 harness、种子技能写库、真实 LLM 调用 / 网络请求、新增第三方运行时依赖。

## 10. 验证策略（Verification Strategy）

在项目根目录运行：

```
python -m pytest tests/test_models.py tests/test_retriever.py -v
```

并确认全量回归：

```
python -m pytest -v
```

**用例要求：**

- `test_models.py`（修改后）：`test_all_dataclasses_defined`（`len == 9`）；`test_task_roundtrip`（`Task.from_dict(Task(...).to_dict()) == 原对象`，`task`/`task_source` 保留）。
- `test_retriever.py`（全部用 `tmp_path` 注入 `Storage` + `SkillRegistry`，`SkillRetriever(registry)`）：
  - **检索正确性**：注册 2–3 个 `description` 含明显不同英文关键词的 active Skill（例如 `code-review`→"review and critique source code"、`text-summarize`→"summarize long text documents"），`retrieve(task, k=1)` 返回与任务关键词最相关者，且分数降序、可复现（同输入跑两次结果一致）。
  - **兜底**：用一个与所有 skill `description` 都无共享 token 的任务（或空注册表），断言 `retrieve_top1` 返回 `DEFAULT_SKILL` 且 `fallback=True`、`score==0.0`；用相关任务断言 `fallback=False` 且返回命中 skill。
  - **tag 过滤**：注册带不同 tags 的 skill，`retrieve(task, tags=["code"])` 只返回 tag 交集命中者。
  - **边界**：`retrieve(task, k=0)` 抛 `ValueError`；`k=10` 而候选仅 3 个时返回 3 个；空注册表 `retrieve` 返回 `[]`；某 skill `description=""` 时该 skill 分数为 0.0、不崩溃。
  - **RetrievalHit/Result 形态**：断言 `retrieve` 返回的元素为 `RetrievalHit`（有 `skill_id`/`version`/`score` 属性）、`retrieve_top1` 返回 `RetrievalResult`（有 `skill`/`score`/`fallback` 属性）。

**额外人工复核（非 pytest，编码者确认并记入 `execution.md`）：**

```
grep -rn "import sqlite3" evoagent/
```

真实 `import sqlite3` 语句**只**应出现在 `evoagent/storage.py`；`retriever.py` 不得出现、也不得访问 `storage.conn`。另确认 `docs/system_design.md` 无 diff（`git status` 中不应出现该文件）。

**收尾提交（用户已授权，必须执行）**：

全部验证通过后，Coder **一次性提交全部变更**：

```
git add -A && git commit -m "0003: 回补 Task 数据契约并落地 SkillRetriever 简单版检索"
```

- 提交信息**首行**必须以 `0003: ` 开头 + 一句目标概括（上例为建议措辞，编码者可用同义的简洁一句话）。
- **不 push、不 amend、不建分支、不 force-push**（仅本地提交）。
- 提交前确认收尾时对 `project_state.md` 已知局限的更新已写入（见下）。
- **把提交哈希记入 `result.md`**（`git rev-parse HEAD` 取哈希）。

**对 `project_state.md` 已知局限的登记（用户裁定，已由优化者在优化阶段完成）**：`project_state.md`「已知局限」中 Task 相关一行已更新为「`docs/system_design.md` 仍缺 `Task` dataclass 字段定义（事务 `0003` 在 `models.py` 代码中补齐，设计文档回补待后续事务）」。编码者**无需再改**，提交前仅确认其已存在即可。

## 11. 明确的非目标（Explicit Non-Goals）

本任务**不做**以下任何事（防止范围蔓延）：

1. **`evoagent/llm.py`** 及任何 LLM provider/model/key 配置。
2. **`AgentExecutor` / `tools.py`**（执行 loop、工具注册，属后续事务）；**不实现 `Task.task_id` 的生成逻辑**（`ExecutionTrace.task_id` 由未来 `AgentExecutor` 写 trace 时生成，本事务只锁定 `Task` 定义不含 `task_id`）。
3. **检索进阶版**（embedding API + numpy，§3.2「进阶版」）与**检索质量度量 harness**（hit@1 人工标注集）。
4. **种子技能写入 / default skill 注册**（§12 冷启动）：本事务只在检索器内置 `DEFAULT_SKILL` 常量，不写库、不落 JSON。
5. **评估 / 演化 / 编排层、`cli.py`、`Benchmark`**。
6. **修改 `docs/system_design.md`**：本事务不修改该只读设计文档（`Task` 字段回补仅落到 `models.py`，文档回补待后续事务，已登记已知局限）。
7. **评分信号纳入 `name`/`tags`**：仅用 `description`；**不做 TF-IDF**（词频 + 余弦）。
8. **新第三方运行时依赖**（openai / anthropic / numpy 等）。
9. **真实 LLM 调用 / 网络请求**。
10. **除收尾提交（§10）外的任何 git 操作**：不 push、不 amend、不建分支、不 force-push、不拆多次提交。

---

### 已裁定决定（记录以备查；无「实现前需确认」的开放问题）

| 裁定点 | 结论 |
|---|---|
| `Task` 字段 | **`task: str` + `task_source: str`，无 `task_id`**（用户拍板，评审 §4.1 方案 b） |
| `docs/system_design.md` | **不修改**；在 `task.md` 验收标准 + `project_state.md` 已知局限登记（用户拍板） |
| dataclass 计数漂移 | `Task` 入 `ALL_DATACLASSES`（9 个）、测试改名 `test_all_dataclasses_defined`、`Task` round-trip 移入 `test_models.py`、`models.py` docstring 更新（评审 §2.1 方案 a） |
| `RetrievalHit`/`RetrievalResult` | `retriever.py` 内 `typing.NamedTuple`，**不进 `models.py`**（评审 §3.1） |
| `retrieve`/`retrieve_top1` 拆分 | `retrieve`=top-k 排序、无兜底；`retrieve_top1`=top-1 + 阈值兜底（内部调 `retrieve(task, k=1)`）（评审 §3.4） |
| tag 过滤 | **保留**；`retrieve(tags=...)` 可选参数，**交集**语义，复用 `registry.list(tags=...)`（评审 §3.3） |
| 评分信号 | **仅 `description`**，不含 `name`/`tags`（评审 §3.5） |
| 评分算法 | 词频 + 余弦（**不做 TF-IDF**）；零范数/空 `description`/无共享 token → **0.0**，不抛异常（评审 §3.2） |
| `k` 边界 | `k < 1` → `ValueError`；`k` 超候选数 → 返回全部；空注册表 → `[]` |
| 兜底结果分数 | `fallback=True` 时 `score == 0.0` |
