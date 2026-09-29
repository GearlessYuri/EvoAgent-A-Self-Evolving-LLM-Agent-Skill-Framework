# 项目状态（Project State）

> 本文件是对仓库当前状况的整体理解快照，按 `workflow/state_protocol.md` 维护：
> 只记录可从仓库验证或用户明确提供的信息；不得描述推测中的未来架构；
> 每个事务关闭时更新到最新事实（历史由 `transactions/` 保留）。

## 项目标识（Project Identity）

名称：EvoAgent（取自仓库目录名；仓库内暂无文档可进一步核实）

用途：基于执行反馈的自演进 Agent Skill 平台（取自 `docs/system_design.md` §0）。

## 当前目标（Current Objective）

（待记录——事务 `0009` 的收官目标已完成，项目补成可交付成品；下一目标尚未在事务中明确。）

## 架构摘要（Architecture Summary）

分层架构（依据 `docs/system_design.md` §2）。**全部分层（底座/存储门面/执行/评估/演化/编排）已落地**，正向流 + 逆向流闭环贯通：

- `evoagent/models.py` —— 数据契约：`Task` + 设计 §5–§11 的 8 个 dataclass，共 **9 个**，含递归 `to_dict`/`from_dict` 序列化。
- `evoagent/config.py` —— 集中常量：路径 + 纯数值阈值/权重 + LLM 常量 + Benchmark/test_script 常量 + 演化 promote/触发常量。
- `evoagent/llm.py` —— `LLMClient`：OpenAI 兼容 LLM 薄封装（`complete()` + `complete_with_usage()` + `chat_json()`）。
- `evoagent/storage.py` —— 存储底座：`Storage` 类，全项目唯一 `import sqlite3`/写 SQL 的模块。
- `evoagent/skills/registry.py` —— `SkillRegistry`；`evoagent/execution/trace.py` —— `TraceStore`；`evoagent/eval/store.py` —— `EvalStore`。
- `evoagent/skills/retriever.py` —— `SkillRetriever`；`evoagent/execution/executor.py` —— `AgentExecutor`。
- `evoagent/eval/evaluator.py` —— `Evaluator`；`evoagent/eval/experience.py` —— `ExperienceExtractor`；`evoagent/eval/benchmark.py` —— `Benchmark`。
- `evoagent/evolution/evolver.py` —— `SkillEvolver`；`evoagent/evolution/validator.py` —— `Validator`。
- `evoagent/evolution/loop.py` —— `EvolutionLoop`：主循环编排（收集低分 real trace → 提炼 → 演化 → 验证 → 更新注册表）。
- `evoagent/cli.py` —— CLI 入口（run / evolve / bench / list）+ `build_components` 组合根。

尚未落地：执行层 `tools.py`（工具调用）。

## 已实现的能力（Implemented Capabilities）

- 可安装/可导入的 `evoagent` 包（`pip install .` 纳入全部子包）。
- 9 个数据契约 dataclass 及其双向递归序列化。
- SQLite 存储底座 + 三门面（`SkillRegistry`/`TraceStore`/`EvalStore`）。
- 执行层（`SkillRetriever` + `AgentExecutor`）、评估层（`Evaluator`/`ExperienceExtractor`/`Benchmark`）、演化层（`SkillEvolver`/`Validator`）、编排层（`EvolutionLoop`）、`cli.py` 入口。
- 完整闭环：正向流（检索→执行→Trace→评估）+ 逆向流（经验→演化→验证→promote）。
- 单元测试 126 项全部通过（`tests/` 下 15 个测试文件）。

## 当前开发阶段（Current Development Stage）

项目已补齐为**可交付成品**：全部分层 + `EvolutionLoop` + `cli.py` + 打包修复 + 设计回补 + README 均落地并通过 `pytest` 验证（事务 `0001`–`0009` 已关闭）。`tools.py`（工具调用）与种子数据播种仍为后续项。

## 已知约束（Known Constraints）

