# 事务 0007 上下文（Context）

- 事务 ID：`0007`
- 创建日期：2026-09-29
- 前置：`0001` 底座 → `0002` 门面 → `0003` 检索 → `0004` llm → `0005` 执行器 → `0006` 评估层（Evaluator + ExperienceExtractor）

## 1. 触发原因

评估层核心已就绪（`0006`），但**缺「尺子」**：`Benchmark`（任务集 + 批量「执行→评估→汇总」）未落地，`Validator` 的 A/B 无从衡量。同时 `0006/result.md` §4 登记的 `test_script` 客观执行延后至此，须一并补上。

## 2. 项目状态快照

见 `state/project_state.md`（`0006` 已关闭）：底座/门面/执行层/评估层核心已落地；`tools.py`、`Benchmark` 及演化/编排层未开始。全量 92 项测试通过。

## 3. 经核实的仓库现状（关键事实）

- git `main`@`58d6e12`，工作树干净。
- `evoagent/eval/evaluator.py`：`evaluate(trace, task, *, reference_answer, rubric, objective_check)` 六分支；`objective_check.type` 不在 `{exact, contains}` 时**视作「无客观」走 judge**（`evaluator.py:74-76` 显式注释「test_script 延后到 0007」）。
- `evoagent/eval/` 下无 `benchmark.py`。
- `evoagent/models.py`：`BenchmarkTask`（§11：`task_id/task/rubric/objective_check/tags/difficulty/reference_answer=""`）已就绪。
- `evoagent/config.py`：无 `BENCHMARKS_DIR`、无 `TEST_SCRIPT_TIMEOUT_SEC`。
- `AgentExecutor.run(task, skill)` 的 prompt 组装**只用 `task.task`**（`executor.py:_render_prompt`），参考答案无法进入执行路径——答案隔离有现成结构。

## 4. 依赖的设计章节

§11（Benchmark/Eval：任务集、防污染三规则、指标、报告）、§9（A/B promote 与 win_rate，供后续 Validator）、§3.3（Benchmark 职责）、§7（test_script 客观类型）、§13（`data/benchmarks/`、`eval/benchmark.py`）。

## 5. 本事务的关键衔接决策

- **Benchmark 单独落地，SkillEvolver 顺延 `0008`**：Benchmark 含任务集加载 + 批量编排 + `test_script` 安全设计 + 防污染三规则的代码化隔离，体量已足；SkillEvolver 与其无耦合（用户确认），且与 `Validator`（A/B）天然成对，归 `0008` 更聚焦（理由见 `plan.md` §4）。
