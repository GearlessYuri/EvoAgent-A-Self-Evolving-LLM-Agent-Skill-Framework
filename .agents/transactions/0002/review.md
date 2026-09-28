# 事务 0002 评审（Review）

> 评审者（Reviewer）产出。按 `roles/reviewer.md` 要求，每条发现归入「已确认的问题 / 可能存在的风险 / 需要验证的假设」三类之一。
> 评审依据：实际仓库（含 `0001` 落地后的源码）+ `docs/system_design.md` + `.agents/` 状态文件 + `0001/result.md`，而非仅凭计划文本。

- 事务 ID：`0002`
- 评审日期：2026-09-28
- 评审对象：`plan.md`（规划者产出）

---

## 0. 评审方法与实际核实记录

| 核实项 | 方法 | 结果 |
|---|---|---|
| 底座层源码 | 读 `evoagent/models.py` / `config.py` / `storage.py` | 已存在；8 dataclass + `_Serializable` 递归序列化、`Storage` 5 表 + 参数化 CRUD |
| `skills` 表列 | 读 `storage.py` `_SCHEMA` | `skill_id, version, status, parent_version, change_log, metrics, created_at, updated_at` —— **无 `name`/`description`/`tags`** |
| `trace_steps` 列 | 读 `storage.py` | 含 `truncated INTEGER NOT NULL DEFAULT 0`，**截断逻辑未实现** |
| JSON 反序列化现状 | 读 `storage.py` `query()` | `query` 返回原始值，JSON 列以 TEXT 字符串返回（**未 `json.loads`**）；`insert`/`update` 侧 `_serialize_value` 已 `json.dumps` |
| `config.py` 常量 | 读 `config.py` | 仅 `DATA_DIR`/`DB_PATH`/4 阈值权重/`SQLITE_WAL_ENABLED`；**无 `SKILLS_DIR`、无截断阈值** |
| 门面包是否已存在 | `find` | `evoagent/` 下无 `skills/`/`execution/`/`eval/` 子包，三门面均未实现 |
| git 状态 | `git rev-parse` / `git log` / `git branch` | **git 已初始化**：`main`，HEAD `78d505e`；`git status --short` 显示 `active_transaction.md`/`project_state.md` 已改、`0002/` 未跟踪 |
| `.gitignore` | 读文件 | 忽略 `*.db`/`*.sqlite3`，**不忽略 `data/`**（注释明确「Skill JSON 归档需纳入 git」） |
| 既有测试 | `python -m pytest tests/ -q` | **26 passed**（底座层绿） |
| `data/` 目录 | `ls` | 不存在（门面运行时按需创建，符合计划） |

---

## 1. 计划完整性核对（planner.md 要求的 10 小节）

10 个小节**全部具备、内容具体可执行**：

| # | 要求小节 | 是否具备 | 是否具体 |
|---|---|---|---|
| 1 | 当前状态 | ✅ | ✅ 准确描述底座层现状与两处后置逻辑 |
| 2 | 问题 | ✅ | ✅ 5 条证据（无门面 / JSON 未反序列化 / 截断缺失 / 状态机缺失 / 归档缺失） |
| 3 | 目标 | ✅ | ✅ 三门面 + 闭合两处后置，边界清晰 |
| 4 | 范围 | ✅ | ✅ 做/不做逐条列出，非目标含 llm.py、上层模块、Task、git 提交 |
| 5 | 拟议变更 | ✅ | ✅ 逐文件 + 三小节细化接口（§5.1/§5.2/§5.3） |
| 6 | 依赖 | ✅ | ✅ 运行时/顺序/前置/对 0001 的依赖齐全 |
| 7 | 风险 | ✅ | ✅ 7 条风险均附缓解，主动识别 name/tags 缺口与 Task 遗留 |
| 8 | 实施顺序 | ✅ | ✅ 7 步，依赖少的 TraceStore 先做、最复杂 SkillRegistry 最后 |
| 9 | 验收标准 | ✅ | ✅ 7 条客观可判定，逐门面列出往返 / 不变量 / 越界检查 |
| 10 | 验证策略 | ✅ | ✅ 具体命令 + 逐文件用例清单 + grep 人工复核 |