- Python 3.10+（本机 3.13.9）。
- 运行时依赖：标准库 + `openai>=1.0`（OpenAI 兼容 SDK，唯一第三方运行时依赖）；开发期依赖 `pytest`。
- 分层约束：上层只能调下层（或同层）；`storage.py` 是全项目唯一写 SQL/`import sqlite3` 处，`cli.py` 的 `build_components` 是唯一组合根（唯一 `import Storage`/`connect`/`init_schema`）。
- 并发模型：单进程单写者（SQLite 开 WAL）。
- 仓库为 git 仓库（`main` 分支，已初始化）。

## 已知局限（Known Limitations）

- `Storage.query` 本身不自动反序列化 JSON 字段；JSON 反序列化由各门面 `get*` 完成（分层设计）。
- `AgentExecutor` 的 `task_id`/`trace_id` 均每次执行 `uuid4()` 生成、语义趋同（`Task` 无稳定 id，任务关联/重试需后续事务回补）。
- `LLMClient.complete_with_usage()` 的 `total_cost` 恒为占位 `0.0`（定价表未设计）。
- `Evaluator` 的 judge 与执行同模型（未引入 `LLM_JUDGE_MODEL`）；`test_script` 仅「崩溃/超时隔离」非 OS 沙箱。
- `Benchmark.load_tasks` 要求 JSON 含 `reference_answer`（`from_dict` 严格）。
- `ExperienceExtractor` 的 `_MIN_CONFIDENCE` 硬编码在 `experience.py`（非 `config`）。
- 演化候选只用三态（draft/active/deprecated）、版本恒 patch 递增、A/B 顺序跑（非「同批交错」抵消 judge 漂移）。
- `EvolutionLoop` 触发条件只做「总样本数阈值」（不实现「连续 M 次」/「定时」模式）。
- 种子技能与 benchmark 集**未播种**（`evolve`/`bench` 需先准备数据，README 已标注非开箱即用）。
- `metrics` 增量回写未实现（使用次数/成功率由 traces/evals 聚合，属后续报告层）。

## 已知风险（Known Risks）

（待记录）

## 当前优先级（Current Priorities）

（待记录）

## 重要决策（Important Decisions）

- 2026-09-26：建立 `.agents/` 多智能体协作工作区（规划 → 评审 → 优化 → 编码的工作流，事务化历史保留）。
- 2026-09-27（事务 0001）：底座层——8 个 dataclass；5 张表；`config.py` 不预置 LLM 参数；JSON 序列化在通用 CRUD；`truncated` 列先建好。
- 2026-09-28（事务 0002）：存储领域门面层——`name`/`description`/`tags` 落 SQLite 加 3 列；JSON 反序列化/`passed` 三态落门面；`truncated` 仅 DB 层。
- 2026-09-28（事务 0003）：执行层检索器——`Task` 无 `task_id`（用户拍板）；评分仅 `description`；`RetrievalHit`/`Result` 为 retriever 内 NamedTuple。
- 2026-09-28（事务 0004）：底座层 `llm.py`——只走 OpenAI 兼容路径；窄接口 `complete()`；引入 `openai>=1.0`。
- 2026-09-28（事务 0005）：执行层 `AgentExecutor`——`complete_with_usage()` 伴生方法；v1 单轮无工具。
- 2026-09-29（事务 0006）：评估层 Evaluator + ExperienceExtractor——`chat_json()` + 解析兜底；六分支 `eval_basis` + `passed` 三态；judge 同模型。
- 2026-09-29（事务 0007）：Benchmark + test_script——`test_script` 客观定论（子进程 + 超时）；`Benchmark` 任务集加载 + 批量汇总；防污染三规则代码化。
- 2026-09-29（事务 0008）：演化层 SkillEvolver + Validator——候选 draft（patch 递增）；A/B win_rate 三支结局；promote 走状态机。
- 2026-09-29（事务 0009）：收官——`EvolutionLoop` 内存过滤（只挖 real 且非 infra 低分 trace）+ 总样本数阈值；`cli.py` `build_components` 唯一组合根 + `run` 映射 `retrieval_fallback`；打包修复 `packages.find` 纳入 4 子包；`docs/system_design.md` 回补 `Task` 定义（仅此一处）；README 如实标注 seed 数据前置。

## 当前事务（Current Transaction）

无，0009 已关闭，下一个事务 ID 应为 0010。
