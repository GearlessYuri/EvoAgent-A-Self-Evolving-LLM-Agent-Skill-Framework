# 事务 0003 计划（Plan）

> 规划者（Planner）产出。按 `roles/planner.md` 要求的小节组织。

---

## 1. 当前状态（Current State）

系统**存储层完整、执行层为零**。经实仓核实：

- 底座层（`0001`）：`models.py` 8 个 dataclass + 递归序列化、`config.py` 常量、`storage.py` 5 表 + 通用 CRUD。
- 存储领域门面层（`0002`）：`SkillRegistry` / `TraceStore` / `EvalStore`。其中 `SkillRegistry.list()` 返回全部 active 版本的完整 `Skill`（含 `name`/`description`/`tags`/`prompt_template`/`few_shots`/`tools`），`get_active()` 返回单版本——是检索器的现成数据源。
- `config.py` 已含 `RETRIEVAL_FALLBACK_THRESHOLD = 0.3`（§3.2 兜底阈值）。
- 全量 52 项测试通过；git `main`@`810b9d1`，工作树干净。

**缺失**：`evoagent/skills/retriever.py` 不存在；`models.py` 无 `Task` dataclass；`llm.py` 未实现。

## 2. 问题（Problem）

**正向闭环的入口缺失，且被一个设计缺口卡住。**

证据：

1. 设计 §4 的正向流第一步是 `Task → SkillRetriever.retrieve(task) → top-k Skill`，但 `SkillRetriever` 未实现——闭环 `Task → Skill Retrieval → Agent Execution → …` 的检索环节断档。
2. `SkillRetriever.retrieve()` 的入参是 `Task`，而 `models.py` **没有 `Task`**（设计 §1/§3.2/§4 引用 `Task` 却从未定义字段，仅 §11 定义了 `BenchmarkTask`）。这是 `0001/review.md` §4.3 已发现、`0002/result.md` §5.1 明确「执行层落地前需先回补」的已知缺口。
3. 设计 §3.2 强调「**检索质量是执行质量的上限**」——检索环节不落地，后续 `AgentExecutor` 无技能可执行、评估与演化也无意义。
4. `llm.py` 是另一个候选方向，但它需 provider 选型 + 引入 openai/anthropic SDK + 补 LLM 配置参数，且**当前无任何调用方**（`AgentExecutor`/`Evaluator` 均未落地）；相对而言，「简单版检索」纯标准库、零新依赖、离线可测，是更轻、更紧迫的一步。

## 3. 目标（Objective）

回补 `Task` dataclass 设计缺口，并落地执行层的第一步 `SkillRetriever`（**简单版**）：

- `evoagent/models.py`：新增 `Task` dataclass（闭合设计缺口）
- `evoagent/skills/retriever.py`：新增 `SkillRetriever`（关键词 / 余弦相似度 + tag 过滤 + 无匹配兜底）
- `tests/test_retriever.py`：`Task` 往返 + 检索正确性 + 兜底阈值 + tag 过滤测试

成果须通过 `pytest` 验证，**不引入任何第三方运行时依赖、不做真实 LLM 调用 / 网络请求 / git 操作**。

## 4. 范围（Scope）

**做（In scope）**

1. `evoagent/models.py`（**仅追加** `Task` dataclass，不动既有 8 个）：见 §5.1。
2. `evoagent/skills/retriever.py`：`SkillRetriever`（§5.2）。
3. `tests/test_retriever.py`：`Task` 往返 + 检索测试（§9/§10）。
4. （**需评审者 / 优化者裁定**，见 §7 风险 1）`docs/system_design.md`：补一段 `Task` 字段定义，使设计与代码一致。

**不做（Out of scope，明确非目标）**

- `evoagent/llm.py` 及任何 LLM provider/model/key 配置（需 SDK 依赖与 provider 选型，延后到 `AgentExecutor`/`Evaluator` 事务）。
- `AgentExecutor` / `tools.py`（执行 loop 与工具注册，属后续事务）。
- 检索**进阶版**（embedding API + numpy，§3.2「进阶版」）——本事务只做简单版。
- 检索质量度量 harness（hit@1 人工标注集，§3.2）——属 benchmark/eval 事务。
- 种子技能写入（§12 冷启动）与 default skill 的**注册**（本事务只在检索器内内置 default skill 常量，不写库）。
- 评估 / 演化 / 编排层、`cli.py`、`Benchmark`、真实 LLM 调用 / 网络请求、git 操作、新第三方运行时依赖。

## 5. 拟议变更（Proposed Changes）

| 文件 | 变更性质 |
|---|---|
| `evoagent/models.py` | **追加** `Task` dataclass（§5.1，不改既有 8 个） |
| `evoagent/skills/retriever.py` | 新建 `SkillRetriever`（§5.2） |
| `tests/test_retriever.py` | 新建（§9/§10） |
| `docs/system_design.md` | （**需裁定**，见 §7 风险 1）补 `Task` 字段定义 |

