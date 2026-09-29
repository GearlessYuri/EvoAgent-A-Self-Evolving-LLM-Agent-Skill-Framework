# 事务 0006 上下文（Context）

- 事务 ID：`0006`
- 创建日期：2026-09-29
- 前置：`0001` 底座 → `0002` 门面 → `0003` 检索 → `0004` llm → `0005` 执行器

## 1. 触发原因

正向流（§4）已贯通到「执行 + Trace」，但**评估层缺失**——Trace 无法变成可比较的「分数 + 结论」，演化无从获得梯度（§7）。本事务落地评估层核心：`Evaluator`（客观 + LLM-as-judge）+ `ExperienceExtractor`（经验提炼），并复用 `0004` 预留的 `chat_json` 扩展点。

## 2. 项目状态快照

见 `state/project_state.md`（`0005` 已关闭）：底座层完整（含 `llm.py`）、门面层 + 执行层（`SkillRetriever`/`AgentExecutor`）已落地；评估/演化/编排层未开始。全量 75 项测试通过。

## 3. 经核实的仓库现状（关键事实）

- git `main`@`82963ac`（`0005` 收尾后追加工作区提交），工作树干净。
- `evoagent/llm.py`：`complete`/`complete_with_usage` 已就绪，**无 `chat_json`**（`0004` 预留的扩展点）。
- `evoagent/eval/store.py`（`0002`）：`EvalStore.save_eval/get_eval/list_evals/save_experience/list_experiences` 已就绪；`passed` 三态转换已实现。
- `evoagent/models.py`：`EvaluationResult`（§7）、`Experience`（§8）、`ExecutionTrace`（§6）、`Task`（§4）字段齐全。
- `evoagent/config.py`：已有 `OBJECTIVE_WEIGHT=0.7`/`JUDGE_WEIGHT=0.3`/`PASS_THRESHOLD=0.6`（`0001`）——融合权重与 passed 阈值**无需新增配置**。
- `evoagent/eval/` 下**无 `evaluator.py`/`experience.py`/`benchmark.py`**。

## 4. 依赖的设计章节

§7（Evaluator 信号设计）、§8（Experience 数据结构）、§3.3（评估层职责）、§11（BenchmarkTask 的 `objective_check` 形态，供 `objective_check` 参数参考）。

## 5. 本事务的关键衔接决策

- **chat_json**：`0004` 裁定 #3 收窄了 `complete()`，但 `chat_json` 是 §7 LLM-as-judge 的明确需求（`0004/result.md` §4 登记的扩展点），本事务实现。
- **Benchmark 顺延**：`Benchmark`（任务集 + 运行器 + 汇总）是 `Validator`（A/B）的「尺子」，依赖 `AgentExecutor`+`Evaluator` 齐备、且含任务集加载/批量跑分等独立大块，故**顺延至 `0007`**（工作量判断见 `plan.md` §4）。
