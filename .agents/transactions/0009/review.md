# 事务 0009 评审（Review）

> 评审者（Reviewer）产出。按 `roles/reviewer.md` 要求，每条发现归入「已确认的问题 / 可能存在的风险 / 需要验证的假设」三类之一。
> 评审依据：实际仓库（`0001`–`0008` 落地后的源码）+ `docs/system_design.md` + `.agents/` 状态文件 + `0008/result.md`，而非仅凭计划文本。

- 事务 ID：`0009`（项目收官事务）
- 评审日期：2026-09-29
- 评审对象：`plan.md`（规划者产出）

---

## 0. 评审方法与实际核实记录

| 核实项 | 方法 | 结果 |
|---|---|---|
| `TraceStore.list` 签名 | 读 `execution/trace.py:109` | 仅 `skill_id`/`status`/`since` 过滤，**无 `task_source`/`error_type` 参数**；返回 summary（`steps=[]`，但含 `task_source`/`error_type`/`skill_id`/`final_output`/`status` 等列） |
| `ExperienceExtractor.extract` 输入 | 读 `eval/experience.py:21-29` | `_extract_prompt` 只用 `trace.skill_id`/`status`/`final_output`/`trace_id` + `result` 字段——**summary trace 够用，无需 `get()` 取全量** |
| `Validator.validate` 四结局 | 读 `evolution/validator.py` | 四结局：样本不足（register draft、不写 failed_evolution）/ promoted（+metrics 快照）/ insignificant / regression（后两者写 failed_evolution） |
| `SkillEvolver.evolve` | 读 `evolution/evolver.py` | 候选 `status="draft"`、patch 递增、`metrics={}`、`tools` 原样、`parent_version` |
| `SkillRetriever.retrieve_top1` | 读 `skills/retriever.py:97-103` | 返回 `RetrievalResult(skill, score, fallback)`；`fallback` 即 `retrieval_fallback` 信号源 |
| `pyproject.toml` | 读 | `[tool.setuptools] packages = ["evoagent"]`（**不含子包**，问题属实） |
| `config.py` | 读 | 有 `PROMOTE_WIN_RATE_THRESHOLD`/`MIN_REGRESSION_TASKS`（0008），**无 `MIN_EVOLUTION_SAMPLES`** |
| `Task` 实际字段 | 读 `models.py:82` | `task: str` + `task_source: str`（无 `task_id`） |
| `loop.py`/`cli.py`/`README.md` 是否存在 | `find` | 均**不存在** |
| git / 测试现状 | `git log`/`git status`/`pytest` | HEAD `cdc839f`（main）；`git status --short` 非空（state 文件已改 + `0009/` 未跟踪，**工作树非干净**）；全量 `115 passed` |

---

## 1. 计划完整性核对（planner.md 要求的 10 小节）

10 个小节**全部具备、内容具体可执行**（遵循「文档精炼纪律」，简洁但非空话）：

| # | 要求小节 | 是否具备 | 是否具体 |
|---|---|---|---|
| 1 | 当前状态 | ✅ | ✅ 缺 loop/cli/README、打包只含顶层、设计缺 Task |
| 2 | 问题 | ✅ | ✅ 项目不可交付（无编排/入口/打包/一致/文档） |
| 3 | 目标 | ✅ | ✅ 5 子项一个连贯目标 |
| 4 | 范围 | ✅ | ✅ 做/不做清晰 |
| 5 | 拟议变更 | ✅ | ✅ 文件表 + §5.1–§5.6 细化 |
| 6 | 依赖 | ✅ | ✅ 标准库 + 既有 openai，无新第三方 |
| 7 | 风险 | ✅ | ✅ 6 条均附缓解（污染/阻塞/成本/打包/越界/组装） |
| 8 | 实施顺序 | ✅ | ✅ 6 步 |
| 9 | 验收标准 | ✅ | ✅ 9 条客观可判定 |
| 10 | 验证策略 | ✅ | ✅ 命令 + 用例清单 + 人工复核 |

结论：结构完整、无事实性硬错。收官事务计划相对干净；Loop 只编排、只挖 `task_source=="real"`（防污染硬保证）、四子命令与 §13 一致、打包修复标准正确、设计回补已获用户授权。主要待办是**几个自创常量/接口细节的钉死**与**人工验证步骤的可执行性**。

---

## 2. 已确认的问题（对照仓库核实成立）

### 2.1 `TraceStore.list()` 无 `task_source`/`error_type` 过滤，Loop 的防污染过滤须「内存完成」（计划未明示）

- **已核实**：`TraceStore.list(skill_id=None, status=None, since=None)`（`trace.py:109`）**不支持** `task_source`/`error_type` 过滤。计划 §5.2 写「`trace_store.list()` → 过滤 `task_source=="real"` 且 `error_type!="infra"`」，实际是**先取全部、再在 Python 内存过滤**。
- **已核实可行**：`list()` 返回的 summary 行**含** `task_source`/`error_type` 列（仅 `steps=[]`），故内存过滤可行；且 `ExperienceExtractor._extract_prompt` 只用 `skill_id`/`status`/`final_output`/`trace_id`，summary 够用，Loop **无需逐条 `get()` 取全量**。
- **建议**：优化者在 `task.md` 明示这两个隐含依赖——(a) `task_source`/`error_type` 过滤在 Loop 侧内存完成（不靠 `list()` 参数）；(b) 传给 `extractor.extract` 的是 summary trace（非 `get()` 全量），避免编码者误以为 `list()` 支持这些过滤、或误做 N+1 `get()`。

