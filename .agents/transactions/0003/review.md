# 事务 0003 评审（Review）

> 评审者（Reviewer）产出。按 `roles/reviewer.md` 要求，每条发现归入「已确认的问题 / 可能存在的风险 / 需要验证的假设」三类之一。
> 评审依据：实际仓库（`0001`/`0002` 落地后的源码）+ `docs/system_design.md` + `.agents/` 状态文件 + `0002/result.md`，而非仅凭计划文本。

- 事务 ID：`0003`
- 评审日期：2026-09-28
- 评审对象：`plan.md`（规划者产出）

---

## 0. 评审方法与实际核实记录

| 核实项 | 方法 | 结果 |
|---|---|---|
| `Task` 是否存在 | 读 `models.py` + `test_models.py` | `models.py` 无 `Task`；`test_models.py` 的 `ALL_DATACLASSES` 硬编码 8 个、`test_eight_dataclasses_defined` 断言 `len==8` |
| `SkillRegistry.list`/`get_active` 签名 | 读 `skills/registry.py` | `list(tags=None) -> list[Skill]`（全部 active、按 skill_id 升序、完整对象含 description/tags）；`get_active(skill_id) -> Skill | None` |
| 检索字段是否可读 | 读 `registry.py` | `name`/`description`/`tags` 已落 SQLite（0002 加列），`list()`/`get_active()` 返回的 `Skill` 带三者 |
| 检索阈值常量 | 读 `config.py` | `RETRIEVAL_FALLBACK_THRESHOLD = 0.3` 已存在；计划复用、未另起炉灶 |
| git / 测试现状 | `git log`/`git status`/`pytest` | HEAD `810b9d1`（main）；`git status --short` 显示 `active_transaction.md`/`project_state.md` 已改、`0003/` 未跟踪（**工作树非干净**）；全量 `52 passed` |
| 设计 §3.2 原文 | 读 `docs/system_design.md` | 「`Task → top-k (skill_id, version, score)`」「关键词 / TF-IDF + 余弦」「加 tag 过滤」「余弦 < 0.3 走内置 default skill + `retrieval_fallback=True`」 |
| coder 写范围 | 读 `roles/coder.md` / `protocol.md` | 写 = **源代码 + 测试 + execution.md / result.md**；不含 `docs/` |

---

## 1. 计划完整性核对（planner.md 要求的 10 小节）

10 个小节**全部具备、内容具体可执行**：

| # | 要求小节 | 是否具备 | 是否具体 |
|---|---|---|---|
| 1 | 当前状态 | ✅ | ✅ 准确：存储层完整、执行层为零、Task 缺失、retriever 缺失 |
| 2 | 问题 | ✅ | ✅ 4 条证据，含「检索质量是执行质量上限」与 llm.py 优先级对比 |
| 3 | 目标 | ✅ | ✅ Task 回补 + SkillRetriever 简单版，耦合合理（retriever 入参即 Task） |
| 4 | 范围 | ✅ | ✅ 做/不做边界清晰；docs 修改明确标「需裁定」；embedding/llm.py/Executor/种子写库均排除 |
| 5 | 拟议变更 | ✅ | ✅ 逐文件 + §5.1/§5.2 细化 Task 字段与 retriever 接口 |
| 6 | 依赖 | ✅ | ✅ 运行时（re/math 标准库）、顺序、对 0002 门面/0001 常量的依赖 |
| 7 | 风险 | ✅ | ✅ 7 条均附缓解，Task 缺口/评分复杂度/兜底/空表/k 边界/蔓延/序列化均有覆盖 |
| 8 | 实施顺序 | ✅ | ✅ 5 步，Task→retriever→测试→(可选)docs→验证 |
| 9 | 验收标准 | ✅ | ✅ 8 条客观可判定，含分层 grep、兜底、tag、不越界、全量回归 |
| 10 | 验证策略 | ✅ | ✅ 命令 + 逐用例清单 + grep 人工复核 |

结论：结构完整，无 0001「9 个 dataclass」式事实笔误。问题集中在**Task 字段这一设计级开放项**与**若干接口/评分细节的钉死**。

---

## 2. 已确认的问题（对照仓库核实成立）

### 2.1 追加 `Task` 后，`test_models.py` 的「8 个 dataclass」硬编码与 docstring 双重失准

