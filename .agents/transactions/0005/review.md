# 事务 0005 评审（Review）

> 评审者（Reviewer）产出。按 `roles/reviewer.md` 要求，每条发现归入「已确认的问题 / 可能存在的风险 / 需要验证的假设」三类之一。
> 评审依据：实际仓库（`0001`–`0004` 落地后的源码）+ `docs/system_design.md` + `.agents/` 状态文件 + `0004/result.md`，而非仅凭计划文本。

- 事务 ID：`0005`
- 评审日期：2026-09-28
- 评审对象：`plan.md`（规划者产出）

---

## 0. 评审方法与实际核实记录

| 核实项 | 方法 | 结果 |
|---|---|---|
| `llm.py` 现状 | 读 | `LLMClient` 仅 `complete()`；`_get_client()` 惰性 import openai；`complete()` 直接 `create()` 后取 `resp.choices[0].message.content`，**无计时、无 usage 返回** |
| `TraceStore` 现状 | 读 `execution/trace.py` | `save(trace)` 写 traces+steps（含 4000 截断）；`get(trace_id)` 合并重建；`save` 返回 `None` |
| `ExecutionTrace` 字段 | 读 `models.py` | `started_at`/`ended_at` 为**必填 str**（无默认值）；`task_id`/`task_source`/`skill_id`/`skill_version`/`steps`/`final_output`/`status` 必填；`usage: dict | None` 注释三键 |
| `RetrievalResult` | 读 `skills/retriever.py` | `RetrievalResult(skill, score, fallback)`；`fallback` 即 `retrieval_fallback` 信号源；`DEFAULT_SKILL` 内置常量 |
| `executor.py` 是否存在 | `find` | 不存在（`execution/` 下仅 `__init__.py`/`trace.py`） |
| git / 测试现状 | `git log`/`git status`/`pytest` | HEAD `fa420b7`（main）；`git status --short` 非空（state 文件已改 + `0005/` 未跟踪 + `workflow/prompts/` 未跟踪，**工作树非干净**）；全量 `68 passed` |
| 设计 §3.2/§4/§6 原文 | 读 | §3.2 AgentExecutor 职责（拼 prompt + agent loop + 错误分类 infra/task）；§4 正向流 step3「`AgentExecutor.run(task, skill)` → 输出 + Trace」；§6 `usage={total_tokens,total_cost,total_latency_ms}`、`error_type` infra/task |

---

## 1. 计划完整性核对（planner.md 要求的 10 小节）

10 个小节**全部具备**（计划遵循「文档精炼纪律」较简洁，但**内容具体、非空话**）：

| # | 要求小节 | 是否具备 | 是否具体 |
|---|---|---|---|
| 1 | 当前状态 | ✅ | ✅ 精简但准确（execution 下仅 trace.py、executor 断档） |
| 2 | 问题 | ✅ | ✅ 执行环节缺失 + usage 扩展点闭合 |
| 3 | 目标 | ✅ | ✅ AgentExecutor v1 + `complete_with_usage` |
| 4 | 范围 | ✅ | ✅ 做/不做清晰（tools.py/loop/max_steps/timeout/task 分类/chat_json/Evaluator/真实请求均排除） |
| 5 | 拟议变更 | ✅ | ✅ 文件表 + §5.1/§5.2 接口与流程 |
| 6 | 依赖 | ✅ | ✅ 标准库 uuid/time/typing + 既有 openai；无 config 变更 |
| 7 | 风险 | ✅ | ✅ 6 条均附缓解 |
| 8 | 实施顺序 | ✅ | ✅ 5 步 |
| 9 | 验收标准 | ✅ | ✅ 9 条客观可判定（grep 分层、写后回读、status/error_type/usage/fallback 断言、全量回归） |
| 10 | 验证策略 | ✅ | ✅ 命令 + 用例清单 + grep 人工复核 |

结论：结构完整、无事实性硬错。主要问题集中在**`ExecutionTrace` 必填字段的生成遗漏**与**错误归类 / 接口细节的钉死**。

---

## 2. 已确认的问题（对照仓库核实成立）

### 2.1 `started_at` / `ended_at` 这两个必填字段的生成被计划遗漏

