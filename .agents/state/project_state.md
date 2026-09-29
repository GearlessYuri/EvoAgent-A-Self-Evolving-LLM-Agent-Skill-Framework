# 项目状态（Project State）

> 本文件是对仓库当前状况的整体理解快照，按 `workflow/state_protocol.md` 维护：
> 只记录可从仓库验证或用户明确提供的信息；不得描述推测中的未来架构；
> 每个事务关闭时更新到最新事实（历史由 `transactions/` 保留）。

## 项目标识（Project Identity）

名称：EvoAgent（取自仓库目录名；仓库内暂无文档可进一步核实）

用途：基于执行反馈的自演进 Agent Skill 平台（取自 `docs/system_design.md` §0）。

## 当前目标（Current Objective）

（待记录——事务 `0007` 的「落地 `Benchmark` + `test_script` 客观执行 + 防污染三规则」目标已完成，下一目标尚未在事务中明确。）

## 架构摘要（Architecture Summary）

分层架构（依据 `docs/system_design.md` §2）。**底座层完整**（含 `llm.py`），存储门面层、执行层（检索器 + 执行器）、评估层（Evaluator + ExperienceExtractor + Benchmark）已落地：

- `evoagent/models.py` —— 数据契约：`Task`（§4 回补）+ 设计 §5–§11 的 8 个 dataclass，共 **9 个**，含递归 `to_dict`/`from_dict` 序列化。
- `evoagent/config.py` —— 集中常量：路径 + 纯数值阈值/权重 + LLM 常量 + Benchmark/test_script 常量。
- `evoagent/llm.py` —— `LLMClient`：OpenAI 兼容 LLM 薄封装（`complete()` + `complete_with_usage()` + `chat_json()`）。
- `evoagent/storage.py` —— 存储底座：`Storage` 类（连接 + WAL、建 5 表、通用参数化 CRUD），全项目唯一 `import sqlite3`/写 SQL 的模块。
- `evoagent/skills/registry.py` —— `SkillRegistry`：技能版本 CRUD + 状态机 + active 指针 + 内容 JSON 归档。
- `evoagent/execution/trace.py` —— `TraceStore`：Trace 写入/查询 + 4000 字符截断。
- `evoagent/eval/store.py` —— `EvalStore`：评估结果/经验读写 + `passed` 三态转换。
- `evoagent/skills/retriever.py` —— `SkillRetriever`：任务 → top-k skill（词频 + 余弦 + tag 过滤 + 兜底）。
- `evoagent/execution/executor.py` —— `AgentExecutor`：单轮无工具执行（拼 prompt → LLM → 写 Trace）。
- `evoagent/eval/evaluator.py` —— `Evaluator`：客观信号（exact/contains/test_script）+ LLM-as-judge 融合 + `passed` 三态。
- `evoagent/eval/experience.py` —— `ExperienceExtractor`：Trace + Result → `Experience[]`。
- `evoagent/eval/benchmark.py` —— `Benchmark`：任务集加载 + 批量「执行→评估→汇总」+ `BenchmarkReport`。

尚未落地：执行层 `tools.py`（工具调用）、演化/编排层（`SkillEvolver`/`Validator`/`EvolutionLoop`）、`cli.py`。

## 已实现的能力（Implemented Capabilities）

- 可安装/可导入的 `evoagent` 包骨架（`pyproject.toml` PEP 621、`requirements.txt`、`__init__.py` 暴露 `__version__`）。
- 9 个数据契约 dataclass（`Task` + 设计 §5–§11 的 8 个）及其双向递归序列化。
- SQLite 存储底座：WAL 连接、自动建父目录、5 张表 schema、参数化 CRUD。
- 存储领域门面层：`SkillRegistry`、`TraceStore`、`EvalStore`。
- 执行层：`SkillRetriever`（检索）、`AgentExecutor`（单轮执行、usage 采集）。
- 评估层：`Evaluator`（客观 + judge + 融合 + passed 三态）、`ExperienceExtractor`（经验提炼）、`Benchmark`（任务集 + 批量跑分 + 汇总 + 防污染隔离）。
- LLM 薄封装 `LLMClient`：`complete()` + `complete_with_usage()` + `chat_json()`。
- 单元测试 104 项全部通过（`tests/` 下 11 个测试文件）。

## 当前开发阶段（Current Development Stage）

底座层、存储门面层、执行层、评估层（`Evaluator` + `ExperienceExtractor` + `Benchmark`）已落地并通过 `pytest` 验证（事务 `0001`–`0007` 已关闭）。演化/编排层（`SkillEvolver`/`Validator`/`EvolutionLoop`）与 `tools.py` 尚未开始。

