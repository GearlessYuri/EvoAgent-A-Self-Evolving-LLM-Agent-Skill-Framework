# 事务 0006 评审（Review）

> 评审者（Reviewer）产出。按 `roles/reviewer.md` 要求，每条发现归入「已确认的问题 / 可能存在的风险 / 需要验证的假设」三类之一。
> 评审依据：实际仓库（`0001`–`0005` 落地后的源码）+ `docs/system_design.md` + `.agents/` 状态文件 + `0005/result.md`，而非仅凭计划文本。

- 事务 ID：`0006`
- 评审日期：2026-09-29
- 评审对象：`plan.md`（规划者产出）

---

## 0. 评审方法与实际核实记录

| 核实项 | 方法 | 结果 |
|---|---|---|
| `llm.py` 现状 | 读 | `complete()`（复用 `complete_with_usage`）+ `complete_with_usage()`；**无 `chat_json`**；模块 docstring 第 3 行写「不实现 … chat_json …」 |
| `EvalStore` 现状 | 读 `eval/store.py` | `save_eval`/`get_eval`/`list_evals` + `save_experience`/`list_experiences`；`passed` 三态转换、JSON 反序列化已就绪 |
| `EvaluationResult` / `Experience` 字段 | 读 `models.py` | `EvaluationResult` 全字段必填（含 `objective: dict`/`judge_score`/`rubric_scores`）；`Experience` 全字段必填（**含 `summary`**） |
| `config.py` 常量 | 读 | `OBJECTIVE_WEIGHT=0.7`/`JUDGE_WEIGHT=0.3`/`PASS_THRESHOLD=0.6` 已存在；**无 `LLM_JUDGE_MODEL`、无 confidence 阈值** |
| `eval/` 目录 | `find` | 仅 `__init__.py`/`store.py`，**无 `evaluator.py`/`experience.py`/`benchmark.py`** |
| git / 测试现状 | `git log`/`git status`/`pytest` | HEAD `82963ac`（main）；`git status --short` 非空（state 文件已改 + `0006/` 未跟踪，**工作树非干净**）；全量 `75 passed` |
| 设计 §7/§8/§3.3 原文 | 读 | §7 四分支 `eval_basis`、融合公式、`passed` 三态、judge「与执行不同模型」；§8 `Experience` 字段与 `category`/`target_section` 枚举；§3.3 评估层职责 |

---

## 1. 计划完整性核对（planner.md 要求的 10 小节）

10 个小节**全部具备、内容具体可执行**（计划遵循「文档精炼纪律」，较简洁但非空话）：

| # | 要求小节 | 是否具备 | 是否具体 |
|---|---|---|---|
| 1 | 当前状态 | ✅ | ✅ 评估层缺失、config 已含融合权重 |
| 2 | 问题 | ✅ | ✅ Trace 无评估出口、chat_json 未落地 |
| 3 | 目标 | ✅ | ✅ chat_json + Evaluator + ExperienceExtractor |
| 4 | 范围 | ✅ | ✅ 做/不做清晰；Benchmark 顺延 0007 有工作量理由；test_script 延后 |
| 5 | 拟议变更 | ✅ | ✅ 文件表 + §5.1/§5.2/§5.3 细化 |
| 6 | 依赖 | ✅ | ✅ 标准库 + 既有 openai；无 config 变更 |
| 7 | 风险 | ✅ | ✅ 6 条均附缓解（passed 边界、客观判定、chat_json 兜底、judge 模型、test_script、蔓延） |
| 8 | 实施顺序 | ✅ | ✅ 4 步 |
| 9 | 验收标准 | ✅ | ✅ 8 条客观可判定（四分支、跳过 judge、写库回读、confidence 过滤、grep 分层） |
| 10 | 验证策略 | ✅ | ✅ 命令 + 用例清单 + grep 人工复核 |

结论：结构完整、无事实性硬错。主要问题集中在**§7 融合逻辑的若干数值/分支细节未钉死**与**「judge 模型分离」这一设计显式要求的偏离**。

---

## 2. 已确认的问题（对照仓库核实成立）

### 2.1 `Experience.summary`（必填字段）被计划 §5.3 遗漏