- **已核实**：`ExecutionTrace` 的 `started_at` 与 `ended_at` 是**必填 `str`（无默认值）**（`models.py:141–142`）。`AgentExecutor.run()` 要构造合法 `ExecutionTrace`，**必须**为二者生成时间戳字符串。
- **计划 §5.2 的流程**只写了「生成 `trace_id`/`task_id`（`uuid4().hex`）→ 拼 prompt → … → 组 `steps` → 写 trace」，**完全未提 `started_at`/`ended_at` 的来源与格式**（`skill_id`/`skill_version`/`task_source`/`final_output`/`status` 等可从入参或 LLM 输出推出，但时间戳不能）。
- **后果**：编码者须临场决定用 `datetime`/`time` 生成什么格式的时间串（ISO？epoch？），且验收 §9.3「写后回读一致」无法锁定这一格式——测试与实现可能各写一套。
- **建议**：优化者在 `task.md` 钉死 `started_at`/`ended_at` 的生成方式（如 `datetime.now(timezone.utc).isoformat()`），并作为验收断言的一部分。

### 2.2 计划 §7 风险 3 的模板错误归类自相矛盾，且「按 infra 记」与设计定义冲突

- **已核实**：设计 §3.2 明确定义 `error_type`——`infra` = 网络 / 限流 / API 故障，`task` = 技能本身导致。`prompt_template.format()` 抛 `KeyError` 属**技能作者的问题（task 类）**，不是 infra。
- **计划 §7 风险 3**写「视为 skill 作者责任，异常按 infra 记 error trace（或优化者另裁定分类）；不吞」——三句话互相打架：「skill 作者责任」= task 类，却「按 infra 记」；「不吞」又暗示上抛。而 §4 又明确**排除** `task` 类错误分类。
- **建议**：优化者钉死为**不捕获、直接上抛**（模板占位符错误是确定性 authoring bug，应在测试期暴露，非运行时 infra/task 条件）；若坚持捕获落库，其 `error_type` 应为 `task`（但属 §4 非目标，故首选上抛）。**不得按 infra 记。**

---

## 3. 可能存在的风险（有迹象，未完全核实）

### 3.1 `complete_with_usage` 与 `complete()` 的实现关系未定

计划 §7 风险 1 已自识：二者可「复用（complete 内部调 complete_with_usage 丢 usage）」或「独立实现」。当前 `complete()` 是单次 `create()` 调用；若复用，`complete()` 会顺带做 latency 计时（无害但多一次 `time.monotonic`）。属优化者二选一，非阻塞。

### 3.2 usage 三键形状的「谁补 `total_cost`」未钉死

- `complete_with_usage` 拟返回 `{total_tokens, total_latency_ms}`（**2 键**），而 §6 `usage` 是 **3 键**（含 `total_cost`）。计划由 `AgentExecutor` 补 `total_cost=0.0`。
- 这造成「成本占位由执行层补」的隐式耦合：未来定价表落地（`total_cost` 真实化）时，改动点被拆在 llm 层与执行层两处。**建议**：要么 `complete_with_usage` 直接返回 §6 完整 3 键（`total_cost=0.0` 占位），要么明确记录「cost 由执行层补」为既知约定，二选一并钉死。

### 3.3 `time.monotonic` 秒→毫秒换算未说明

`total_latency_ms` 需要毫秒，`time.monotonic()` 返回**秒（float）**；计划未写「×1000 取整」。属实现细节，但应一并钉死，避免测试对 latency 量纲的断言模糊。

### 3.4 `task_id` / `trace_id` 均用 uuid 生成，二者语义趋同（前瞻性）

设计 §6 分列 `task_id` 与 `trace_id` 两字段，隐含二者可不同（如同一任务重试产生多条 trace）。但 `Task` 无 `task_id`（`0003` 用户裁定），executor 每次 `run` 只能各自 `uuid4()`，导致 `task_id` 与 `trace_id` 都是「每次执行新值」、语义近乎相同。v1 单次执行无害，但**未来任务关联 / 重试**需 `Task` 携带稳定 id。建议在 `result.md` 登记此前瞻局限（承接 0003 的 `Task` 无 id 裁定）。

### 3.5 `.format()` 对字面花括号 / 多余占位符脆弱

`skill.prompt_template.format(task=task.task)` 在模板含字面 `{`/`}`（如 code-review 技能的代码示例）或除 `{task}` 外的占位符时，会 `KeyError`/`ValueError`。§7 风险 3 已部分覆盖，但根本问题是 `.format()` 作为模板引擎过脆。建议优化者至少钉死「仅替换 `{task}`、其余花括号字面保留」的实现口径（如 `str.replace` 或受限格式化），而非盲用 `.format()`。

### 3.6 `run()` 返回契约与设计 §4 的轻微差异