## 已知约束（Known Constraints）

- Python 3.10+（本机 3.13.9）。
- 运行时依赖：标准库 + `openai>=1.0`（OpenAI 兼容 SDK，唯一第三方运行时依赖）；开发期依赖 `pytest`。
- 分层约束：上层只能调下层（或同层）；`storage.py` 是全项目唯一写 SQL/`import sqlite3` 处，`llm.py` 只依赖 `config`，执行/评估层只调下层接口。
- 并发模型：单进程单写者（SQLite 开 WAL）。
- 仓库为 git 仓库（`main` 分支，已初始化）。

## 已知局限（Known Limitations）

- `Storage.query` 本身不自动反序列化 JSON 字段；JSON 反序列化由各门面 `get*` 完成（分层设计）。
- `AgentExecutor` 的 `task_id`/`trace_id` 均每次执行 `uuid4()` 生成、语义趋同（`Task` 无稳定 id，任务关联/重试需后续事务回补）。
- `LLMClient.complete_with_usage()` 的 `total_cost` 恒为占位 `0.0`（定价表未设计，真实化待后续事务）。
- `Evaluator` 的 judge 与执行同模型（未引入 `LLM_JUDGE_MODEL`，设计 §7 要求「不同模型」已接受简化）。
- `Evaluator` 的 `test_script` 仅「崩溃/超时隔离」（子进程 + 超时），非 OS 沙箱——不可信脚本需 OS 级沙箱。
- `Benchmark.load_tasks` 要求 JSON 含 `reference_answer`（`from_dict` 严格，§4.3「可选」措辞与实际不一致）。
- `ExperienceExtractor` 的 `_MIN_CONFIDENCE` 硬编码在 `experience.py`（非 `config`）。
- `docs/system_design.md` 仍缺 `Task` dataclass 字段定义（事务 `0003` 在 `models.py` 代码中补齐，设计文档回补待后续事务）。
- `pyproject.toml` 的 `packages=["evoagent"]` 不含子包，`pip install .` 不打包门面（待引入 `cli.py`/真实安装时处理）。
- `metrics` 增量回写未实现（使用次数/成功率由 traces/evals 聚合，属后续报告层）。

## 已知风险（Known Risks）

（待记录）

## 当前优先级（Current Priorities）

（待记录）

## 重要决策（Important Decisions）

- 2026-09-26：建立 `.agents/` 多智能体协作工作区（规划 → 评审 → 优化 → 编码的工作流，事务化历史保留）。
- 2026-09-27（事务 0001）：底座层落地决策——8 个 dataclass；5 张表；`config.py` 不预置 LLM 参数；JSON 序列化在通用 CRUD；`truncated` 列先建好。
- 2026-09-28（事务 0002）：存储领域门面层落地决策——`name`/`description`/`tags` 落 SQLite 加 3 列；JSON 反序列化/`passed` 三态落门面；`truncated` 仅 DB 层。
- 2026-09-28（事务 0003）：执行层检索器落地决策——`Task` 无 `task_id`（用户拍板）；评分仅 `description`；`RetrievalHit`/`Result` 为 retriever 内 NamedTuple。
- 2026-09-28（事务 0004）：底座层 `llm.py` 落地决策——只走 OpenAI 兼容路径；窄接口 `complete()`；引入 `openai>=1.0`。
- 2026-09-28（事务 0005）：执行层 `AgentExecutor` 落地决策——`complete_with_usage()` 伴生方法；v1 单轮无工具；`run()` 只返回 Trace。
- 2026-09-29（事务 0006）：评估层 Evaluator + ExperienceExtractor 落地决策——`chat_json()` + 解析兜底；六分支 `eval_basis` + `passed` 三态；judge 同模型；`_MIN_CONFIDENCE` 硬编码。
- 2026-09-29（事务 0007）：Benchmark + test_script 落地决策——
  - `test_script` 客观定论：子进程 + 超时（`TEST_SCRIPT_TIMEOUT_SEC=5`），`returncode==0`→pass；`value` 非字符串/空→无客观走 judge。
  - `Benchmark`：任务集加载 + 批量「执行→评估→汇总」+ `BenchmarkReport`（不进 models.py）。
  - `success_rate` 口径：`passed is True 数 / passed 非 None 数`（None 不计分母）；`avg_total_score` 全任务均值。
  - 防污染三规则代码化：来源隔离（`task_source="benchmark"`）/ 答案隔离（reference_answer 只传 evaluator）/ extension 只考不学（无导出经验 API）。

## 当前事务（Current Transaction）

无，0007 已关闭，下一个事务 ID 应为 0008。
