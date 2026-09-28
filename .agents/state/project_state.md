# 项目状态（Project State）

> 本文件是对仓库当前状况的整体理解快照，按 `workflow/state_protocol.md` 维护：
> 只记录可从仓库验证或用户明确提供的信息；不得描述推测中的未来架构；
> 每个事务关闭时更新到最新事实（历史由 `transactions/` 保留）。

## 项目标识（Project Identity）

名称：EvoAgent（取自仓库目录名；仓库内暂无文档可进一步核实）

用途：基于执行反馈的自演进 Agent Skill 平台（取自 `docs/system_design.md` §0）。

## 当前目标（Current Objective）

（待记录——事务 `0004` 的「落地 `llm.py` + 引入 `openai`」目标已完成，下一目标尚未在事务中明确。）

## 架构摘要（Architecture Summary）

分层架构（依据 `docs/system_design.md` §2）。**底座层已完整**（含 `llm.py`），存储领域门面层与执行层检索器已落地：

- `evoagent/models.py` —— 数据契约：`Task`（§4 回补）+ 设计 §5–§11 的 8 个 dataclass，共 **9 个**，含递归 `to_dict`/`from_dict` 序列化。
- `evoagent/config.py` —— 集中常量：路径（`DATA_DIR`/`DB_PATH`/`SKILLS_DIR`）+ 纯数值阈值/权重 + LLM 常量（`LLM_BASE_URL`/`LLM_MODEL`/`LLM_API_KEY_ENV`，key 仅环境变量）。
- `evoagent/llm.py` —— `LLMClient`：OpenAI 兼容 LLM 薄封装（窄接口单方法 `complete()`，client 可注入，惰性 import openai）。
- `evoagent/storage.py` —— 存储底座：`Storage` 类（连接 + WAL、建 5 表、通用参数化 CRUD），全项目唯一 `import sqlite3`/写 SQL 的模块。
- `evoagent/skills/registry.py` —— `SkillRegistry`：技能版本 CRUD + 状态机 + active 指针 + 内容 JSON 归档。
- `evoagent/execution/trace.py` —— `TraceStore`：Trace 写入/查询 + 4000 字符截断。
- `evoagent/eval/store.py` —— `EvalStore`：评估结果/经验读写 + `passed` 三态转换。
- `evoagent/skills/retriever.py` —— `SkillRetriever`：任务 → top-k skill（简单版：词频 + 余弦 + tag 过滤 + 无匹配兜底）。

尚未落地：执行/评估/演化/编排层（`AgentExecutor`/`tools.py`/`Evaluator`/`ExperienceExtractor`/`Benchmark`/`SkillEvolver`/`Validator`/`EvolutionLoop`）、`cli.py`。

## 已实现的能力（Implemented Capabilities）

- 可安装/可导入的 `evoagent` 包骨架（`pyproject.toml` PEP 621、`requirements.txt`、`__init__.py` 暴露 `__version__`）。
- 9 个数据契约 dataclass（`Task` + 设计 §5–§11 的 8 个）及其双向递归序列化。
- SQLite 存储底座：WAL 连接、自动建父目录、5 张表 schema、参数化 CRUD。
- 存储领域门面层：`SkillRegistry`、`TraceStore`、`EvalStore`。
- 执行层检索器 `SkillRetriever`：`retrieve`/`retrieve_top1`，词频 + 余弦 + tag 过滤。
- LLM 薄封装 `LLMClient`：OpenAI 兼容路径、窄接口 `complete()`、client 可注入。
- 单元测试 68 项全部通过（`tests/` 下 7 个测试文件）。

## 当前开发阶段（Current Development Stage）

底座层（含 `llm.py`）、存储领域门面层与执行层检索器已落地并通过 `pytest` 验证（事务 `0001`–`0004` 已关闭）。执行层其余部分（`AgentExecutor`/`tools.py`）及评估/演化/编排层尚未开始。

## 已知约束（Known Constraints）

