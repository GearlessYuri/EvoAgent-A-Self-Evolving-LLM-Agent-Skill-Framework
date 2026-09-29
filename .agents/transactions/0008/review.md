# 事务 0008 评审（Review）

> 评审者（Reviewer）产出。按 `roles/reviewer.md` 要求，每条发现归入「已确认的问题 / 可能存在的风险 / 需要验证的假设」三类之一。
> 评审依据：实际仓库（`0001`–`0007` 落地后的源码）+ `docs/system_design.md` + `.agents/` 状态文件 + `0007/result.md`，而非仅凭计划文本。

- 事务 ID：`0008`
- 评审日期：2026-09-29
- 评审对象：`plan.md`（规划者产出）

---

## 0. 评审方法与实际核实记录

| 核实项 | 方法 | 结果 |
|---|---|---|
| `Benchmark.run` / `BenchmarkReport` | 读 `eval/benchmark.py` | `run(tasks, skill) -> BenchmarkReport(per_task, success_rate, avg_total_score)`；`per_task` 为 `(task_id, passed, total_score)` |
| `SkillRegistry` 状态机 | 读 `skills/registry.py`（0002 轮） | `register` 尊重 `status`（`""`→active）；`promote`/`rollback` 经 `_set_active`（目标 active、其余 deprecated）；**不校验目标当前态**（draft/candidate 均可直接 promote） |
| `config.py` | 读 | 有 `BENCHMARKS_DIR`/`TEST_SCRIPT_TIMEOUT_SEC`（0007）；**无 `PROMOTE_WIN_RATE_THRESHOLD`/`MIN_REGRESSION_TASKS`** |
| `Skill` / `Experience` 字段 | 读 `models.py` | `Skill` 有 `parent_version`/`change_log`/`metrics`/`status`；`Experience.trace_id` **必填**、`category` 含 `"failed_evolution"` |
| `evolution/` 目录 | `find` | **不存在**（无 `evolver.py`/`validator.py`） |
| git / 测试现状 | `git log`/`git status`/`pytest` | HEAD `36bace4`（main）；`git status --short` 非空（state 文件已改 + `0008/` 未跟踪，**工作树非干净**）；全量 `104 passed` |
| 设计 §9/§10/§11/§3.1/§3.4 原文 | 读 | §9 promote 规则（0.55/20/平局 0.5、样本不足转人工、不通过写 failed_evolution）；§10 状态机 `draft→candidate→active→deprecated`；§3.1 `metrics` 仅 benchmark 快照；§3.4 Evolver/Validator 职责 |

---

## 1. 计划完整性核对（planner.md 要求的 10 小节）

10 个小节**全部具备、内容具体可执行**（遵循「文档精炼纪律」，简洁但非空话）：

| # | 要求小节 | 是否具备 | 是否具体 |
|---|---|---|---|
| 1 | 当前状态 | ✅ | ✅ evolution/ 不存在、状态机与 Benchmark 已就绪、config 无阈值 |
| 2 | 问题 | ✅ | ✅ 演化层缺失、逆向流闭环断档 |
| 3 | 目标 | ✅ | ✅ SkillEvolver + Validator + 2 config 常量 |
| 4 | 范围 | ✅ | ✅ 做/不做清晰；EvolutionLoop/cli 顺延 0009；工具演化延后 |
| 5 | 拟议变更 | ✅ | ✅ 文件表 + §5.1/§5.2 细化 Evolver/Validator |
| 6 | 依赖 | ✅ | ✅ 标准库 + 既有 openai；无新第三方 |
| 7 | 风险 | ✅ | ✅ 6 条均附缓解（阈值/状态机/防污染/版本/配对/蔓延） |
| 8 | 实施顺序 | ✅ | ✅ 4 步 |
| 9 | 验收标准 | ✅ | ✅ 9 条客观可判定（阈值/候选字段/防污染/四步判定/版本衔接/落库） |
| 10 | 验证策略 | ✅ | ✅ 命令 + 用例清单 + grep 人工复核 |

结论：结构完整、无事实性硬错。A/B 阈值（0.55/20/平局 0.5）与 §9/§11 **逐条对齐**、win_rate 口径正确、promote 走既有状态机不绕过。主要问题集中在**「样本不足转人工」与「丢弃+failed_evolution」的区分**、**metrics 快照未落**、以及候选状态/版本跳级等细节。

---

## 2. 已确认的问题（对照仓库核实成立）

### 2.1 「样本不足（转人工）」与「不通过/不显著（丢弃+failed_evolution）」被计划笼统合并为「不 promote → 写 failed_evolution」