设计 §4 写「`AgentExecutor.run(task, skill)` → 最终输出 + ExecutionTrace」（输出与 trace 并列）。计划 §5.2 只返回 `ExecutionTrace`（`final_output` 已在 trace 内）。这是合理简化，但需优化者确认「只返回 trace」即定案，避免未来调用方（Loop/CLI）对返回契约再猜。

---

## 4. 需要验证的假设（附建议的确认方式）

### 4.1 `complete_with_usage` 是计划自创接口（设计未定义），需优化者钉死签名

- 设计 §13 只列 `LLMClient.complete() / chat_json()`，**无 `complete_with_usage`**。该方法是计划为解决 `0004/result.md` §4 登记的「usage 采集扩展点」而**自行发明**的（取路径 b「伴生方法」）。
- **但**它属**已登记决策的落实**（0004 result §4 明确列出三条路径并建议下一个消费者事务二选一），故不是「既成设计放行」，也不是无中生有——风险中等。
- **需钉死**：返回类型 `tuple[str, dict]`、dict 的键（是否含 `total_cost`）、`resp.usage=None` 时 `total_tokens=0`、latency 的量纲与取整、`complete()` 是否复用。§5.1 已标「优化者定」，此处确认。

### 4.2 few-shot 的渲染格式未定义（设计仅「few-shot 追加」）

设计 §3.2 只说「模板填充 + few-shot + 工具声明」，§5 `FewShot(input, output)` 但**未定义**如何把 `list[FewShot]` 拼进 prompt。计划 §5.2 仅写「few-shot 追加」，无具体格式（如「示例：\n输入：{input}\n输出：{output}」）。这是**计划/设计均未钉死**的渲染细节，优化者须给出确定性格式，否则 prompt 结构不可复现、测试无法断言。

### 4.3 已核实的前提（报告结果）

- **git**：HEAD `fa420b7` ✅ 与 context §3 一致；工作树非干净（state 文件 + `0005/` + 未跟踪的 `workflow/prompts/`），计划/context「工作树干净」已过时（轻微，与前序同类）。
- **测试**：全量 `68 passed` ✅ 与 project_state/context 一致。
- **`llm.py`**：`complete()` 现状确认（无 usage/计时），`complete_with_usage` 需在 `llm.py` 新引入 `import time`。
- **`TraceStore`**：`save`/`get` 已就绪，executor 直接消费；`save` 对 `trace.usage` 由 `Storage` 自动 `json.dumps`（dict 值）。
- **`RetrievalResult.fallback`** 已就绪，`retrieval_fallback` 参数可正确映射到 trace 字段。

---

## 5. 总体结论

**该计划可以进入优化（Optimizer）阶段。** 计划结构完整（10 小节齐全、虽精简但具体）、正确闭合 `0004/result.md` §4 的 usage 扩展点（取伴生方法路径 b，不改 `complete()`）、范围控制良好（tools.py/工具调用/多轮 loop/max_steps/timeout/task 分类/chat_json/Evaluator/真实请求均排除——且 v1 单轮无工具模式下 `task` 类错误本就不会发生，该裁剪合理）、分层正确（executor 只调 `llm`/`trace_store`，DI 注入便于测试）。**无事实性硬错。**

**进入 `task.md` 前，优化者必须钉死以下问题：**

1. **[必钉] `started_at`/`ended_at` 的生成方式与格式**（`ExecutionTrace` 必填字段，计划流程遗漏，§2.1）。
2. **[必钉] 模板错误的归类与行为**：首选不捕获、上抛；不得「按 infra 记」（§2.2）。
3. **[必钉] `complete_with_usage` 签名与 usage 形状**：返回键是否含 `total_cost`、latency 量纲/取整、`complete()` 复用与否（§3.2/§3.3/§4.1）。
4. **[必钉] few-shot 渲染格式**（§4.2）与 prompt 填充口径（仅替换 `{task}`、字面花括号保留，§3.5）。
5. **[建议] 登记前瞻局限**：`task_id`/`trace_id` 语义趋同、`total_cost=0.0` 占位（定价未实现）、`run()` 仅返回 Trace 的契约（§3.4/§3.6）。

**未发现的问题**：`run(task, skill)` 签名与设计 §4 一致（skill 由调用方经检索器/注册表取得后传入，满足 §3.2「加载 Skill」的实质、且更可测）；无范围蔓延、无不必要抽象、无新第三方依赖、回归风险低（`llm.py` 只加方法、`complete()` 行为不变，§9.1 已锁定）。
