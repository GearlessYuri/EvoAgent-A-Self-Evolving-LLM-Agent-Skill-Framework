# 事务 0008 上下文（Context）

- 事务 ID：`0008`
- 创建日期：2026-09-29
- 前置：`0001` 底座 → `0002` 门面（含 SkillRegistry 状态机）→ `0003` 检索 → `0004` llm → `0005` 执行器 → `0006` 评估层 → `0007` Benchmark

## 1. 触发原因

评估层（`Evaluator`/`ExperienceExtractor`/`Benchmark`）已就绪，正向闭环与「尺子」都齐了，但**演化层缺失**——`Experience[]` 无法变成候选新版本、`Benchmark` 无法驱动 A/B promote。本事务落地演化层核心：`SkillEvolver` + `Validator`，串起「经验 → 候选 → 验证 → promote」的逆向流闭环（§9）。

## 2. 项目状态快照

见 `state/project_state.md`（`0007` 已关闭）：底座/门面/执行层/评估层（含 Benchmark）已落地；演化/编排层（`SkillEvolver`/`Validator`/`EvolutionLoop`）与 `tools.py` 未开始。全量 104 项测试通过。

## 3. 经核实的仓库现状（关键事实）

- git `main`@`36bace4`，工作树干净。
- `evoagent/evolution/` **不存在**（无 `evolver.py`/`validator.py`）。
- `evoagent/skills/registry.py`（`0002`）：`register`（尊重 `status`，`""`→active）、`promote`/`rollback`（`_set_active`：目标 active、其余 deprecated、目标不存在抛 `ValueError`）、`get_active`、`get`——promote 的现成状态机。
- `evoagent/eval/benchmark.py`（`0007`）：`Benchmark.run(tasks, skill) -> BenchmarkReport(per_task=[(task_id, passed, total_score)], success_rate, avg_total_score)`；`load_tasks`/`load_tasks_by_name`。
- `evoagent/eval/store.py`（`0002`）：`EvalStore.save_experience`（failed_evolution 落库用）。
- `evoagent/models.py`：`Skill` 有 `parent_version`/`change_log`/`metrics`/`status`；`Experience.category` 含 `"failed_evolution"`（§8）。
- `evoagent/config.py`：**无** `PROMOTE_WIN_RATE_THRESHOLD`/`MIN_REGRESSION_TASKS`。

## 4. 依赖的设计章节

§9（演化流程 + promote 规则）、§10（版本化 SemVer + 状态机 + 不可变历史）、§11（win_rate / 最小题数 / 防污染）、§3.4（SkillEvolver/Validator 职责）。

## 5. 本事务的关键衔接决策

- **SkillEvolver + Validator 一并落地**：同属演化闭环（Evolver 产候选 → Validator 验证 → promote），版本管理/防污染/A-B 判定贯穿两者，拆分反碎片化；体量（2 源 + 2 测）与 `0006`/`0002` 相当（理由见 `plan.md` §4）。
- **promote 走 `0002` 状态机**：候选为**新版本**（`status="draft"`、`parent_version` 记录），`Validator` 经 `registry.register`（draft）+ `registry.promote`（draft→active、旧版 deprecated），**不绕过 active 指针、不原地改**。
- **A/B 阈值设计既定**（§9/§11）：0.5 平局、0.55 win_rate、20 题下限，本事务**不得改值**，仅集中到 config。