结论：结构完整，无「9 个 dataclass」式的事实性笔误（§1 正确写「8 个」）。主要问题集中在两处**设计缺口**的裁定与若干**接口边界**的钉死。

---

## 2. 已确认的问题（对照仓库核实成立）

### 2.1 `Skill` 的 `name` / `description` / `tags` 持久化位置是真实设计缺口，计划的默认裁定（放 JSON）有可核实的代价

- **已核实**：`0001` 落地的 `skills` 表**没有** `name`/`description`/`tags` 列（`storage.py` `_SCHEMA` 可证）；`docs/system_design.md` §5 的两份持久化清单（SQLite 元数据 = `skill_id, version, status, parent_version, change_log, metrics, timestamps`；JSON 内容 = `prompt_template, few_shots, tools`）**均未列出**这三个字段，而 `Skill` dataclass 有它们。这是设计缺口，计划在 §5.1 与 §7 风险 1 中**正确识别**了它。
- **计划的默认裁定**：三者写入 JSON 归档（与 `prompt_template`/`few_shots`/`tools` 同文件），`list(tags=...)` 据此加载内容过滤，理由「零 schema 迁移、JSON 自足」。
- **已确认的代价**：`name`/`description`/`tags` 是**高频查询字段**——`list(tags=...)`（§3.1）、`description` 语义检索（§3.2）、tag 过滤（§3.2）都依赖它们。放 JSON 意味着每次过滤 / 检索都要**打开全部 JSON 文件**（O(N) 文件读取），这与设计 §5 自己的原则「元数据要频繁查询/统计（放进 SQLite）」相悖。
- **注意**：放 JSON 同样是对 §5 的偏离——§5 的 JSON 内容清单只有 3 个字段，把 `name`/`description`/`tags` 塞进去也是「扩清单」；放 SQLite 则是「加 3 列」。**两条路都偏离 §5 原文**，因此必须由优化者做**显式裁定并记录**，不能默认滑过去。
- **建议**：优化者在 `task.md` 中二选一——(a) 接受 JSON 裁定（保持表结构不变、接受 O(N) 过滤，明确记录为 v1 取舍）；或 (b) 裁定为 SQLite 列（`skills` 表加 3 列，需一次 schema 迁移，更符合 §5「元数据好查询」原则与 §3.2 检索需求，但要改动 `storage.py` 的 `_SCHEMA`，与计划 §6「不改 storage.py 通用契约」冲突，需一并裁定）。**无论哪条，都必须落到验收标准**：`list(tags=...)` 与 `get()` 的重建逻辑、测试断言都要与该裁定一致。

### 2.2 `truncated` 标志不在数据契约中，`get()` 无法向调用方暴露「内容已被截断」

- **已核实**：`TraceStep` dataclass（`models.py`）**无 `truncated` 字段**；设计 §6 的 `TraceStep` 也没有，`truncated` 只存在于持久化层（`trace_steps.truncated` 列）。这是**设计本身的缺口**，计划忠实照搬（未给 `TraceStep` 加字段）。
- **已确认的后果**：`TraceStore.save()` 截断并置位 `truncated=1` 后，`get(trace_id)` 重建的 `TraceStep` **只带截断后的 `content`，无任何标志**——调用方（未来的 Evaluator）无法得知内容被截断。截断信息在往返中**丢失**。
- **对测试的直接影响**：验收标准 §9.4 的「`truncated=1`」无法通过 `get()` 验证（`get()` 返回的对象无此字段），**必须直查 `trace_steps` 表**（`Storage.query("trace_steps", ...)`）才能断言。计划 §10 未点明这一点，编码者可能误用 `get()` 去验 `truncated`，导致测试写不出来或写成「空验证」。
- **建议**：优化者明确——(a) `truncated` 仅作 DB 层防撑爆的保护，不进入数据契约，`test_trace.py` 直查 `trace_steps` 表断言 `truncated` 与截断后长度；或 (b) 若未来 Evaluator 需要，考虑给 `TraceStep` 增加 `truncated` 字段（这会改动 `models.py`，属范围外扩展，需显式批准）。默认走 (a)。

