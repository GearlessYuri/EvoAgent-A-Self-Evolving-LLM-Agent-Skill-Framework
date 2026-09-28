# 事务 0001 评审（Review）

> 评审者（Reviewer）产出。按 `roles/reviewer.md` 要求，每条发现归入「已确认的问题 / 可能存在的风险 / 需要验证的假设」三类之一。
> 评审依据：实际仓库现状 + `docs/system_design.md` + `.agents/` 状态与协议文件，而非仅凭计划文本。

- 事务 ID：`0001`
- 评审日期：2026-09-26
- 评审对象：`plan.md`（规划者产出）

---

## 0. 评审方法与实际核实记录

本次评审做了以下**实仓核实**，而非仅阅读计划文本：

| 核实项 | 方法 | 结果 |
|---|---|---|
| 仓库现状 | `find` 全量遍历 | 仅 `.agents/` + `docs/system_design.md`，**无任何 `.py`、`pyproject.toml`、`requirements.txt`、`tests/`** —— 计划「纯文档仓库、业务代码为零」成立 |
| dataclass 数量 | `grep "@dataclass"` | **恰好 8 个**（`FewShot` `ToolSpec` `Skill` `TraceStep` `ExecutionTrace` `EvaluationResult` `Experience` `BenchmarkTask`） |
| 表清单一致性 | `grep`（skills/traces/trace_steps/evals/experiences） | 设计内部不一致：§13 的 `evoagent.db` 注记只列 4 表，§3.3 与 §13 文件表写「evals / experiences 表门面」 |
| Python / pytest 环境 | `python --version`、`python -m pytest --version` | `Python 3.13.9`、`pytest 8.4.2`，`python -m pytest` 可用 |
| 事务文件实际位置 | `find` | 事务文件在 `.agents/transactions/0001/`，**不在**顶层 `transactions/0001/` |

---

## 1. 计划完整性核对（planner.md 要求的 10 小节）

planner.md 要求的 10 个小节，`plan.md` **全部具备、且内容具体可执行**：

| # | 要求小节 | 是否具备 | 是否具体（非空话） |
|---|---|---|---|
| 1 | 当前状态 | ✅ | ✅ 基于 `find` 实况，逐项列出存在/不存在 |
| 2 | 问题 | ✅ | ✅ 给出 3 条证据（依赖单向性 / 无地基 / 无可验证迭代） |
| 3 | 目标 | ✅ | ⚠️ 具体，但含「9 个 dataclass」数量错误（见 §2.1） |
| 4 | 范围 | ✅ | ✅ 做/不做边界清晰，非目标明确列出 `llm.py`、门面层、上层、LLM 调用、第三方依赖 |
| 5 | 拟议变更 | ✅ | ⚠️ 逐文件列表，但同样重复「9 个 dataclass」错误 |
| 6 | 依赖 | ✅ | ✅ 运行时/测试/顺序/前置条件齐全 |
| 7 | 风险 | ✅ | ✅ 5 条风险均附缓解；其中「表清单不全」已主动识别设计歧义 |
| 8 | 实施顺序 | ✅ | ✅ 7 步，顺序与依赖关系（models→config→storage→tests）一致 |
| 9 | 验收标准 | ✅ | ⚠️ 7 条客观可判定，但第 2 条「9 个 dataclass」错误 |
| 10 | 验证策略 | ✅ | ✅ 给出具体命令 + 4 条验证要点 |

结论：结构完整。唯一硬伤是「9 个 dataclass」这一数字错误在 §3/§5/§9 三处反复出现。

---

## 2. 已确认的问题（对照仓库/设计核实成立）

### 2.1 「9 个 dataclass」数量错误（计划 §3、§5、§9）

- **事实**：`docs/system_design.md` 全文仅定义 **8 个** dataclass —— §5 `FewShot` / `ToolSpec` / `Skill`，§6 `TraceStep` / `ExecutionTrace`，§7 `EvaluationResult`，§8 `Experience`，§11 `BenchmarkTask`。已用 `grep "@dataclass"` 核实。
- **计划的错误**：§3「9 个 dataclass」、§5「…共 9 个 dataclass」、§9 验收标准第 2 条「定义设计 §5–§11 的 9 个 dataclass」。且 §5 自己列出的清单只有 8 个名字，自相矛盾。
- **后果**：若编码者照「9 个」执行，会为凑数捏造一个设计中不存在的第 9 个 dataclass（最可能被误加的是 `Task`，而设计并未定义 `Task` 的数据结构，见 §4.3）；或验收标准 §9.2 永远无法满足。
- **处置**：优化者必须将全部「9 个」更正为「8 个」。

