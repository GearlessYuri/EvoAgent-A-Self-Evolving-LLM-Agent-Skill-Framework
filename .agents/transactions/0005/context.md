# 事务 0005 上下文（Context）

- 事务 ID：`0005`
- 创建日期：2026-09-28
- 前置事务：`0001`（底座）→ `0002`（门面）→ `0003`（检索器 + `Task`）→ `0004`（`llm.py`）

## 1. 触发原因

正向闭环（§4）的「执行」环节缺失：`SkillRetriever`（`0003`）已就绪、`LLMClient`（`0004`）已就绪，但 `AgentExecutor` 未实现。本事务落地执行层 `AgentExecutor`，并闭合 `0004/result.md` §4/§11.10 登记的 `usage` 采集扩展点。

## 2. 项目状态快照

见 `state/project_state.md`（`0004` 已关闭）：底座层完整（含 `llm.py`），门面层 + 检索器已落地；执行层其余部分（`AgentExecutor`/`tools.py`）及评估/演化/编排层未开始。全量 68 项测试通过。

## 3. 经核实的仓库现状（关键事实）

- git `main`@`fa420b7`（`0004` 收尾后追加了「文档精炼纪律」工作区提交），工作树干净。
- `evoagent/llm.py`：`LLMClient.complete(prompt) -> str` 单方法，`client` 可注入、惰性 import openai；**丢弃** token/cost/latency（`evoagent/llm.py:30-36`）。
- `evoagent/execution/trace.py`：`TraceStore.save/get/list` 已就绪（`0002`），`save` 含 4000 截断；`ExecutionTrace.usage` 为 `dict | None` 字段（`evoagent/models.py:149`）。
- `evoagent/models.py`：`Task` 无 `task_id`（`0003` 裁定）；`ExecutionTrace` 有 `task_id`/`trace_id`/`task_source`/`retrieval_fallback`/`usage` 字段（§6）。
- `evoagent/skills/retriever.py`：`RetrievalResult(skill, score, fallback)` 的 `fallback` 即 `retrieval_fallback` 信号源。
- `evoagent/execution/` 下**无 `executor.py`**、**无 `tools.py`**。

## 4. 依赖的设计章节

§3.2（AgentExecutor 职责）、§4（正向流步骤 3）、§6（ExecutionTrace/TraceStep）、§13（`execution/executor.py`、`test_executor.py`）。

## 5. 本事务的关键衔接决策

- **usage 扩展**：`0004/result.md` §4 给出三条路径（扩展 `complete()` / 伴生方法 / 绕过分层）；本事务取**伴生方法**（见 `plan.md` §5），不改 `complete()` 的窄契约。
- **无工具调用 v1**：`tools.py` 与 function-calling 是独立的大块（§3.2 工具边界 + 沙箱），本事务**不实现**，`AgentExecutor` 先做无工具的单轮执行骨架（§12 有 `text-summarize` 无工具种子技能，合法）。