### 2.3 计划 §1 的「工作树干净」与实际 git 状态不符（轻微）

- **已核实**：`git status --short` 显示 `M .agents/state/active_transaction.md`、`M .agents/state/project_state.md`、`?? .agents/transactions/0002/`——工作树**不干净**。计划 §1 写「工作树干净」已过时（这些改动正是 0002 事务自身对状态文件的更新）。
- **影响**：不影响代码方案正确性，但作为「当前状态」陈述不准确。优化者知悉即可，无需改方案。

---

## 3. 可能存在的风险（有迹象，未完全核实）

### 3.1 `register()` 的初始状态语义未定义，可能与 §3.1「Evolver 写候选」冲突

- 计划 §5.1 写「首个版本默认 active」，但设计 §3.1 明确 `SkillRegistry` 被「Evolver（写候选）」调用，§10 状态机含 `draft → candidate → active`。**演化产出的新版本是 draft/candidate，不是 active**，它也要经 `register()` 落库。
- 若 `register()` 无条件「首个版本置 active」，未来 Evolver 无法用它写候选版本（会把候选误置 active）。计划未说明 `register()` 是「尊重 `Skill.status` 字段（status 为空时才默认 active）」还是「无条件强制 active」。
- **建议**：优化者钉死 `register()` 语义——尊重 `skill.status`，仅在 status 为空 / 未显式指定时默认 active；并明确非首版本的登记路径（本事务虽不实现 Evolver，但接口不应给未来留坑）。§9.3 的测试应补一条「register 一个 status=draft/candidate 的版本，其 status 被如实保存，不强制 active」。

### 3.2 `list()` 返回语义与实现代价未定义

- `SkillRegistry.list(tags=...)` 返回 `list[Skill]`：若返回**完整对象**，则需为每个 skill 加载整个 JSON 内容（含 few_shots/tools）只为按 tags 过滤，浪费；且未说明返回**全部版本**还是**仅 active 版本**（检索 §3.2 只关心 active）。
- `TraceStore.list(...)` 返回 `list[ExecutionTrace]`：未说明是否加载 `steps`（若加载，是 N+1 查询；若不加载，返回的 `ExecutionTrace.steps` 为空会误导）。
- **建议**：优化者明确两个 `list()` 的返回粒度（Skill 的版本范围；Trace 是否含 steps），避免编码者臆断。

### 3.3 状态机边界情况未穷举

- `promote`：目标版本已是 active？目标版本不存在（§7 已提「抛异常」）？
- `rollback`：`to_version` 不存在？`to_version` 恰是当前 active（no-op 还是报错）？
- `deprecate`：无 active 时调用？
- `get_active`：无 active 时返回 None 还是抛异常？
- 计划 §7 风险 4 只覆盖「目标不存在抛异常」与「单 active 不变量」，上述边界未列。**建议**：优化者在 `task.md` 中对每个边界给出明确行为（抛异常 / 返回 None / no-op），并让测试覆盖。

### 3.4 若干接口细节未钉死（实现时易臆断）

- **`passed` 三态的 bool↔int 转换**：验收 §9.5 要求「`True`/`False`/`None` 精确保留」，但未指明由门面做 `bool→1/0`、`None→NULL` 及读回的逆转换（`sqlite3` 读回是 `0`/`1`/`None` 的 int/None，不会自动还原为 bool）。
- **`TraceStore.list(since=...)` 的时间列**：未指明用 `started_at` 还是 `ended_at`（`traces` 表两者都有）。
- **`save()` 幂等性**：`traces.trace_id` 是主键，重复 `save()` 同 `trace_id` 是报错还是 upsert？未说明。
- **JSON 归档缺失时 `get()` 的行为**：SQLite 元数据在、JSON 文件不在（人为删除 / 未写完）时，`get()` 报错还是返回部分对象？
- **门面构造签名**：§10 提「SkillRegistry 需支持注入归档根目录」「测试用 `Storage(tmp_path/"x.db")`」，但 §5.1/§5.2/§5.3 未给出三门面的构造参数（如何注入 `Storage` 实例与归档根目录）。优化者应在 `task.md` 明确构造签名，否则测试隔离无法落地。

