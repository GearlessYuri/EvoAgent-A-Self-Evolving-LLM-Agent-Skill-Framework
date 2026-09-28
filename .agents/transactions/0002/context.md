# 事务 0002 上下文（Context）

> 本文件是事务开始时的「时间胶囊」，记录当时的项目状态与触发背景，使本事务脱离当前项目状态也可被独立理解。
> 按 `workflow/transaction_protocol.md` 维护。

- 事务 ID：`0002`
- 创建日期：2026-09-28
- 事务性质：第二个开发事务（承接已关闭的 `0001` 底座层）

---

## 1. 触发原因

事务 `0001` 已落地系统设计的**底座层**（`models.py` 数据契约 / `config.py` 配置 / `storage.py` 存储底座），26 项测试全部通过。但存储层**只完成了通用底座**，尚缺三个**领域门面**：

- `SkillRegistry`（技能版本管理 + active 指针 + 内容归档）
- `TraceStore`（执行轨迹写入 / 查询 + 4000 字符截断）
- `EvalStore`（评估结果 / 经验读写）

`0001/result.md` 的「后续问题」与「建议的下一步」明确指出：下一步应落地**存储领域门面层**，并在门面内补齐两处被 `0001` 显式后置的逻辑——**JSON 字段反序列化**（`query` 现以 TEXT 返回原始 JSON 字符串）与 **`trace_steps.content` 4000 字符截断 + `truncated` 置位**。

## 2. 事务开始时的项目状态快照

摘自当时的 `state/project_state.md`：

- **项目标识 / 用途**：EvoAgent —— 基于执行反馈的自演进 Agent Skill 平台（`docs/system_design.md` §0）。
- **架构摘要**：分层架构（§2），已落地**底座层**；`models.py` 8 个 dataclass + 递归序列化、`config.py` 常量、`storage.py` 5 表 + 通用 CRUD。尚未落地 `llm.py`、存储门面、执行 / 评估 / 演化 / 编排层、`cli.py`。
- **已实现能力**：可导入包、8 数据契约、SQLite 底座（WAL + 5 表 + 参数化 CRUD）、26 项单元测试通过。
- **当前开发阶段**：底座层已落地并通过 `pytest`；上层模块尚未开始。
- **已知局限**：通用 `Storage.query` 不自动反序列化 JSON 字段；系统设计未给出 `Task` dataclass 定义；Skill JSON 归档依赖 git（当时未初始化）。
- **当前事务**：无（`0001` 已关闭，下一个 ID 为 `0002`）。

## 3. 经核实的实际仓库现状（以实际代码 / 文件为准）

**git 状态**：仓库为 git 仓库（`main` 分支），HEAD = `78d505e`「初始提交：系统设计文档、.agents 多智能体工作区、底座层（事务 0001）」；`git status --short` 为空（工作树干净）。`.pytest_cache/`、`__pycache__/` 在磁盘上存在但被 `.gitignore` 忽略。

**实际文件清单**（`find` 结果，排除 `.git`）：

```
.agents/（roles / workflow / state / transactions/0001 全量、transactions/README）
docs/system_design.md
.gitignore
pyproject.toml            # 无运行时第三方依赖
requirements.txt          # 仅 pytest
evoagent/__init__.py      # __version__ = "0.1.0"
evoagent/models.py        # 8 个 dataclass + _Serializable 递归序列化
evoagent/config.py        # DATA_DIR/DB_PATH + 4 阈值/权重 + WAL 开关
evoagent/storage.py       # Storage：connect(WAL)/init_schema(5 表)/CRUD
tests/test_models.py
tests/test_storage.py
```

**与 0002 直接相关的关键事实（已核实）**：

1. `storage.py` 的 `query()` 对 JSON 列（`metrics` / `usage` / `objective` / `rubric_scores`）**以原始 TEXT 返回**，不自动 `json.loads`；`insert`/`update` 侧的 `_serialize_value` 已对 dict/list 做 `json.dumps`。
2. `trace_steps` 表已含 `truncated INTEGER NOT NULL DEFAULT 0` 列，但 **4000 字符截断 + 置位逻辑未实现**（设计 §6 明确要求，`0001` 裁定归属 `TraceStore`）。
3. `skills` 表列：`skill_id, version, status, parent_version, change_log, metrics, created_at, updated_at`——**没有 `name` / `description` / `tags` 列**（详见 §4 设计缺口）。
4. `config.py` 仅含 `DATA_DIR` / `DB_PATH`，**无 `SKILLS_DIR`、无截断阈值常量**。
5. `.gitignore` 忽略 `*.db` / `*.sqlite3`，但**不忽略 `data/`**（注释明确「Skill JSON 归档需纳入 git」）。

## 4. 已定决策（人工已拍板，作为本事务给定输入，原文记录）

> 以下两条为既定输入，本事务**不再重新讨论**，直接作为规划依据。

1. **git 已初始化**：git 已于 2026-09-28 初始化（main 分支，首次提交 78d505e 已包含设计文档、.agents 工作区与 0001 底座层）。设计文档中「Skill JSON 归档 / benchmark report 纳入 git 追踪」的前提已成立，规划时直接依赖即可。

2. **Task dataclass 缺口已核实**：`docs/system_design.md` 仅在 §11 定义了 `BenchmarkTask`（跑分题目结构）的字段；运行时 `Task`（进入 CLI/Loop 的任务载体，至少需携带任务文本与 `task_source` 标签，见 §4）全文没有字段定义。若 0002 的目标涉及 `Task`，必须把「回补设计文档中 `Task` 字段定义」列入拟议变更；若不涉及，将其列入风险或后续建议。

## 5. 本事务将引用的系统设计章节

- §2 分层视图与「上层只调下层」约束（存储门面只调 `storage.py`，不 `import sqlite3`）
- §3.1 `SkillRegistry` 职责与关键接口（`register` / `get` / `get_active` / `list` / `promote` / `rollback` / `deprecate`）
- §3.2 `TraceStore` 职责（写入 / 查询，按 skill / 时间 / 状态过滤）
- §3.3 `EvalStore`（evals / experiences 表门面）
- §5 Skill 持久化映射（SQLite 元数据 + JSON 内容本体）
- §6 `ExecutionTrace` / `TraceStep` 持久化与 4000 字符截断
- §7 `EvaluationResult`、§8 `Experience` 数据结构
- §10 Skill 版本化（状态机 `draft → candidate → active → deprecated`、回滚边、单 active 不变量、`metrics` 快照口径）
- §13 目录结构（`skills/registry.py`、`execution/trace.py`、`eval/store.py`）

## 6. 已知的设计缺口（本事务需处理或登记）

1. **`name` / `description` / `tags` 的持久化位置未定义**：设计 §5 的 SQLite 元数据清单与 JSON 内容清单**均未列出**这三个字段，但 `Skill` dataclass 有它们，且 §3.1 `list(tags=...)` 需要 `tags` 可过滤、检索（§3.2）需要 `description`。0001 的 `skills` 表也因此没有这三列。本事务在 `SkillRegistry` 中必须落定其存储位置（详见 `plan.md` §5/§7）。
2. **`Task` dataclass 字段定义缺失**（见 §4 决策 2）：本事务**不涉及** `Task`，登记为风险与后续建议，待执行层事务前回补设计。