- **已核实**：`test_models.py:18–34` 的 `ALL_DATACLASSES` 是**硬编码的 8 个 dataclass 列表（不含 `Task`）**，`test_eight_dataclasses_defined` 断言 `len(ALL_DATACLASSES) == 8`；`models.py` 模块 docstring 写「8 个 dataclass / §5–§11」。
- **后果**：本事务追加第 9 个 dataclass `Task` 后——(a) 该测试**不会失败**（列表硬编码，`Task` 不在其中），但「恰好 8 个 dataclass」的断言名与语义**变为错误**；(b) `models.py` docstring 的「8 个」「§5–§11」双双失准（`Task` 既非 8 个之一，也不来自 §5–§11）。
- **测试位置不一致**：计划 §10 把 `Task` round-trip 放进 `test_retriever.py`，而其余 8 个 dataclass 的 round-trip 全部在 `test_models.py`——放置方式与既有约定割裂。
- **计划未处理**：§9.1 只说「既有 8 个 dataclass 不动」、§9.8 只要求「52 项无回归」，未提这个「8 个」硬编码。
- **建议**：优化者钉死——(a) 将 `Task` 加入 `ALL_DATACLASSES`、把 `test_eight_dataclasses_defined` 更名为「全部 dataclass」并把 `Task` round-trip 移入 `test_models.py`（与既有约定一致）；或 (b) 显式保留 `Task` round-trip 在 `test_retriever.py`，同时更新 `models.py` docstring 与测试名为「8（§5–§11）+ Task」。**不得无声漂移。**

### 2.2 拟议修改 `docs/system_design.md` 超出编码者写范围（计划已自标「需裁定」，此处确认）

- **已核实**：`roles/coder.md` 与 `workflow/protocol.md` 中编码者写范围 = **源代码 + 测试 + execution.md / result.md**，**不含 `docs/system_design.md`**。`docs/system_design.md` 在本工作流中是只读的业务/设计文档。
- **计划的处理**：§4 第 4 项、§5 表、§7 风险 1 均把「补写 `docs/system_design.md` 的 Task 定义」标为「需裁定」，并正确引用「coder.md 写范围不含 docs」。这是**正确识别**。
- **一致性（若真要改）**：计划提议的 `Task(task: str, task_source: str, task_id: str = "")` 与既有 §5–§11 dataclass 风格一致（snake_case、`str` 字段、可选字段给默认值），且与 §6 `ExecutionTrace.task_id`/`task_source`、§11 `BenchmarkTask.task` 相呼应，**风格上不冲突**。
- **建议**：默认**不修改** `docs/system_design.md`（登记「设计文档仍缺 `Task` 定义」为已知局限，与 0002 对 `truncated` 的处理一致）；若要改，须由用户/人工拍板并明确「由谁、在哪个非编码环节写」，不得交由编码者在本事务落笔。

---

## 3. 可能存在的风险（有迹象，未完全核实）

### 3.1 `RetrievalHit` / `RetrievalResult` 是计划自创类型，设计未定义，形式未定

- 设计 §3.2 只说返回 `(skill_id, version, score)` 与「default skill 兜底」，**未定义** `RetrievalHit` / `RetrievalResult`。计划 §5.2 提出这两个类型却只写「具体返回类型由优化者钉死」。
- **风险**：若把它们做成 `models.py` 的新 dataclass，会追加第 10/11 个 dataclass，进一步放大 2.1 的「dataclass 数量漂移」；若做成 `retriever.py` 内 NamedTuple / 普通对象则更轻。需优化者钉死其**形式与所在文件**（建议：`retrieve` 返回 `list[tuple[str, str, float]]` 或 retriever 内 `NamedTuple`；`retrieve_top1` 返回一个轻量结果对象，**不进 `models.py`**）。

### 3.2 评分算法与「除零」边界未钉死

- 计划默认「词频向量 + 余弦」，把 TF-IDF 加权列为「可选、默认不做」。这与 §3.2「关键词 / TF-IDF + 余弦」的「关键词」档**等价、可接受**，但需优化者明确裁定（词频 vs TF-IDF）。
- **除零/空向量边界**：任务文本与所有 skill 的 `description` **无任何共享 token**、或某 skill `description` 为空串时，余弦相似度分母为 0 → **除零/未定义**。计划 §7 风险 4 只覆盖「空注册表」，未覆盖「非空注册表但零共享 token」「空 description」。需在实现与测试中显式处理（如：零范数时相似度按 0 计）。

### 3.3 `tag 过滤` 的语义与来源未定，且「可裁为不做」偏离设计明文

- 设计 §3.2 **明文**要求「加 tag 过滤」。计划 §5.2 选「可选 `tags` 参数」并自评「若评审者认为过早可裁为不在本事务」——但**完全砍掉会偏离设计明文**。
- 未钉死的是：tag 来源是「Task 携带」还是「retrieve 参数」。计划选后者（复用 `registry.list(tags=...)` 交集语义），方向合理；建议**保留**（可选参数）并钉死「交集过滤」语义，而非砍掉。

### 3.4 `retrieve`（top-k）与 `retrieve_top1`（top-1+兜底）的拆分关系未定义

- 设计 §4 写「`retrieve(task)` → top-1…低于阈值走 default」，把**兜底并入检索**。计划拆成 `retrieve(k)`（无兜底）与 `retrieve_top1`（带兜底）两方法，但未说明：`retrieve(k=1)` 是否也应兜底？`retrieve_top1` 是否内部调用 `retrieve(1)`？二者关系需钉死，否则 `AgentExecutor`（未来调用方）不知该调哪个。

### 3.5 `name`/`tags` 进评分信号是计划自创（设计只说 `description` 供检索）