- **已核实设计 §9 step 5 明确区分两种结局**：①「该 skill 的 regression 集不足 20 题 → 不自动 promote，候选留在 candidate 状态**转人工确认**」；②「不通过/不显著 → **丢弃候选**，写一条 `failed_evolution` 的 Experience」。二者是**不同动作**：转人工不丢弃、不写 failed_evolution；丢弃才写 failed_evolution。
- **计划的写法**：§5.2 promote 判定四分支后，只给了一句「不 promote 动作：写 `failed_evolution` Experience」——把「样本不足（转人工）」也归入「写 failed_evolution」，且未说明样本不足时候选是否注册留待人工。
- **后果**：按计划实现，样本不足会**错误地**写一条 failed_evolution（语义上「样本不足」≠「演化失败」），且候选既不注册也不丢弃、悬空。
- **建议**：优化者把结局拆成三支——(a) 通过 → register(draft)+promote；(b) 样本不足 → 候选 `register`（留 draft/candidate 供人工）、**不写** failed_evolution、`reason="sample_insufficient"`；(c) 不通过/不显著 → 不注册、写 failed_evolution。并分别配测试。

### 2.2 `metrics` 基准快照未落（与 §3.1「只有 benchmark 得分作为快照随版本记录」冲突）

- **已核实**：设计 §3.1 明确 `metrics`「只有 benchmark 得分作为快照随版本记录」。计划 §9.2 要求候选 `metrics 空`（Evolver 侧**正确**——draft 尚未验证、无得分），但 §5.2 Validator 的 promote 动作（`register`→`promote`）**未把 A/B 的 benchmark 得分写回 `metrics`**。
- **后果**：promote 后的 active 版本 `metrics` 恒空，与 §3.1 的「benchmark 快照」设计不符，且后续报告层/回滚决策无法从 `metrics` 看到该版本的跑分。
- **建议**：优化者钉死——Validator 在 `register` 前把 `candidate.metrics = {"benchmark": {"success_rate":…, "avg_total_score":…, "win_rate":…}}`（字段名以优化者定），使 promote 后的版本自带得分快照。

---

## 3. 可能存在的风险（有迹象，未完全核实）

### 3.1 候选初始状态 `draft` vs `candidate`（设计 §4/§9/§10 自相矛盾）

- 设计三处不一致：§4 step8 说「status=draft」、§9 step3 说「status=candidate」、§10 状态机为 `draft → candidate → active → deprecated`（四态）。计划选 `draft`（§5.1），`promote` 直接 `draft→active`，**跳过 `candidate` 态**；且「转人工」时（§2.1）候选停留 `draft` 而非 §9 说的 `candidate`。
- **已核实**：`SkillRegistry._set_active` 不校验目标当前态，draft 直接 promote 可行——所以「跳过 candidate」在现实现下能跑，但与 §10 的四态机语义不符。
- **建议**：优化者钉死——本事务是否只用 `draft`/`active`/`deprecated` 三态（把 `candidate` 视为设计遗留、登记为已知简化），还是采用 §9 的 `candidate` 态。**须显式记录，不得静默。**

### 3.2 版本跳级规则含糊（计划已自识「由优化者钉」）

计划 §5.1「默认 patch，diff 大则 minor/major，规则由优化者钉」。但「谁定版本」（LLM 建议的跳级 vs 代码按 diff 确定性 bump）、「diff 大小」如何量化（按什么 diff、阈值多少）均未定。设计 §10「由 Evolver 提议 + 规则按 diff 大小自动判定」同样是两条腿。需钉死，否则 `version` 严格递增的验收 §9.2 无法可靠实现。

### 3.3 `failed_evolution` Experience 的字段映射未定义

`Experience.trace_id` **必填**，但 failed_evolution 无天然关联 trace（是演化失败，非某次执行）；`win_rate`/`avg` 失败指标如何落入 `summary`/`suggestion`/`target_section` 未钉。计划 §5.2 只说「写 failed_evolution（含 win_rate/avg）」。建议钉死：`trace_id=""` 或固定占位、指标序列化进 `summary` 的格式。

### 3.4 win_rate 判定里 branch 3/4 的 `reason` 值未穷举

计划 branch 1 有 `reason="sample_insufficient"`，branch 2 是 promote；但 branch 3（不显著 `0.5<win_rate<0.55`）与 branch 4（win_rate≤0.5 或 avg 下降）的 `reason` 字符串（如 `"insignificant"` vs `"regression"`）未定义。`ValidationResult.reason` 的取值集合需钉死，测试才能断言。