### 2.2 事务目录路径不一致（跨文档，非计划代码范围，但影响工作流可追溯性）

- **事实**：实际事务文件位于 `.agents/transactions/0001/`。但以下位置均指向**顶层** `transactions/0001/`：`active_transaction.md` 的「相关文件」、`workflow/transaction_protocol.md`、`workflow/state_protocol.md`、`.agents/transactions/README.md`、以及本次评审任务的指令本身。
- **后果**：后续代理按文档找 `transactions/0001/plan.md` 会落空。本评审已按实际情况写入 `.agents/transactions/0001/review.md`。
- **处置**：这是工作区文档层的一致性问题，不属于本事务代码范围；建议在优化或后续事务中统一路径口径，至少更正 `active_transaction.md` 的「相关文件」两条路径为 `.agents/transactions/0001/…`。

---

## 3. 可能存在的风险（有迹象，未完全核实）

### 3.1 `trace_steps.content` 的截断与 `truncated` 列被遗漏

设计 §6 明确要求：`content` 超 4000 字符截断存储并置 `truncated=True`。该 `truncated` 字段**不在** `TraceStep` dataclass 定义里，也不在计划的任何表/字段清单中。计划 §4 只说 storage.py「以设计字段为准」建表，但未提及 `truncated` 列与 4000 字符截断规则。编码者极可能漏掉。**建议** task.md 明确 `trace_steps` 含 `truncated` 列（布尔，默认 false）及截断规则落点。

### 3.2 SQL 表 schema 未细化，且现有验证存在循环性

计划只给表清单，未给列名/类型/约束/外键（如 §6 要求 `trace_steps` 以 `trace_id` 为外键；`skills` 表列清单见 §5）。§10 的 `test_storage` 验证是「插入一条再查回、字段一致」的自洽 round-trip，**无法**发现「列名与设计字段名不一致」这类 drift —— 测试与实现共用同一 schema 时是循环论证。**建议** task.md 给出各表关键列清单，并要求测试用 `PRAGMA table_info(...)` 断言关键列，锁定 schema 防止漂移（计划 §7 已把「Schema 与设计漂移」列为头号风险，但 §10 的验证手段未真正覆盖它）。

### 3.3 嵌套 dataclass 的序列化/反序列化边界未定义

`Skill` 含 `list[FewShot]` / `list[ToolSpec]`，`ExecutionTrace` 含 `list[TraceStep]` 与 `usage: dict = None`，`EvaluationResult.passed` 为 `bool | None`。验收标准 §9.3 的「round-trip 字段值不丢、类型正确」未覆盖：嵌套对象如何递归重建、`None` 与空列表如何区分、`bool | None` 如何判别。若编码者只做浅层 `to_dict`，嵌套 dataclass 会在 round-trip 后退化为 dict、类型丢失。**建议** task.md 明确「递归序列化 + None/空集/联合类型」的处理要求与对应测试用例。

### 3.4 `requirements.txt` 偏离设计 §13，且未显式说明

设计 §13 的 `requirements.txt` 注释为 `openai / anthropic / numpy / pytest`；计划只写 `pytest`（openai/anthropic/numpy 属 llm.py/retriever 范围，随功能延后）。方向合理、符合设计「最小依赖」原则，但这是对设计原文的**未声明偏离**。**建议** task.md 显式记录「openai/anthropic/numpy 于后续 llm.py/检索事务再引入」，避免后续事务误判依赖已齐全。

### 3.5 `data/` 目录与默认 DB 路径的初始化行为未定义

