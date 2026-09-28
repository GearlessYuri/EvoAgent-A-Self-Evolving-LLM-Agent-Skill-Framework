# 事务 0003 上下文（Context）

> 本文件是事务开始时的「时间胶囊」，记录当时的项目状态与触发背景，使本事务脱离当前项目状态也可被独立理解。
> 按 `workflow/transaction_protocol.md` 维护。

- 事务 ID：`0003`
- 创建日期：2026-09-28
- 事务性质：第三个开发事务（承接已关闭的 `0001` 底座层与 `0002` 存储领域门面层）

---

## 1. 触发原因

`0001`（底座层）与 `0002`（存储领域门面层）已落地并通过全量 52 项测试。当前系统的**存储层完整**，但**执行层尚未开始**——系统设计的正向闭环（`Task → Skill Retrieval → Agent Execution → …`）缺了入口。

`0002/result.md` 的「后续问题」与「建议的下一步」指出：下一步应进入**执行层**，而执行层的第一步 `SkillRetriever` 依赖一个**设计缺口**——`docs/system_design.md` 全文引用 `Task`（§1/§3.2/§4）却从未定义其字段（仅 §11 定义了 `BenchmarkTask`）。因此本事务在落地 `SkillRetriever` 的同时，必须**回补 `Task` dataclass 定义**（作为拟议变更提出，由后续流程批准）。

## 2. 事务开始时的项目状态快照

摘自当时的 `state/project_state.md`：

- **项目标识 / 用途**：EvoAgent —— 基于执行反馈的自演进 Agent Skill 平台。
- **架构摘要**：分层架构（§2）。已落地**底座层**（`models.py` 8 个 dataclass、`config.py` 常量、`storage.py` 5 表 + 通用 CRUD）与**存储领域门面层**（`SkillRegistry` / `TraceStore` / `EvalStore`）。尚未落地 `llm.py`、执行 / 评估 / 演化 / 编排层、`cli.py`。
- **已实现能力**：可导入包、8 数据契约、SQLite 底座、三门面、52 项单元测试全部通过。
- **当前开发阶段**：底座层与门面层已落地并通过 `pytest`（`0001`、`0002` 已关闭）；上层尚未开始。
- **已知局限**：系统设计未给出 `Task` dataclass 字段定义（仅 `BenchmarkTask` 有定义）；`pyproject.toml` 未含子包（`packages=["evoagent"]`）；`metrics` 增量回写未实现。
- **当前事务**：无（`0002` 已关闭，下一个 ID 为 `0003`）。

## 3. 经核实的实际仓库现状（以实际代码 / 文件为准）

**git 状态**：`main` 分支，HEAD = `810b9d1`「事务 0002：存储领域门面层（SkillRegistry/TraceStore/EvalStore）」（其父为 `78d505e` 初始提交）；`git status --short` 为空（工作树干净）。

**源码结构**（`evoagent/`）：

```
evoagent/__init__.py            # __version__ = "0.1.0"
evoagent/models.py              # 8 个 dataclass（无 Task）+ _Serializable 递归序列化
evoagent/config.py              # DATA_DIR/DB_PATH/SKILLS_DIR + 阈值权重 + TRACE_CONTENT_MAX_CHARS；无 LLM 参数
evoagent/storage.py             # Storage：WAL + 5 表 + 参数化 CRUD（唯一 import sqlite3）
evoagent/skills/__init__.py     # 空包
evoagent/skills/registry.py     # SkillRegistry（register/get/get_active/list/promote/rollback/deprecate + JSON 归档）
evoagent/execution/__init__.py  # 空包
evoagent/execution/trace.py     # TraceStore（save/get/list + 4000 截断）
evoagent/eval/__init__.py       # 空包
evoagent/eval/store.py          # EvalStore（save_eval/get_eval/list_evals/save_experience/list_experiences）
```

**与本事务直接相关的关键事实（已核实）**：

1. `models.py` 含 **8 个** dataclass（`FewShot`/`ToolSpec`/`Skill`/`TraceStep`/`ExecutionTrace`/`EvaluationResult`/`Experience`/`BenchmarkTask`），**无 `Task`**。
2. `evoagent/skills/` 下**只有** `__init__.py` 与 `registry.py`，**无 `retriever.py`**。
3. `SkillRegistry.list(tags=None) -> list[Skill]` 返回**全部 active 版本**的完整 `Skill` 对象（含 `name`/`description`/`tags`/`prompt_template`/`few_shots`/`tools`）；`get_active(skill_id) -> Skill | None`。二者是检索器的现成数据源。
4. `config.py` 已含 `RETRIEVAL_FALLBACK_THRESHOLD = 0.3`（§3.2 兜底阈值），本事务可直接复用，**无需新增配置常量**。
5. `llm.py` 尚未实现；`SkillRetriever` 的「简单版」（关键词 / TF-IDF + 余弦）**不需要 LLM**，可纯标准库实现。

## 4. 本事务将引用的系统设计章节

- §2 分层视图（执行层 `SkillRetriever` · `AgentExecutor` 位于存储层之上）
- §3.2 `SkillRetriever`：`Task → top-k (skill_id, version, score)`，简单版关键词 / TF-IDF + 余弦，tag 过滤，无匹配兜底（`RETRIEVAL_FALLBACK_THRESHOLD`）+ `retrieval_fallback` 标记，检索质量度量（hit@1）
- §4 正向流：`Task` 进入 CLI/Loop 打 `task_source` 标签；`SkillRetriever.retrieve(task) → top-1 active Skill`，低于阈值走 default skill
- §11 `BenchmarkTask`（对照：`Task` 与其的差异——运行时任务载体 vs 跑分题目）
- §13 目录结构（`skills/retriever.py`、`tests/test_retriever.py`）
- §14 技术选型（简单版检索不引入向量数据库）

## 5. 已知的设计缺口（本事务处理）

**`Task` dataclass 字段定义缺失**：设计全文引用 `Task`（§1/§3.2/§4）却从未给出字段定义（仅 §11 `BenchmarkTask` 有）。§4 只暗示了 `Task` 至少需携带**任务文本**与 **`task_source` 标签**（`real` / `benchmark`，防污染），§6 `ExecutionTrace` 另有 `task_id`。本事务在落地 `SkillRetriever`（其入参即 `Task`）时必须回补该定义——以 `plan.md` 的「拟议变更」提出，由评审 / 优化流程批准后落地。
