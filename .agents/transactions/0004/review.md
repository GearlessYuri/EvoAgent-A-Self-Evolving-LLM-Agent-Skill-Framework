# 事务 0004 评审（Review）

> 评审者（Reviewer）产出。按 `roles/reviewer.md` 要求，每条发现归入「已确认的问题 / 可能存在的风险 / 需要验证的假设」三类之一。
> 评审依据：实际仓库（`0001`–`0003` 落地后的源码）+ `docs/system_design.md` + `.agents/` 状态文件 + `0003/result.md`，而非仅凭计划文本。

- 事务 ID：`0004`
- 评审日期：2026-09-28
- 评审对象：`plan.md`（规划者产出）

---

## 0. 评审方法与实际核实记录

| 核实项 | 方法 | 结果 |
|---|---|---|
| `llm.py` 是否存在 | `find` | 不存在（`evoagent/` 下仅 `__init__`/`models`/`config`/`storage`/`skills/`/`execution/`/`eval/`） |
| `config.py` 当前常量 | 读 | 无任何 LLM 常量；docstring 明示「不含 LLM 参数（随 llm.py 事务引入）」 |
| `pyproject.toml` 依赖 | 读 | `dependencies = []`，且第 10 行注释「本事务不引入任何第三方运行时依赖；仅标准库 + 开发期 pytest」 |
| `requirements.txt` | 读 | 仅 `pytest` |
| `models.py` dataclass 数 | 读 | `Task`（`task`/`task_source`，**无 `task_id`**）+ §5–§11 的 8 个 = **9 个** |
| 现有测试对 config 的依赖 | `grep` + 读 `test_trace.py`/`test_storage.py` | `test_trace.py` 仅用 `config.TRACE_CONTENT_MAX_CHARS`；**无任何测试断言 config 内容或「无 LLM 常量」** → 加 LLM 常量**零回归** |
| git / 测试现状 | `git log`/`git status`/`pytest` | HEAD `db105a5`（main）；`git status --short` 非空（state 文件已改 + `0004/` 未跟踪，**工作树非干净**）；全量 `63 passed` |
| openai 是否已安装 | `python -c "import openai"` | **已安装 `openai 2.38.0`**（v1.x API） |

---

## 1. 计划完整性核对（planner.md 要求的 10 小节）

10 个小节**全部具备、内容具体可执行**：

| # | 要求小节 | 是否具备 | 是否具体 |
|---|---|---|---|
| 1 | 当前状态 | ✅ | ✅ 准确：底座缺 llm.py、config 无 LLM 常量、deps 为空 |
| 2 | 问题 | ✅ | ✅ 4 条证据，含「llm.py 是执行/评估/演化/编排层共同硬依赖」 |
| 3 | 目标 | ✅ | ✅ 明确落实 5 条用户裁定，无重新讨论 |
| 4 | 范围 | ✅ | ✅ 做/不做清晰；anthropic/chat_json/tool calling/AgentExecutor/真实调用/git 均排除 |
| 5 | 拟议变更 | ✅ | ✅ 逐文件 + §5.1/§5.2/§5.3 细化常量、接口、依赖 |
| 6 | 依赖 | ✅ | ✅ 运行时（openai + os/typing）、顺序、前置条件、对既有模块（无，纯新增） |
| 7 | 风险 | ✅ | ✅ 7 条均附缓解，惰性 import/注入边界、key 缺失、依赖失控、接口过宽、返回值解析、docstring 失准、蔓延均有覆盖 |
| 8 | 实施顺序 | ✅ | ✅ 5 步，config→依赖声明→llm.py→测试→验证 |
| 9 | 验收标准 | ✅ | ✅ 8 条客观可判定（含 key 仅环境变量、单方法、注入不发请求、依赖断言、全量回归） |
| 10 | 验证策略 | ✅ | ✅ 命令 + 用例清单 + 手工冒烟（非自动、可跳过） |

结论：结构完整、无事实性硬错。计划把 5 条用户裁定当作**给定输入**（§2/§5 明确「落实」「不再讨论」），姿态正确。主要待办集中在**默认值的确认**与**若干接口/测试边界**。

---

## 2. 已确认的问题（对照仓库核实成立）

### 2.1 `pyproject.toml` 第 10 行注释将在加 `openai` 后失准，计划未提及更新（轻微）

