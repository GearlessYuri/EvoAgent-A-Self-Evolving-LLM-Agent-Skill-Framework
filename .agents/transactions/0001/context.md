# 事务 0001 上下文（Context）

> 本文件是事务开始时的「时间胶囊」，记录当时的项目状态与触发背景，使本事务脱离当前项目状态也可被独立理解。
> 按 `workflow/transaction_protocol.md` 维护。

- 事务 ID：`0001`
- 创建日期：2026-09-26
- 事务性质：首个开发事务（仓库尚无任何事务历史）

---

## 1. 触发原因

仓库在 2026-09-26 完成 `.agents/` 多智能体协作工作区的引导，但**没有任何业务源代码**。
系统设计（`docs/system_design.md`）已完整定义了一个 Python 项目的架构，却尚未落地任何一行代码。
因此本事务作为第一个开发事务，目标是落地系统设计中一切上层模块所依赖的**底座层**（数据契约 + 配置 + 存储底座）。

## 2. 事务开始时的项目状态快照

摘自当时的 `state/project_state.md`：

- **项目标识**：EvoAgent（取自仓库目录名；无文档可进一步核实）。
- **架构摘要**：未记录（截至工作区引导时仓库无任何源代码 / 文档 / 配置文件）。
- **已实现能力**：无。
- **当前开发阶段**：多智能体协作工作区已引导完成；尚未开始任何开发事务。
- **已知约束**：未指定编程语言、技术栈与目标平台（需由系统设计明确）。
- **当前事务**：无（下一个事务 ID 应为 `0001`）。

## 3. 事务开始时的实际仓库现状（经核实）

`find` 遍历结果，仓库当前仅包含以下文件：

```
.agents/README.md
.agents/roles/{coder,optimizer,planner,reviewer}.md
.agents/state/{active_transaction,project_state}.md
.agents/transactions/README.md
.agents/workflow/{protocol,state_protocol,transaction_protocol}.md
docs/system_design.md
```

- **无** `evoagent/` 源码包、**无** `pyproject.toml` / `requirements.txt`、**无** `tests/`、**无** 任何 `.py` 文件。
- 这是一个**纯文档仓库**，业务代码为零。

## 4. 相关背景：系统设计要点

`docs/system_design.md` 将 EvoAgent 定义为「基于执行反馈的自演进 Agent Skill 平台」，其核心闭环为：
`Task → Skill Retrieval → Agent Execution → Execution Trace → Evaluation → Experience → Skill Evolution → Validation → Skill Registry`。

与本事务直接相关的关键决策：

| 决策点 | 选择 |
|---|---|
| 语言 | Python 3.10+ |
| 数据结构 | `dataclasses`（`models.py` 统一定义，跨层「合同」） |
| 持久化 | SQLite（标准库 `sqlite3`）；`storage.py` 是全项目唯一写 SQL 的地方 |
| 配置 | `config.py` 集中管理阈值 / 权重 / 路径 |
| 测试 | `pytest` |

设计的分层（§2）中，**底座层** = `models.py`（数据结构）· `config.py`（配置）· `llm.py`（LLM 薄封装）· `storage.py`（存储底座），是上层存储门面（`SkillRegistry` / `TraceStore` / `EvalStore`）与执行 / 评估 / 演化层共同依赖的地基。

## 5. 本事务将引用的设计章节

- §2 分层视图与「上层只能调下层」的依赖约束
- §5 `Skill` / `FewShot` / `ToolSpec` 数据结构
- §6 `ExecutionTrace` / `TraceStep` 数据结构
- §7 `EvaluationResult` 数据结构
- §8 `Experience` 数据结构
- §11 `BenchmarkTask` 数据结构
- §13 目录结构与「文件 → 模块 / 类」对应表
- §14 技术选型（最小依赖）