### 5.1 `Task` dataclass（回补设计缺口）

设计 §4 只暗示了 `Task` 的职责（进入 CLI/Loop 的任务载体，打 `task_source` 标签），未给出字段表。本计划**提议**的最小定义（供评审 / 优化钉死，勿视为最终结论）：

```python
@dataclass
class Task(_Serializable):
    task: str          # 任务描述（文本，供检索与执行）
    task_source: str   # "real"（真实任务）| "benchmark"（跑分）——§4 防污染标签
    task_id: str = ""  # 可选稳定标识；空则由执行层生成，用于与 ExecutionTrace.task_id 关联
```

依据：§4 步骤 1（任务文本 + `task_source` 标签）、§6 `ExecutionTrace.task_id`/`task_source`。`task_id` 是否应存在于 `Task`（还是执行时生成）属设计未明确处，留给评审者核实、优化者钉死。无论最终字段如何，`Task` 必须继承 `_Serializable` 并支持 `to_dict`/`from_dict` round-trip。

### 5.2 `SkillRetriever`（`skills/retriever.py`）

**为什么存在**：任务千变万化，需按语义挑最相关 Skill；检索质量是执行质量的上限（§3.2）。

**构造签名**（测试隔离关键）：

```python
class SkillRetriever:
    def __init__(self, registry: SkillRegistry):
        ...
```

**接口（语义，具体返回类型由优化者钉死）**：

- `retrieve(task: Task, k: int = 1) -> list[RetrievalHit]`：对全部 active Skill（`registry.list()`）按与 `task.task` 的相似度降序，返回 top-k，每项含 `(skill_id, version, score)`。
- `retrieve_top1(task: Task) -> RetrievalResult`：取 top-1；若其相似度 `< config.RETRIEVAL_FALLBACK_THRESHOLD`，改用内置 default skill 并置 `fallback=True`（对应 §3.2「无匹配兜底」与 §6 `retrieval_fallback` 标记）；否则 `fallback=False`。`RetrievalResult` 携带 `skill` / `score` / `fallback`。

**评分（简单版，纯标准库）**：对 `task.task` 文本与每个 skill 的 `description`（可含 `name` + `tags` 作补充权重）做词元化（小写 + 按非字母数字切分）后，构建词频向量并计算**余弦相似度**（§3.2「关键词 / TF-IDF + 余弦」的简单版）。算法须**确定性**、零外部依赖；是否引入 TF-IDF 加权由优化者裁定（默认先做词频 + 余弦，避免过早引入 IDF 复杂度）。

**tag 过滤（§3.2「加 tag 过滤」）**：`retrieve` 支持可选 `tags` 参数，命中时先按 tag 交集过滤候选再评分（复用 `registry.list(tags=...)` 的语义）。若评审者认为 Task 不携带 tag、该参数过早，可裁为不在本事务实现（登记为非目标）。

**default skill 兜底（§3.2）**：内置一个模块级 default `Skill` 常量（`skill_id="_default"`、通用任务 `prompt_template`、空 `few_shots`/`tools`），在低于阈值时返回。**不写入注册表**（种子 / 冷启动属 §12，后续事务）。

**分层约束**：只调 `SkillRegistry`（读）；不 `import sqlite3`、不直接 `Storage`。

## 6. 依赖（Dependencies）

- **运行时依赖**：仅标准库（`re` / `math` / `dataclasses` / `typing`）。无新增第三方。
- **测试依赖**：`pytest`（已具备）。
- **顺序依赖**：`models.py`（加 `Task`）→ `retriever.py`（依赖 `Task` + `SkillRegistry` + `config.RETRIEVAL_FALLBACK_THRESHOLD`）→ 测试。
- **对既有模块的依赖**：`SkillRegistry.list()` / `get_active()`（`0002` 已交付）；`config.RETRIEVAL_FALLBACK_THRESHOLD`（`0001` 已交付）；`Skill` / `Task`（`models.py`）。
- **前置条件**：`Storage`/`models`/三门面已就绪；本机 Python 3.13.9 + pytest 8.4.2 可用；git 已初始化（不涉及本事务）。

## 7. 风险（Risks）