- **已核实**：`pyproject.toml:10` 现为 `# 本事务不引入任何第三方运行时依赖；仅标准库 + 开发期 pytest`。本事务把 `dependencies = []` 改为 `["openai"]` 后，该注释变为错误。
- **对比**：计划 §5.1 **主动**处理了 `config.py` 同类问题（更新其「不含 LLM 参数」docstring），却漏了 `pyproject.toml` 的这条注释。
- **建议**：优化者在 `task.md` 中把「同步更新 `pyproject.toml` 依赖注释」一并列入，避免残留失准文案。

### 2.2 计划 §1「工作树干净」已过时（轻微，与前序事务同类）

- **已核实**：`git status --short` 显示 `M active_transaction.md`、`M project_state.md`、`?? .agents/transactions/0004/`——非干净。这是 0004 事务自身对状态文件的更新，属预期；仅「干净」表述过时。无需改方案。

---

## 3. 可能存在的风险（有迹象，未完全核实）

### 3.1 `complete() -> str` 丢弃 token/cost/latency，与 §6 `ExecutionTrace.usage` 存在前瞻性张力

- 用户裁定 #3 定了「纯文本入出」，本事务照做是**正确**的；但需显式记录其**前瞻后果**：设计 §6 的 `ExecutionTrace.usage = {total_tokens, total_cost, total_latency_ms}` 要求执行层记录 token/成本/时延，而这些信息**只来自 LLM 响应的 `.usage`/计时**。当前 `complete() -> str` 只回文本，**丢弃了它们**。
- 下一个事务 `AgentExecutor`（§3.2）写 Trace 时需要 `usage`，届时将不得不二选一：(a) 扩展 `complete()` 返回更丰富对象（打破裁定 #3 的「纯文本出」），或 (b) 新增伴生方法（如 `complete_with_usage()`），或 (c) 执行层绕过 `llm.py` 直调 SDK（违反「llm.py 是唯一 LLM 访问点」分层）。
- **建议**：不阻塞本事务，但优化者应在 `task.md`/`result.md` 中**登记为已知局限与后续决策**，明确「`usage` 采集是 `AgentExecutor` 事务对 `llm.py` 接口的前置扩展点」，避免届时无声推翻或绕过分层。

### 3.2 未注入路径（真实 client 惰性构建）的自动测试覆盖较弱

- 计划 §10 自认：「未注入 + 惰性构建」用例「若难以离线断言，可降级为 key 缺失抛 ValueError 的覆盖」。这意味着 `LLMClient()` 未注入时**成功**构建 `openai.OpenAI(base_url=..., api_key=...)` 的路径，很可能**没有自动化断言**（仅手工冒烟）。
- 现状：本机已装 `openai 2.38.0`，理论上可 monkeypatch `openai.OpenAI` 断言被以正确参数调用（§10 已提议）。建议优化者**尽量保留**这条 monkeypatch 断言（而非一律降级），否则「真实路径的 base_url/model 传参」完全无自动防线。若坚持降级，则明确记录为测试覆盖缺口。

### 3.3 「注入 fake 时 openai 未被 import」断言脆弱

- §10「mock-first 强化」拟用 `sys.modules` 探测或 monkeypatch `builtins.__import__` 断言 openai 未被导入。`sys.modules` 是**进程全局态**：一旦同一次 pytest 运行中任何其它测试/插件 import 了 openai，该断言即误报。当前仓库无其它 openai import，故暂可工作，但**脆弱**。建议优先用 `builtins.__import__` 局部拦截，或把该断言限定为「注入路径未触发 `openai.OpenAI` 构造」（比「未 import」更稳健、更贴需求）。

### 3.4 `openai` 版本下界未定，代码隐含依赖 v1.x API

- 计划 §5.2/§10 用 `openai.OpenAI(base_url=..., api_key=...)` 与 `resp.choices[0].message.content`——这是 openai **v1.x** 客户端 API。§5.3 说「不写死版本号，或写宽松下限，由优化者定」。若完全不设下界，环境装到 `openai<1.0`（旧 `openai.ChatCompletion` 接口）会直接报错。
- **建议**：在 `requirements.txt`/`pyproject.toml` 写 `openai>=1.0`（或等价下界），与所用 v1.x API 对齐。

### 3.5 `complete()` 的 `content=None` 与 `os.environ` 取值方式未钉死（计划已部分自识）

