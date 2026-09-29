# 事务 0009 上下文（Context）

- 事务 ID：`0009`（项目收官事务）
- 创建日期：2026-09-29
- 前置：`0001` 底座 → `0002` 门面 → `0003` 检索 → `0004` llm → `0005` 执行器 → `0006` 评估层 → `0007` Benchmark → `0008` 演化层

## 1. 触发原因

全部核心层（底座/门面/检索/LLM/执行/评估/Benchmark/演化）已落地并通过 115 项测试，但**项目尚不可交付**：缺主循环编排 `EvolutionLoop`（§3.5）、缺 `cli.py` 入口（§13）、`pip install .` 不打包子包、设计文档仍缺 `Task` 定义、无 README。本事务是收官事务，把「可用闭环」补成「可交付成品」。

## 2. 项目状态快照

见 `state/project_state.md`（`0008` 已关闭）：各层已落地；`EvolutionLoop`/`cli.py`/`tools.py` 未开始；已知局限含「`pyproject.toml` 不含子包」「设计文档缺 `Task` 定义」。全量 115 项测试通过。

## 3. 经核实的仓库现状（关键事实）

- git `main`@`cdc839f`，工作树干净。
- `evoagent/evolution/` 下**无 `loop.py`**；`evoagent/cli.py` **不存在**；仓库根**无 `README.md`**。
- `pyproject.toml`：`[tool.setuptools] packages = ["evoagent"]`（**不含子包**，`pip install .` 装不出 `skills`/`execution`/`eval`/`evolution`）。
- 已就绪接口：`SkillRegistry.get_active/list`（`0002`）、`SkillRetriever.retrieve_top1`（`0003`）、`AgentExecutor.run`（`0005`）、`EvalStore.list_evals/list_experiences`（`0002`）、`TraceStore.list`（`0002`）、`ExperienceExtractor.extract`（`0006`）、`SkillEvolver.evolve`（`0008`）、`Validator.validate`（`0008`，返回 `ValidationResult`）、`Benchmark.run/load_tasks_by_name`（`0007`）。
- `models.py` 的 `Task` 实际字段：`task: str` + `task_source: str`（`0003` 拍板，无 `task_id`）。

## 4. 依赖的设计章节

§1（闭环）、§3.5（EvolutionLoop 主循环）、§4（正向/逆向流）、§9（触发条件/成本控制）、§13（目录结构 + `cli.py`/`README.md`）、§15（成本控制抓手）。

## 5. 本事务的关键衔接决策

- **5 子项同属「可交付」一个连贯目标**：`EvolutionLoop` + `cli.py` + 打包修复 + `Task` 设计回补 + README——共同把项目变为可安装、可运行、可上手的成品。
- **设计回补仅限 `Task` 一处**（用户授权）：对齐 `0003` 落地实现（`task`/`task_source` 两字段），其余设计章节一律不改。
- **Loop 只编排不重实现**（§3.5）：调 `TraceStore`/`EvalStore`/`ExperienceExtractor`/`SkillEvolver`/`Validator`/`SkillRegistry`，下层逻辑已由 `0001`–`0008` 交付。