- **已核实**：`Experience` 的 `summary: str` 是**必填字段（无默认值）**（`models.py:178`）。计划 §5.3 枚举 extractor 产出的字段为「`category`/`target_section`/`suggestion`/`confidence`」，**漏了 `summary`**。
- **后果**：编码者按计划清单实现时可能漏填 `summary`，导致 `Experience` 构造失败或字段为空。
- **建议**：优化者在 `task.md` 明确 `Experience` 全字段（含 `summary`）都由 extractor 产出，验收 §9.6 补充对 `summary` 非空的断言。

### 2.2 `llm.py` 模块 docstring「不实现 … chat_json …」将在本事务后失准，计划未提更新（轻微）

- **已核实**：`llm.py:3` docstring 现写「不实现 anthropic、多 provider 适配层、chat_json、tool calling」。本事务加 `chat_json` 后该句失准。
- **建议**：与 0004 的 config docstring 同类问题，优化者把「同步更新 `llm.py` docstring」列入 `task.md`（`anthropic`/多 provider/tool calling 仍不实现，仅删去 `chat_json`）。

---

## 3. 可能存在的风险（有迹象，未完全核实）

### 3.1 `contains` 半信号 → 数值 `objective_score` 的映射未定义

设计 §7 融合公式用**标量** `objective_score`（`0.7*obj + 0.3*judge`），但 §11 `objective_check` 是 `{"type": "exact"|"contains"|..., "value": ...}` 的 dict，`contains` 是「半信号」。计划 §5.2 只说「contains → 半信号」，**未定义** `contains` 命中/未命中如何映射为 0~1 分数（命中记 1.0？未命中 0.0？还是部分分？）。这直接影响 `mixed` 分支的 `total_score`。**建议**优化者钉死 `objective_score` 的计算（至少 exact/contains 两种），并覆盖「contains 命中 / 未命中」两用例。

### 3.2 四分支未覆盖「`contains` 半信号 + 无 rubric」组合

计划 §5.2 的四分支是：客观定论 / 半信号+rubric / 无客观+rubric / 无客观+无 rubric。但 `evaluate` 的 `objective_check` 与 `rubric` 是**两个独立可选参数**，存在「`objective_check.type=="contains"` 但 `rubric=None`」的组合，计划未映射。设计 §7 的融合表也仅列「有客观+rubric / 只有 rubric / 两者皆无」三行，同样漏了「有客观+无 rubric」。**建议**优化者补这一分支（或归入 `judge_generic`+`passed=None`，或显式要求 contains 必配 rubric），并加对应用例。

### 3.3 `exact`/`contains` 的比较目标含糊（`reference_answer` vs `objective_check["value"]`）

计划 §5.2 写「exact → `final_output==reference` 定论」，但「reference」指代不明：`evaluate` 同时有 `reference_answer: str` 参数与 `objective_check: dict`（其 `value` 才是判题目标，§11）。设计 §11 把 `reference_answer`（参考答案）与 `objective_check`（判题规则）**分开**。**建议**优化者钉死：客观 `exact`/`contains` 比较用 `objective_check["value"]`；`reference_answer` 的用途（judge 上下文？）单独明确。

### 3.4 `EvaluationResult` 各字段的填充口径未钉死

- `objective` dict（设计 §7 注释 `{status, matched, test_pass, ...}`）在四分支各填什么未定义；
- 跳过 judge 时 `judge_score` 记 0（设计 §7 字段注释已写，但计划未显式落到 §5.2）；
- 客观失败（`status∈{error,timeout}`）时 `total_score` 具体值（0.0？）未钉死。
这些字段影响验收 §9.5 的「回读一致」，需在 `task.md` 逐字段给出口径。

### 3.5 `test_script` 客观类型被当「无客观」处理，与 §7「客观定论跳过 judge」语义暂偏

设计 §7 把 `test_script` 列为客观定论（跳过 judge）。本事务不做 `test_script`（需代码执行沙箱），计划 §4/§7 风险 5 已明确「未知 type 视为无客观 → 跑 judge」。这是**已知延后**、可接受，但应登记：带 `test_script` 的 BenchmarkTask 在 0006 阶段会被误跑 judge（多花一次 judge 且 `eval_basis` 不符），待 `0007` Benchmark 事务补客观执行。

---

## 4. 需要验证的假设（附建议的确认方式）

### 4.1 judge 模型 ≠ 执行模型（§7 显式要求，本事务拟简化）——最重要