### 2.2 CLI `run`/`evolve` 运行时确会发真实 LLM 请求，与 §4/§9.9「无真实 LLM 请求」字面矛盾（措辞，非功能缺陷）

- **已核实**：`cli.py` 的 `run`（`executor.run`→`complete_with_usage`）、`evolve`（`extractor`/`evolver`/`benchmark`→`judge`）在**用户实际调用时必然发真实 LLM 请求**——这是 CLI 的用途。
- **判断**：「mock-first = 仅指自动化测试」是前序事务的既有口径，但收官事务**首次引入可运行入口**，口径应升级。
- **建议**：优化者把 §4/§9.9 措辞改为「自动化测试 mock-first、不发真实请求；CLI 运行时调用 LLM 是预期行为」，避免验收误伤 CLI。

---

## 3. 可能存在的风险（有迹象，未完全核实）

### 3.1 打包修复的验收是「人工步骤」，可能被跳过

验收 §9.5（干净环境 `pip install .` 后 import 全子包）在 §10 标注为「**打包验证（人工，干净环境）**」——非 pytest 自动覆盖，需编码者手动建 venv + `pip install`。风险：如同 0004 的手工冒烟（「无 key 环境未执行」被跳过），该步骤可能被遗漏，导致打包缺陷漏检。**建议**：优化者把它列为 `execution.md`/`result.md` 必记项，并明确「跳过即验收不完整」。

### 3.2 种子数据缺失，`evolve`/`bench` 无 benchmark 文件/技能时会失败或空跑

CLI 的 `evolve`/`bench` 依赖 `data/benchmarks/{regression,extension}.json` 与已注册 skill（§12 冷启动**未播种**）。无这些文件时 `load_tasks_by_name` 会 `FileNotFoundError`、`list` 空跑。计划 §5.6 README「不杜撰未实现能力」，但未明确「需先播种技能与 benchmark 集」。**建议**：README 与 CLI 错误信息如实标注该前置，避免「开箱即用」的误导。

### 3.3 5 子项 bundling 跨度较宽（代码 + 配置 + 文档三类）

`EvolutionLoop`+`cli.py`（代码）、打包（配置）、设计回补 + README（文档）虽同属「可交付」收官目标，但属三类改动。工作流协议「避免合并互不相关目标」下，收官打包可辩护，但建议优化者在 `task.md` 给 5 子项各自独立验收、互不阻塞（尤其打包/设计回补不应被 loop/cli 的测试失败连带阻塞）。

### 3.4 `cli.py run` 的 `retrieval_fallback` 映射细节未明示（轻微）

`retriever.retrieve_top1(task)` 返回 `RetrievalResult(skill, score, fallback)`，而 `AgentExecutor.run(task, skill, *, retrieval_fallback=...)` 有 `retrieval_fallback` 关键字参数。计划 §5.3 只写「`retriever.retrieve_top1` → `executor.run`」，**未说明**把 `result.fallback` 映射为 `retrieval_fallback` 参数。编码者若漏传，`run` 子命令落库的 `retrieval_fallback` 恒为 `False`，与 §4「低相似度走 default skill 并标记 fallback」不符。**建议**：优化者钉死 `r = retriever.retrieve_top1(task); executor.run(task, r.skill, retrieval_fallback=r.fallback)`。

---

## 4. 需要验证的假设（附建议的确认方式）

### 4.1 `MIN_EVOLUTION_SAMPLES = 1`（计划自创，且与 §9「连续 M 次」语义不同）

- 计划 §5.1 自标「K/M 设计未钉，v1 默认 1，可调」。设计 §9 的触发条件有**两种**：「定时（每 N 次执行/每天）」与「阈值（某 skill **连续 M 次** `passed is False`）」，且「连续 M 次」是**连续失败计数**语义，与计划的「总样本数 ≥ 1」**不同**（一条低分 trace 即触发，而非连续 M 次）。计划 §5.2 只实现「样本量」阈值、**未实现「定时」模式**、**未保留「连续」语义**。
- **建议确认方式**：优化者钉死值（1 是否为可接受的 v1 起点），并明确「只做总样本数阈值、不做定时/连续计数」是对 §9 的已知简化，记录在 `task.md`/`result.md`；若坚持「连续 M 次」，则需给出「连续」的实现口径（本事务是否值得为此加复杂度，交由优化者权衡）。

### 4.2 设计回补的 placement（内容已核实一致，位置待定）