- §7 风险 5 已提 `content=None` 需优化者钉死（空串 vs 上抛）；此外 §5.1 写 `os.environ.get(LLM_API_KEY_ENV)`、§9.5 写 `os.environ[LLM_API_KEY_ENV]`，`get` 与 `[]` 两种取值方式在计划内**不一致**。二者最终都应落到「缺失 → `ValueError`」，但实现口径（`get` 判 `None` vs `[]` 捕获 `KeyError`）应统一，避免编码者临场二选一。

---

## 4. 需要验证的假设（附建议的确认方式）

### 4.1 三个 LLM 常量的默认值（DeepSeek 具体 base_url / 模型名 / 环境变量名）

- **计划自标**：§5.1 明确「默认值（DeepSeek 的 base_url / 模型名）为提议值，评审/优化可微调，但三常量名与 key 仅环境变量不可改（裁定 #2）」。
- **区分**：三常量**名称**（`LLM_BASE_URL`/`LLM_MODEL`/`LLM_API_KEY_ENV`）来自用户裁定 #2，属既成输入；但**具体值** `"https://api.deepseek.com"`、`"deepseek-chat"`、`"DEEPSEEK_API_KEY"` 是计划依据上下文示例（「适配 DeepSeek」「如 DEEPSEEK_API_KEY」）**自行落定**的提议值，未获用户点名确认。
- **建议确认方式**：由用户/人工确认实际 provider 与模型名（或接受 DeepSeek 默认）；优化者须在 `task.md` 把这三个具体值记录为「已确认的 LLM 默认配置」，避免下一事务再改口径。

### 4.2 已核实的前提（报告结果，消除不确定性）

- **git**：HEAD `db105a5` ✅ 与计划 §1 一致；工作树非干净（见 §2.2）。
- **测试**：全量 `63 passed` ✅ 与计划 §1 一致。
- **openai 环境**：`openai 2.38.0` 已安装 ✅（v1.x，与 §5.2 所用 API 匹配；也因此 §3.4 的版本下界更值得写明）。
- **config 常量**：当前无 LLM 常量 ✅；加 3 常量**不破坏任何现有测试**（`test_trace.py` 仅用 `TRACE_CONTENT_MAX_CHARS`，无 config 内容断言）。
- **`models.py`**：`Task` 已存在且无 `task_id` ✅（与 0003 裁定一致），本事务不触碰。

---

## 5. 总体结论

**该计划可以进入优化（Optimizer）阶段。** 计划结构完整（10 小节齐全且具体）、正确落实 5 条用户裁定（OpenAI 兼容单路径 / key 仅环境变量 / 窄接口单方法 / mock-first / 仅 openai 一个依赖）、范围控制良好（anthropic / chat_json / tool calling / AgentExecutor / 真实调用 / git 均排除、无新增抽象）、分层正确（`llm.py` 只依赖 `config`，是纯新增底座，无依赖方被波及、零回归——已核实无测试断言 config 内容）。**无事实性硬错。**

**进入 `task.md` 前，优化者应裁定 / 钉死以下问题：**

1. **[必确认] 三个 LLM 常量默认值**（DeepSeek base_url / 模型名 / 环境变量名）——具体值需用户/人工确认或接受 DeepSeek 默认，并在 `task.md` 记录为已确认（§4.1）。
2. **[建议钉] 前瞻性登记**：`complete() -> str` 与 §6 `ExecutionTrace.usage` 的张力，作为已知局限记录，供 `AgentExecutor` 事务处理（§3.1）。
3. **[建议钉] 实现细节**：`content=None` 行为、`os.environ.get` vs `[]` 统一、`openai>=1.0` 版本下界、`pyproject.toml` 依赖注释同步更新（§2.1/§3.4/§3.5）。
4. **[建议钉] 测试边界**：尽量保留「未注入路径 monkeypatch 断言 `openai.OpenAI` 被正确传参」而非一律降级为 ValueError 覆盖；「未 import」断言改用更稳健方式（§3.2/§3.3）。

**未发现的问题**：无范围蔓延、无不必要抽象（client 注入是裁定 #3/#4 的最小扩展点，非适配层）、无安全泄漏（API key 仅环境变量、绝无明文入仓库，§9.1 已覆盖）、实现难度低（薄封装）。