### 3.5 A/B「同批配对」是顺序跑（先 old 后 new），非同时段交错

设计 §9「同批配对 A/B（同时段、同 judge 模型）」。计划 §5.2 `benchmark.run(tasks, old)` 然后 `benchmark.run(tasks, candidate)` 是**顺序**执行。v1 下 judge 同模型（0006 简化）且测试 mock 确定性，顺序跑等价；但「同批配对」抵消 judge 漂移的精义在顺序跑下未真正实现。建议登记为已知局限（真实 A/B 的 judge 漂移问题待 judge 模型分离/同批交错解决）。

---

## 4. 需要验证的假设（附建议的确认方式）

### 4.1 `ValidationResult` 结构（计划自创，需钉死）

计划 §5.2 提出 `ValidationResult`（`validator.py` 内 dataclass，不进 `models.py`），字段 `promoted`/`win_rate`/`old_avg`/`new_avg`/`sample_size`/`reason`。设计未定义此结构。**建议确认方式**：优化者钉死字段名与类型（尤其 `reason` 的取值集合，见 §3.4）。不进 `models.py` 与 0003/0007 先例一致、正确。

### 4.2 `SkillEvolver` 的 LLM 输出 JSON schema（计划自创，需钉死）

计划 §5.1「用 `chat_json` 让 LLM 产出新 `prompt_template`+`few_shots`+`change_log`+建议版本跳级」，但 chat_json 输出的 JSON 键结构（`few_shots` 如何表示、`change_log` 键名、版本跳级建议字段）未定义。`test_evolver.py` 的 mock 需要明确 schema 才能构造。**建议确认方式**：优化者给出一个最小输出 JSON 示例，并钉死缺键/非法键时的兜底（如退化为 patch、change_log 空则回退旧值）。

### 4.3 已核实的前提（报告结果）

- **git**：HEAD `36bace4` ✅ 与 context §3 一致；工作树非干净（state 文件 + `0008/`），context「工作树干净」已过时（轻微，与前序同类）。
- **测试**：全量 `104 passed` ✅ 与 project_state/context 一致。
- **A/B 阈值**：计划 §5 的 `PROMOTE_WIN_RATE_THRESHOLD=0.55`/`MIN_REGRESSION_TASKS=20` 与 §9/§11 既定值一致 ✅（非自创）。
- **win_rate 口径**（更高 1/持平 0.5/更低 0 取均值）与 §11 一致 ✅。
- **promote 走状态机**：`registry.register`（draft）+`registry.promote`（`_set_active`）已核实可行、不绕过 active 指针、不可变历史 ✅。

---

## 5. 总体结论

**该计划可以进入优化（Optimizer）阶段。** 计划结构完整（10 小节齐全且具体）、A/B 阈值（0.55/20/平局 0.5）与 win_rate 口径**严格对齐 §9/§11**、promote 走 `0002` 既有状态机（不绕过 active 指针/不可变历史）、Evolver 防污染是**结构级**（`evolve()` 无参考答案参数）、范围控制良好（EvolutionLoop/cli 顺延 0009、工具演化延后、无新增依赖）、分层正确（Evolver 只调 llm，Validator 只调 benchmark/registry/eval_store）。**无事实性硬错。**

**进入 `task.md` 前，优化者必须裁定 / 钉死以下问题：**

1. **[必裁] 三支结局**：把「通过 / 样本不足（转人工，不写 failed_evolution）/ 不通过（丢弃+failed_evolution）」拆开，各自的动作（是否 register、是否写 failed_evolution）与测试（§2.1）。
2. **[必钉] `metrics` 快照**：Validator 在 promote 前把 benchmark 得分写入 `candidate.metrics`，满足 §3.1（§2.2）。
3. **[必钉] 候选状态**：draft vs candidate（§10 四态 vs §9 candidate）二选一并记录，明确是否使用 candidate 态（§3.1）。
4. **[必钉] 版本跳级规则**：谁定版本 + diff→patch/minor/major 的量化阈值（§3.2）。
5. **[建议钉] 细节**：failed_evolution 的字段映射与 `reason` 取值集合、Evolver 输出 JSON schema、A/B 顺序跑的「同批配对」局限登记（§3.3/§3.4/§4.2/§3.5）。

**未发现的问题**：无范围蔓延（SkillEvolver+Validator 同属演化闭环、捆绑合理）、无新第三方依赖、回归风险低（config 追加常量不动既有；新建 `evolution/` 包不影响既有模块）；`ValidationResult`/Evolver 输出结构不进 `models.py` 与先例一致。
