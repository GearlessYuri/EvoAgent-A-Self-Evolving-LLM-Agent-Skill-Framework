# 项目状态（Project State）

> 本文件是对仓库当前状况的整体理解快照，按 `workflow/state_protocol.md` 维护：
> 只记录可从仓库验证或用户明确提供的信息；不得描述推测中的未来架构；
> 每个事务关闭时更新到最新事实（历史由 `transactions/` 保留）。

## 项目标识（Project Identity）

名称：EvoAgent（取自仓库目录名；仓库内暂无文档可进一步核实）

用途：基于执行反馈的自演进 Agent Skill 平台（取自 `docs/system_design.md` §0）。

## 当前目标（Current Objective）

（待记录——首个事务 0001 的「项目骨架 + 底座层」目标已完成，下一目标尚未在事务中明确。）

## 架构摘要（Architecture Summary）

分层架构（依据 `docs/system_design.md` §2）。已落地**底座层**：

- `evoagent/models.py` —— 数据契约：设计 §5–§11 的 8 个 dataclass（`FewShot` / `ToolSpec` / `Skill` / `TraceStep` / `ExecutionTrace` / `EvaluationResult` / `Experience` / `BenchmarkTask`），含递归 `to_dict` / `from_dict` 序列化。
- `evoagent/config.py` —— 集中常量：路径（`DATA_DIR` / `DB_PATH`）+ 纯数值阈值 / 权重（`RETRIEVAL_FALLBACK_THRESHOLD` / `OBJECTIVE_WEIGHT` / `JUDGE_WEIGHT` / `PASS_THRESHOLD` / `SQLITE_WAL_ENABLED`）。
- `evoagent/storage.py` —— 存储底座：`Storage` 类（连接 + WAL、建 5 表、通用参数化 CRUD），是全项目唯一 `import sqlite3` / 写 SQL 的模块。

尚未落地：`llm.py`、存储领域门面（`SkillRegistry` / `TraceStore` / `EvalStore`）、执行 / 评估 / 演化 / 编排层、`cli.py`。

## 已实现的能力（Implemented Capabilities）

- 可安装 / 可导入的 `evoagent` 包骨架（`pyproject.toml` PEP 621、`requirements.txt` 仅 `pytest`、`__init__.py` 暴露 `__version__`）。
- 8 个数据契约 dataclass 及其双向递归序列化（嵌套重建、`None` / 空集区分、`passed` 三态保留）。
- SQLite 存储底座：WAL 连接、自动建父目录、5 张表 schema、参数化 CRUD（`insert` / `query` / `update` / `delete`）。
- 单元测试 26 项全部通过（`tests/test_models.py`、`tests/test_storage.py`）。

## 当前开发阶段（Current Development Stage）

底座层（`models.py` / `config.py` / `storage.py`）已落地并通过 `pytest` 验证（事务 `0001` 已关闭）。上层模块尚未开始。

## 已知约束（Known Constraints）

- Python 3.10+（本机 3.13.9）。
- 运行时仅标准库（`sqlite3` / `dataclasses` / `typing` / `json` / `pathlib`）；唯一第三方依赖是开发期 `pytest`。
- 分层约束：上层只能调下层（或同层）；`storage.py` 是全项目唯一写 SQL / `import sqlite3` 处。
- 并发模型：单进程单写者（SQLite 开 WAL）。
- 仓库当前非 git 仓库。

## 已知局限（Known Limitations）

- 通用 `Storage.query` 不自动反序列化 JSON 字段（`metrics` / `usage` / `objective` / `rubric_scores` 以 TEXT 返回原始 JSON 字符串），反序列化后置到领域门面层。
- 系统设计未给出 `Task` dataclass 字段定义（仅 `BenchmarkTask` 有定义）。
- Skill 内容 JSON 归档与版本 diff 依赖 git，当前未初始化。

## 已知风险（Known Risks）

（待记录）

## 当前优先级（Current Priorities）

（待记录）

## 重要决策（Important Decisions）

- 2026-09-26：建立 `.agents/` 多智能体协作工作区（规划 → 评审 → 优化 → 编码的工作流，事务化历史保留）。
- 2026-09-27（事务 0001）：底座层落地决策——
  - 数据契约裁定为 **8 个** dataclass（设计全文 `@dataclass` 实际数量；计划中「9」为笔误）。
  - 存储表裁定为 **5 张**（`skills` / `traces` / `trace_steps` / `evals` / `experiences`，含 `experiences`）。
  - `config.py` 不预置任何 LLM provider / model / API key 常量（随 `llm.py` 事务引入）。
  - 依赖仅 `pytest`；openai / anthropic / numpy 延后到对应功能事务。
  - JSON 序列化在通用 `insert` / `update` 按值类型（dict/list）自动完成；`query` 不自动反序列化（后置门面层）。
  - `trace_steps.truncated` 列本事务建好，但 4000 字符截断 + 置位逻辑归属后续 TraceStore。

## 当前事务（Current Transaction）

无，0001 已关闭，下一个事务 ID 应为 0002。