| 风险 | 缓解 |
|---|---|
| 1. **`Task` 字段定义是设计缺口**，无权威字段表；若字段定错，后续 `AgentExecutor`/`Trace` 会返工 | 本事务在 plan 中给出「提议最小定义」并标注依据（§4/§6），**交评审者核实、优化者钉死**；`docs/system_design.md` 的补写是否入本事务由优化者裁定（coder.md 写范围不含 docs，若裁定不改设计文档，则登记为「设计文档仍缺 Task 定义」的已知局限） |
| 2. **检索评分算法过于复杂**（引入 TF-IDF / 向量化），违背「简单版」与「不引入复杂度」 | 默认词频 + 余弦，确定性、纯标准库；TF-IDF 权重列为可选，默认不做；评审者把关 |
| 3. **default skill 兜底机制不清**（是否写库 / 是否 `_default` 注册） | 本事务只内置常量、不写库，`retrieve_top1` 返回 `fallback=True` + default skill；种子写库（§12）显式延后 |
| 4. **空注册表 / 无 active Skill 时检索行为未定义** | 明确：`registry.list()` 为空时 `retrieve_top1` 直接走 default skill（`fallback=True`）；测试覆盖空表场景 |
| 5. **top-k 的 k 边界**（`k<1`、`k` 大于候选数） | 优化者钉死：`k<1` 报错或返回空；`k` 超出时返回全部候选（截断），测试覆盖 |
| 6. **范围蔓延**：把 embedding、`llm.py`、`AgentExecutor`、种子技能带入本事务 | §4「明确非目标」逐条列出；编码者不得越界 |
| 7. **`Task` 三态 / 序列化漏测** | `Task` 复用 `_Serializable`，`test_retriever.py` 含 `Task` round-trip 用例（含 `task_id` 默认空串） |

## 8. 实施顺序（Implementation Order）

1. `evoagent/models.py` 追加 `Task` dataclass（继承 `_Serializable`）。
2. 实现 `evoagent/skills/retriever.py`：词元化 / 词频 + 余弦 → `retrieve` → `retrieve_top1`（阈值 + default 兜底）→（可选）tag 过滤。
3. 编写 `tests/test_retriever.py`（`Task` 往返 + 检索正确性 + 兜底 + tag + 边界）。
4. （若裁定）补 `docs/system_design.md` 的 `Task` 定义。
5. 运行验证命令（§10），确认全绿。

## 9. 验收标准（Acceptance Criteria）

1. **`Task`**：`models.py` 新增 `Task` dataclass，继承 `_Serializable`，`to_dict`/`from_dict` round-trip 字段不丢；既有 8 个 dataclass 不动。
2. **包结构**：`evoagent/skills/retriever.py` 存在且 `import evoagent.skills.retriever` 成功。
3. **分层约束**：`SkillRetriever` 只调 `SkillRegistry`（读），不 `import sqlite3`、不直接操作 `Storage`（grep 验证：`import sqlite3` 仍只出现在 `storage.py`）。
4. **检索正确性**：注册若干 `description`/`tags` 不同的 Skill 后，`retrieve` 能把语义最相关的 active Skill 排第一，返回 `(skill_id, version, score)` 且分数降序、确定可复现。
5. **兜底**：`retrieve_top1` 在 top-1 相似度 `< RETRIEVAL_FALLBACK_THRESHOLD` 或空注册表时，返回内置 default skill 且 `fallback=True`；否则返回命中 skill 且 `fallback=False`。
6. **tag 过滤**（若实现）：`retrieve(tags=...)` 只返回与给定 tag 有交集的 skill。
7. **不越界**：不含 embedding、`llm.py`、`AgentExecutor`、种子技能写库、真实 LLM 调用 / 网络请求、新增第三方运行时依赖、git 操作。
8. **测试**：`tests/test_retriever.py` 全部 PASSED，既有 52 项测试无回归（全量 `python -m pytest` 全绿），无失败、无跳过掩盖。

## 10. 验证策略（Verification Strategy）

在项目根目录运行：

```
python -m pytest tests/test_retriever.py -v
```

并确认全量回归：

```
python -m pytest -v
```

**用例要求（`test_retriever.py`，全部用 `tmp_path` 注入 `Storage` + `SkillRegistry`）：**

- `Task` round-trip：`task`/`task_source` 字段保留；`task_id` 默认空串 round-trip 后仍为空串。
- 检索正确性：注册 2–3 个 `description` 明显不同的 active Skill，断言 `retrieve(task, k=1)` 返回语义最相关者、分数降序、可复现。
- 兜底：构造一个与所有 Skill 都无关的 `task`（或空注册表），断言 `retrieve_top1` 返回 default skill 且 `fallback=True`；相关任务断言 `fallback=False`。
- tag 过滤（若实现）：`retrieve(tags=[...])` 只返回交集命中者。
- 边界：`k<1`、`k` 大于候选数、空注册表。

**额外人工复核（非 pytest）**：

```
grep -rn "import sqlite3" evoagent/
```

真实 `import sqlite3` 语句只应出现在 `evoagent/storage.py`；`retriever.py` 不得出现、也不得访问 `storage.conn`。