### 3.5 `data/` 目录与 `.gitignore` 的交互（非阻塞，记录）

- `.gitignore` 忽略 `*.db` 但**不忽略 `data/`**，因此门面落盘的 `data/skills/*.json` 会被 git 视为待跟踪文件（本事务不提交，但 `git status` 会出现它们）。计划 §4「不做 git 提交」已覆盖，编码者执行时 `data/` 会进入未跟踪清单——属预期，非缺陷，仅提示勿误当「范围外残留」处理。

---

## 4. 需要验证的假设（附验证方法）

以下为计划依赖、本次已核实或需优化者裁定的假设：

1. **git 已初始化（JSON 归档前提）** —— **已核实为真**：`main` 分支、HEAD `78d505e`。计划与 `context.md` §4 决策 1 一致，前提成立。
2. **底座层 26 测试通过** —— **已核实为真**：`python -m pytest tests/ -q` → `26 passed`。门面层的回归基线存在。
3. **`.gitignore` 不忽略 `data/`（JSON 归档可被 git 追踪）** —— **已核实为真**：仅忽略 `*.db`/`*.sqlite3`。
4. **`name`/`description`/`tags` 归属（JSON vs SQLite）** —— **未核实、需优化者裁定**，见 §2.1。验证方法：对照 §5「元数据频繁查询放 SQLite」原则 + §3.2 检索对 `description`/`tags` 的依赖，择一裁定并写进 `task.md` 与验收标准。
5. **`register()` 初始状态语义** —— **未核实、需优化者钉死**，见 §3.1。验证方法：核对 §3.1「Evolver 写候选」与 §10 状态机，明确 `register()` 是否尊重 `skill.status`。

---

## 5. 总体结论

**该计划可以进入优化（Optimizer）阶段。** 计划结构完整（10 小节齐全且具体）、范围控制良好（无范围蔓延、无新增依赖 / 抽象）、正确衔接 `0001/result.md` 的三条后续建议（JSON 反序列化、4000 截断、git 前提），且**无「9 个 dataclass」式的事实性硬错**。

**进入 `task.md` 前，优化者必须裁定 / 钉死以下问题（否则编码者会臆断或留坑）：**

1. **[必裁] `name`/`description`/`tags` 归属**：JSON 归档（保持表结构，接受 O(N) 过滤）还是 SQLite 加 3 列（需改 `storage.py` 的 `_SCHEMA`）。二选一并落入验收标准与测试（§2.1）。
2. **[必钉] `truncated` 的验证路径**：`get()` 不返回 `truncated`，`test_trace.py` 必须**直查 `trace_steps` 表**断言截断与置位（§2.2）。
3. **[必钉] `register()` 状态语义**：尊重 `skill.status`（status 空才默认 active），并补「register draft/candidate 版本不被强制 active」的测试（§3.1）。
4. **[建议钉] 状态机边界 + 接口细节**：promote/rollback/deprecate/get_active 的边界行为、`passed` bool↔int 转换、`list()` 返回粒度、`since` 时间列、`save()` 幂等、JSON 缺失行为、门面构造签名（§3.3/§3.4）。

**未发现的问题**：范围控制干净（llm.py、执行/评估/演化层、Task、git 提交、真实 LLM 调用均明确排除）；复用 `Storage` + `models.py`、无新第三方依赖、无新抽象；回归风险低（不改 `config.py` 既有常量、不改 `storage.py` 契约，§10 要求全量 pytest 复跑）；实现难度现实（TraceStore→EvalStore→SkillRegistry 的难度递增顺序合理）。