- Python 3.10+（本机 3.13.9）。
- 运行时依赖：标准库 + `openai>=1.0`（OpenAI 兼容 SDK，唯一第三方运行时依赖）；开发期依赖 `pytest`。
- 分层约束：上层只能调下层（或同层）；`storage.py` 是全项目唯一写 SQL/`import sqlite3` 处，`llm.py` 只依赖 `config`。
- 并发模型：单进程单写者（SQLite 开 WAL）。
- 仓库为 git 仓库（`main` 分支，已初始化）。

## 已知局限（Known Limitations）

- `Storage.query` 本身不自动反序列化 JSON 字段；JSON 反序列化由各门面 `get*` 完成（分层设计）。
- `LLMClient.complete() -> str` 只回文本、丢弃 token/cost/latency（`AgentExecutor` 事务需扩展或加伴生方法以采集 `usage`）。
- `docs/system_design.md` 仍缺 `Task` dataclass 字段定义（事务 `0003` 在 `models.py` 代码中补齐，设计文档回补待后续事务）。
- `pyproject.toml` 的 `packages=["evoagent"]` 不含子包，`pip install .` 不打包门面（待引入 `cli.py`/真实安装时处理）。
- `metrics` 增量回写未实现（使用次数/成功率由 traces/evals 聚合，属后续报告层）。

## 已知风险（Known Risks）

（待记录）

## 当前优先级（Current Priorities）

（待记录）

## 重要决策（Important Decisions）

- 2026-09-26：建立 `.agents/` 多智能体协作工作区（规划 → 评审 → 优化 → 编码的工作流，事务化历史保留）。
- 2026-09-27（事务 0001）：底座层落地决策——
  - 数据契约裁定为 **8 个** dataclass；存储表裁定为 **5 张**（含 `experiences`）。
  - `config.py` 不预置 LLM 参数；依赖仅 `pytest`（openai/anthropic/numpy 延后）。
  - JSON 序列化在通用 `insert`/`update` 按值类型自动完成；`query` 不自动反序列化。
  - `trace_steps.truncated` 列先建好，4000 截断逻辑后置。
- 2026-09-28（事务 0002）：存储领域门面层落地决策——
  - `Skill.name`/`description`/`tags` 裁定持久化到 SQLite `skills` 表（加 3 列，带默认值），JSON 归档仅 3 内容字段。
  - JSON 反序列化与 `passed` 三态转换落在各门面 `get*`（`Storage.query` 仍不反序列化）。
  - `truncated` 仅 DB 层，不进 `TraceStep` 数据契约；4000 截断逻辑在 `TraceStore.save`。
  - 门面构造注入 `Storage`；`SkillRegistry` 额外注入 `skills_dir`。
  - `pyproject.toml` 子包问题登记为已知局限（本事务不修）。
- 2026-09-28（事务 0003）：执行层第一步（检索）落地决策——
  - `Task` 字段裁定为 `task: str` + `task_source: str`，**无 `task_id`**（用户拍板；`ExecutionTrace.task_id` 由未来 `AgentExecutor` 生成）。
  - 评分信号仅用 `skill.description`（不含 `name`/`tags`）；词频 + 余弦、不做 TF-IDF；零范数 → 0.0。
  - `RetrievalHit`/`RetrievalResult` 为 `retriever.py` 内 `NamedTuple`，不进 `models.py`。
  - `retrieve`（top-k 无兜底）与 `retrieve_top1`（top-1 + 阈值兜底）拆分；兜底返回内置 `DEFAULT_SKILL`（不写库、不落 JSON）。
  - `docs/system_design.md` 不回补（登记已知局限，待后续事务）。
- 2026-09-28（事务 0004）：底座层最后一块 `llm.py` 落地决策——
  - 只走 OpenAI 兼容路径（不实现 anthropic/多 provider 适配层）；`LLM_BASE_URL`/`LLM_MODEL`/`LLM_API_KEY_ENV` 三常量，key 仅环境变量、绝无明文。
  - `LLMClient` 窄接口单方法 `complete()`（纯文本入出），client 可注入，惰性 import openai。
  - 首次引入运行时第三方依赖 `openai>=1.0`（仅一个，不引入 anthropic/numpy）。
  - `complete() -> str` 丢弃 token/cost/latency，登记为 `AgentExecutor` 事务的 `usage` 扩展点。

## 当前事务（Current Transaction）

无，0004 已关闭，下一个事务 ID 应为 0005。