- 设计 §3.2 只提「语义描述（description）供检索」。计划 §5.2「可含 name + tags 作补充权重」是**范围外扩**。属轻微，但需优化者裁定：默认仅 `description` 评分，还是明确纳入 name/tags。

### 3.6 `models.py` docstring 双重失准（见 2.1）

追加 `Task` 后，「8 个 dataclass / §5–§11」在数量与来源章节上都失准，须一并更新（与 2.1 同一处置）。

---

## 4. 需要验证的假设（附建议的确认方式）

### 4.1 `Task` 字段的「设计依据」与「计划自创」之分（本事务唯一真正的设计级开放项）

逐字段裁定如下：

| 字段 | 可推出 / 自创 | 依据 |
|---|---|---|
| `task: str`（任务文本） | **可推出**（风险低） | §3.2「按任务语义挑」、§4「Task 进入 CLI/Loop」、§11 `BenchmarkTask.task` 类比 |
| `task_source: str` | **可推出**（风险低） | §4 step1「打来源标签 task_source」、§6 `ExecutionTrace.task_source` |
| `task_id: str = ""` | **自创（需拍板）** | 设计**从未说 Task 携带 id**——§4 只给 Task 打 `task_source` 标签，未打 `task_id`；§6 `ExecutionTrace.task_id` 存在，但该 id 来自 Task 还是执行时生成，设计未写明 |

- **结论**：`task` 与 `task_source` 有设计依据，可视为成立；`task_id` 是计划**自行发明**的字段，**不得当作既成设计放行**。
- **建议的确认方式**：由用户/人工拍板，或优化者对照 §4/§6 的关联需求在 `task.md` 显式裁定为二选一——(a) `Task` 携带可选 `task_id`（默认空，执行时生成）；(b) `Task` **不含** `task_id`，由 `AgentExecutor` 在写 `ExecutionTrace` 时生成。**无论哪条，都应在 `task.md` 记录为「已确认的 Task 定义」**，避免下一事务再翻案。

### 4.2 是否在本事务修改 `docs/system_design.md`

见 §2.2。**建议默认不修改**（登记为已知局限）；若要改，需用户/人工批准并明确执行环节。这本身是一个「需用户拍板」的开放项，与 4.1 的 `task_id` 一起，是进入 `task.md` 前必须解决的仅有的两个「设计级」问题。

### 4.3 已核实的前提（报告结果，消除不确定性）

- **git**：HEAD `810b9d1`（main）✅ 与计划 §1 一致；但 `git status --short` 非空（state 文件已改、`0003/` 未跟踪），计划 §1「工作树干净」**已过时**（轻微，同 0002）。
- **测试**：全量 `52 passed` ✅ 与计划 §1「52 项」一致。
- **门面接口**：`SkillRegistry.list(tags=None)` / `get_active` ✅ 与计划 §1/§5.2 依赖一致，返回完整 `Skill`（含 `description`/`tags`）。
- **检索常量**：`config.RETRIEVAL_FALLBACK_THRESHOLD = 0.3` ✅ 计划复用，未另起炉灶。

---

## 5. 总体结论

**该计划可以进入优化（Optimizer）阶段。** 计划结构完整（10 小节齐全且具体）、范围控制良好（embedding/llm.py/AgentExecutor/种子写库/git 均明确排除、无新增第三方依赖）、正确衔接 `0002/result.md`（执行层第一步 + 回补 Task），且对 `Task` 字段的设计级风险**已主动标注「供评审核实、勿视为最终结论」**——这是正确姿态。**无 0001 式的硬性事实错误。**

**进入 `task.md` 前，优化者必须裁定 / 钉死以下问题：**

1. **[必裁，设计级] `Task.task_id` 是否存在于 `Task`**：这是本事务唯一真正的设计开放项（`task`/`task_source` 有依据，`task_id` 是自创）。需用户/人工拍板或优化者在 `task.md` 显式裁定，并记录为「已确认的 Task 定义」（§4.1）。
2. **[必裁，设计级] `docs/system_design.md` 是否修改**：默认不修改（登记已知局限）；修改超出编码者写范围，须用户批准（§2.2）。
3. **[必钉] `test_models.py`「8 个 dataclass」硬编码/docstring 的漂移**：追加 Task 后须更新 `ALL_DATACLASSES`、测试名与 `models.py` docstring，并定 `Task` round-trip 的位置（§2.1）。
4. **[必钉] retriever 接口细节**：`RetrievalHit`/`RetrievalResult` 的形式与位置（勿入 models.py）、`retrieve`/`retrieve_top1` 拆分关系、`tag 过滤` 语义（保留交集过滤）、评分信号（仅 description vs +name/tags）、除零/空 description 边界（§3.1–§3.5）。

**未发现的问题**：分层约束（retriever 只读 `SkillRegistry`、不 import sqlite3/不直接 Storage）正确；复用 `RETRIEVAL_FALLBACK_THRESHOLD` 正确；回归风险低（models.py 仅追加、无表结构变更、无依赖方被破坏）；「简单版纯标准库、零依赖、确定性」符合 §14 最小依赖与「不引入复杂度」原则。