- 设计 §7 **明确**要求「用与执行不同的另一个模型当裁判（同模型有自偏好偏差）」。计划 §5.2 拟用同一 `LLMClient`/`config.LLM_MODEL`，登记为「已知简化」，并问评审「是否加 `LLM_JUDGE_MODEL`」。
- **确认方式**：由用户/优化者裁定二选一——(a) 接受同模型简化（登记已知局限，`judge` 与执行共用 `LLM_MODEL`）；(b) 引入 `LLM_JUDGE_MODEL` 常量（属 config 变更，与 §6「无 config 变更」冲突，需一并改）。**这是本事务唯一对设计显式要求的实质性偏离，不得静默滑过。**

### 4.2 `chat_json` 的强制 JSON 机制（`response_format` vs prompt 指令）

- 设计 §7 说「强制 JSON 输出（`response_format` 或解析兜底）」。计划 §5.1 把「`response_format={"type":"json_object"}` vs prompt 指令」交优化者定，理由需兼顾 DeepSeek 兼容（可能不支持 `response_format`）。
- **确认方式**：优化者择一，并保证「解析兜底」（提取首个平衡 `{...}`）作为统一回退，测试覆盖纯 JSON / 带前后缀 JSON / 非 JSON 抛错。

### 4.3 confidence 过滤阈值（设计 §9 要求过滤，值未定）

- 设计 §9「按 confidence 过滤低置信度」未给具体阈值。计划 §5.3「阈值由优化者定」，但 §6 又写「无 config 变更」——若阈值入 `config.py`（与其它阈值一致的做法）则需改 config。
- **确认方式**：优化者定阈值数值与落点（`experience.py` 硬编码 vs `config` 常量），并消除与「无 config 变更」的措辞冲突。

### 4.4 `category`/`target_section` 枚举校验

- 设计 §8 给出 `category` 七值、`target_section` 三值。验收 §9.6「category/target_section 合法」的「合法」未具体化：extractor 是否校验/归一化 LLM 输出到枚举？LLM 返回非法值时行为？
- **确认方式**：优化者钉死「校验 + 非法值处理（丢弃该条 / 置默认 / 抛错）」，并让验收可判定。

---

## 5. 总体结论

**该计划可以进入优化（Optimizer）阶段。** 计划结构完整（10 小节齐全且具体）、正确复用 `0004` 预留的 `chat_json` 扩展点、`Evaluator` 四分支 `eval_basis` 与设计 §7 的融合/`passed` 三态**整体一致**、范围控制良好（Benchmark 顺延 0007 有充分理由、test_script 延后、无新增依赖、无抽象膨胀）、分层正确（`Evaluator` 只调 `llm`/`eval_store`，`ExperienceExtractor` 只调 `llm`、纯返回不写库）。**无事实性硬错。**

**进入 `task.md` 前，优化者必须裁定 / 钉死以下问题：**

1. **[必裁] judge 模型分离**（§4.1）：接受同模型简化并登记，还是引入 `LLM_JUDGE_MODEL`（连带改 §6「无 config 变更」）。
2. **[必钉] 融合数值细节**（§3.1/§3.2/§3.3/§3.4）：`objective_score` 的 exact/contains 映射、补「contains+无 rubric」分支、`exact`/`contains` 比较目标（`objective_check["value"]`）、`objective` dict / `judge_score` 跳过记 0 / 客观失败 `total_score` 的填充口径。
3. **[必钉] `chat_json` 机制**（§4.2）与 **confidence 阈值**（§4.3，含 config 措辞冲突）。
4. **[必钉] 字段完整性**：`Experience.summary`（§2.1）与 `category`/`target_section` 校验口径（§4.4）；`llm.py` docstring 同步更新（§2.2）。

**未发现的问题**：`Evaluator`+`ExperienceExtractor`+`chat_json` 同属评估层核心（Extractor 消费 Evaluator 产物、二者共用 chat_json），捆绑合理非蔓延；`evaluate(trace, task, *, reference_answer, rubric, objective_check)` 以参数承接 Benchmark 的字段（而非读 Benchmark），与 §7 签名一致、且 Benchmark 顺延 0007 后由 Validator 取参传入，衔接正确；无新第三方依赖、回归风险低（`llm.py` 仅加方法，`complete`/`complete_with_usage` 行为不变）。