- 计划 §5.5 把 `Task` dataclass 定义「在 §4 附近」。设计现有 dataclass 惯例是**独立章节**（§5–§11 每结构一节），§4 是「数据流设计」。内容（`task`/`task_source`，无 `task_id`）已核实与 `models.py` 逐字段一致、与 §4/§6 一致。
- **建议确认方式**：优化者定 placement（在 §4 内嵌小代码块，或新增独立小节），并明确「仅此一处新增、不得扰动 §4 数据流」，`git diff` 只允许该一处新增（§9.6 已列）。另请确认：设计回补是**对编码者写范围（不含 docs）的用户授权例外**，已在 context §5 获授权，编码者不得因此顺手改其它章节。

### 4.3 `build_components` 的组装范围与接线深度

`cli.py` 的 `build_components(db_path=None)` 需组装**约 12 个组件**：`Storage`（`connect()`+`init_schema()`）→ `SkillRegistry`/`TraceStore`/`EvalStore` → `LLMClient` → `SkillRetriever`/`AgentExecutor`/`Evaluator`/`ExperienceExtractor`/`Benchmark`/`SkillEvolver`/`Validator`/`EvolutionLoop`。计划 §5.3 只给签名「组装 Storage→各门面→…→loop」，未列全接线清单。`list` 子命令只需 `SkillRegistry`，若无条件全量组装是冗余（虽 `LLMClient` 惰性构建不强制 API key、安全）。
- **建议确认方式**：优化者定 `build_components` 是「全量组装」（简单、`list` 冗余可接受）还是「按子命令最小组装」（省资源），并列出完整组件接线清单，保证 `list` 无 LLM 可端到端跑（§9.4 已列）。

### 4.4 `EvolutionLoop.run` 的边界：`get_active` 为 None / 无低分 trace / `tasks` 为空

计划 §5.2 每 skill 流程「`registry.get_active(skill_id)` → …」，但未明示：某 skill 无 active 版本时（`get_active` 返回 `None`）是否跳过；`trace_store.list()` 无低分 trace 时（整体空跑）`run` 返回空 `list[ValidationResult]` 是否成立；`tasks` 为空时 `validate` 会走「样本不足」（`Validator` 已处理 `<20`）。这些边界应明确，测试覆盖（空 trace、无 active skill、空 tasks）。

### 4.5 已核实的前提（报告结果）

- **git**：HEAD `cdc839f` ✅ 与 context §3 一致；工作树非干净（state 文件 + `0009/`），context「工作树干净」已过时（轻微，与前序同类）。
- **测试**：全量 `115 passed` ✅ 与 project_state/context 一致。
- **Loop 复用**：`Validator` 四结局（含 metrics 快照、样本不足转人工不写 failed_evolution、insignificant/regression 写 failed_evolution）已由 0008 交付，Loop 正确复用、不重实现 ✅。
- **防污染**：Loop 只挖 `task_source=="real"` 是 §11 规则 1 的 Loop 侧硬保证，正确 ✅。
- **CLI 四子命令**（run/evolve/bench/list）与 §13 一致 ✅；打包修复（`packages.find` + `include=["evoagent*"]`）标准正确 ✅；设计回补已获用户授权（context §5）✅。
- **`Task` 回补内容**：`task`/`task_source`（无 `task_id`）与 `models.py:82` 逐字段一致 ✅。

---

## 5. 总体结论

**该计划可以进入优化（Optimizer）阶段。** 计划结构完整（10 小节齐全且具体）、正确承接 `0008/result.md` 的 EvolutionLoop+cli 建议、Loop 只编排不重实现（复用 0002–0008 交付的六模块）、防污染是 Loop 侧硬保证、CLI 四子命令与 §13 一致、打包修复与设计回补（已获用户授权）均正确、`Task` 回补内容与 `models.py` 逐字段一致。**无事实性硬错。**

**进入 `task.md` 前，优化者必须裁定 / 钉死以下问题：**

1. **[必钉] `MIN_EVOLUTION_SAMPLES` 值 + 是否保留「连续 M 次」/「定时」语义**（§4.1，计划自创常量，且对 §9 触发条件做了「只做样本量阈值」的简化）。
2. **[必钉] 措辞升级 + 隐含依赖明示**：§4/§9.9「无真实 LLM 请求」→「测试 mock-first，CLI 运行时调 LLM 是预期」（§2.2）；明示 Loop 的内存过滤 + summary trace 够用（§2.1）。
3. **[必钉] `cli.py run` 的 `retrieval_fallback` 映射**（§3.4）与 `EvolutionLoop.run` 边界（无 active/空 trace/空 tasks，§4.4）。
4. **[必钉] 人工验证可执行性**：打包验证（§9.5）与 seed 数据前置（§3.2）须在 `execution.md`/README 落地，不得被跳过。
5. **[建议钉] 设计回补 placement 与 `build_components` 组装范围/接线清单**（§4.2/§4.3），并给 5 子项各自独立验收（§3.3）。

**未发现的问题**：无新第三方依赖、无不必要抽象（`build_components` 是 CLI 必需的组合根、`EvolutionLoop` 纯编排）、回归风险低（config 追加常量、新建 loop/cli 不触既有模块）；`Task` 回补、打包修复、README 均与设计/实现一致。