计划 §5 config.py 含「默认数据目录」，storage.py `connect()` 需默认 DB 路径，但未说明：是否/如何创建 `data/` 目录、DB 文件名、`connect()` 是否自动创建父目录（mkdir -p 语义）。测试用 `tmp_path` 隔离（§7 已覆盖），但**生产默认路径**的创建行为未定义。**建议** task.md 明确 `connect()` 自动创建父目录、默认 DB 路径与文件名。

---

## 4. 需要验证的假设（计划依赖、尚未核实，附验证方法）

### 4.1 `experiences` 表是否应建（计划已主动识别，但需裁定）

- **现象**：设计内部不一致。§13 `evoagent.db` 注记只列 `skills / traces / trace_steps / evals` 4 表；但 §3.3 与 §13 文件表均写「EvalStore：evals / experiences 表门面」，§8 定义 Experience、§9 要求写 `category="failed_evolution"` 的 Experience。计划选择建 5 表（含 `experiences`），方向正确，且已在 §7 风险中主动标注此歧义。
- **验证/裁定方法**：以 §3.3 + §8 + §9 为准（Experience 必须持久化，否则失败演化无法复盘），确认 **5 表**（`skills` / `traces` / `trace_steps` / `evals` / `experiences`）。建议优化者在 task.md 中裁定为 5 表，并顺带在后续更正 §13 注记。

### 4.2 Python / pytest 环境前置条件

计划 §6 假设「本机 Python 3.10+ 与 pytest」。**已核实**：`python` = 3.13.9（≥3.10）、`python -m pytest` = 8.4.2，均可用。§7 的「环境缺失」风险实际较低，§10 验证命令可直接运行。

### 4.3 `Task` 数据结构在设计中的缺失（前瞻性，非本事务范围）

设计全文引用 `Task`（§1/§3.2/§4）却从未给出其 dataclass 字段定义（仅 `BenchmarkTask` 有定义）。本事务不含 `Task` 是**正确**的（`Task` 不在 §5–§11 的 dataclass 清单内），但优化者应知悉：后续 executor/retriever 事务将需要 `Task` 的 schema，设计此处有缺口，届时需回补设计而非凭空捏造。

### 4.4 git 未初始化与设计的 git 依赖

设计 §10/§11/§13 多处依赖「git 追踪 JSON / 可视化 diff」（如 Skill 版本内容 diff）。当前仓库**非 git 仓库**（环境信息确认）。本事务不涉及 git 依赖（不产生 JSON 内容文件），不阻塞；但后续 SkillRegistry / 版本化事务会触及，属未满足的设计前提，优化者应知悉。

---

## 5. 总体结论

**该计划可以进入优化（Optimizer）阶段**，但存在一个必须在优化阶段修正的硬性事实错误，以及若干需优化者明确/裁定的点。

**必须先解决的问题清单（进入 task.md 前）**：

1. **[硬性] 更正 dataclass 数量**：将计划 §3/§5/§9 三处「9 个 dataclass」全部改为「8 个」，并把 §5 的清单与验收标准 §9.2 对齐为 8 个 dataclass（`FewShot` `ToolSpec` `Skill` `TraceStep` `ExecutionTrace` `EvaluationResult` `Experience` `BenchmarkTask`）。此错误出现在验收标准中，会直接误导编码者或使验收无法判定。

**建议优化者一并裁定/明确（非阻塞，但应写入 task.md）**：

2. 裁定表清单为 **5 表**（含 `experiences`），并明确 `trace_steps` 的 `truncated` 列与 4000 字符截断规则（§3.1、§4.1）。
3. 给出各表关键列清单，并要求 `test_storage.py` 用 `PRAGMA table_info` 断言关键列（§3.2）。
4. 明确嵌套 dataclass 的递归序列化与 `None`/空集/`bool|None` 处理（§3.3）。
5. 显式声明 `openai/anthropic/numpy` 延后引入、`config.py` 的 LLM 参数取舍、`data/` 目录与默认 DB 路径的创建行为（§3.4、§3.5）。

**未发现的问题**：范围控制良好（无范围蔓延、无不必要抽象/依赖）；实施顺序与依赖关系自洽；除 §9.2 外验收标准均可客观判定；与 `docs/system_design.md` 及 `.agents/` 状态文件在**事务目标层面**一致（底座层 = models/config/storage，不含 llm.py 与上层）。
