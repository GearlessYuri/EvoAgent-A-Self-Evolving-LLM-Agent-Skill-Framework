# 事务 0004 计划（Plan）

> 规划者（Planner）产出。按 `roles/planner.md` 要求的小节组织。
> 本计划**落实**用户已拍板的 5 条裁定（见 §2 目标 / §5），不再将其列为开放项。

---

## 1. 当前状态（Current State）

系统**存储层完整、检索入口就绪、底座层缺最后一块 `llm.py`**。经实仓核实：

- `0001`（底座）：`models.py` 9 个 dataclass（`Task` + §5–§11 的 8 个）、`config.py` 常量、`storage.py` 5 表。
- `0002`（门面）：`SkillRegistry` / `TraceStore` / `EvalStore`。
- `0003`（检索）：`SkillRetriever`（`retrieve` / `retrieve_top1` + `DEFAULT_SKILL`）。
- `evoagent/llm.py` **不存在**；`config.py` **无 LLM 常量**（docstring 明示「随 llm.py 事务引入」）；`pyproject.toml` `dependencies = []`；`requirements.txt` 仅 `pytest`。
- 全量 63 项测试通过；git `main`@`db105a5`，工作树干净。

## 2. 问题（Problem）

**`llm.py` 缺失，卡住执行/评估/演化/编排层的全部后续模块。**

证据：

1. `AgentExecutor`（§3.2）、`Evaluator` 的 LLM-as-judge（§7）、`ExperienceExtractor`（§3.3）、`SkillEvolver`（§3.4）**都需要调用 LLM**，`llm.py` 是它们共同的底座依赖；它不落地，闭环的后半段无从谈起。
2. `config.py` 的 LLM 参数被显式延后到「llm.py / evaluator 事务」，本事务正是兑现时点。
3. 项目至今**零第三方运行时依赖**；本事务须**首次**引入 openai SDK，且必须在「最小依赖 + mock-first」下保证可测试，不能因引入依赖而让测试依赖真实网络 / API key。
4. 设计 §2/§13 明确 `llm.py` 属底座层、接口为 `LLMClient.complete() / chat_json()`；但用户裁定 #3 已收窄为「单方法、纯文本入出」，故本事务只做 `complete()`。

## 3. 目标（Objective）

落地底座层最后一块 `evoagent/llm.py` —— OpenAI 兼容的 LLM 薄封装，并首次引入运行时第三方依赖 `openai`：

- `evoagent/config.py`：新增 3 个 LLM 常量（`LLM_BASE_URL` / `LLM_MODEL` / `LLM_API_KEY_ENV`）
- `evoagent/llm.py`：`LLMClient`（窄接口、单方法 `complete()`、纯文本入出、可注入 mock client）
- `pyproject.toml` / `requirements.txt`：新增 `openai` 依赖
- `tests/test_llm.py`：mock-first 单测（不发真实请求）

**落实的 5 条裁定**：① 只走 OpenAI 兼容路径、不做 anthropic / 多 provider 层；② 三常量 + key 仅读环境变量；③ 窄接口单方法文本入出、留注入扩展点、不写抽象；④ mock-first 全单测不发请求、真实调用仅手工冒烟；⑤ 运行时新增 `openai` 一个第三方依赖。

## 4. 范围（Scope）

**做（In scope）**

1. `evoagent/config.py`（**追加** 3 常量 + 更新模块 docstring）：见 §5.1。
2. `evoagent/llm.py`：`LLMClient`（§5.2）。
3. `pyproject.toml`：`dependencies = []` → `dependencies = ["openai"]`（§5.3）。
4. `requirements.txt`：追加 `openai`（§5.3）。
5. `tests/test_llm.py`（§9/§10）。

**不做（Out of scope，明确非目标）**

- **anthropic SDK**、任何多 provider 适配层（裁定 #1）。
- **`chat_json()`**：设计 §13 虽列了它，但裁定 #3 收窄为「单方法、纯文本入出」；`chat_json` 属 `Evaluator`（§7 LLM-as-judge）的未来需求，留待评估层事务。
- **tool calling / 结构化输出 / 多轮消息编排**：`AgentExecutor`（§3.2）的未来需求，不在本事务。
- **错误分类**（§3.2 `error_type` infra/task）——归属 `AgentExecutor`，`llm.py` 只透传异常、不分类。
- **`AgentExecutor` / `tools.py` / `Evaluator` / 任何上层模块**。
- **真实 LLM 调用 / 网络请求**（仅手工冒烟验证，不进自动测试，裁定 #4）。
- **任何 git 操作**（收尾提交由 Coder 依 task.md 执行）。
- **numpy、anthropic 等其它依赖**（仅 `openai` 一个，裁定 #5）。

## 5. 拟议变更（Proposed Changes）

| 文件 | 变更性质 |
|---|---|
| `evoagent/config.py` | 追加 `LLM_BASE_URL` / `LLM_MODEL` / `LLM_API_KEY_ENV`；更新模块 docstring（不再声称「不含 LLM 参数」） |
| `evoagent/llm.py` | 新建 `LLMClient`（§5.2） |
| `pyproject.toml` | `dependencies` 由 `[]` 改为 `["openai"]` |
| `requirements.txt` | 追加 `openai` |
| `tests/test_llm.py` | 新建（§9/§10） |

### 5.1 `config.py` —— 3 个 LLM 常量（裁定 #2）

在既有常量之后追加：

```python
# ── LLM（事务 0004 引入，OpenAI 兼容路径） ────────────────────────────────
LLM_BASE_URL = "https://api.deepseek.com"   # §14 OpenAI 兼容 provider base_url（可覆盖）
LLM_MODEL = "deepseek-chat"                 # 默认模型
LLM_API_KEY_ENV = "DEEPSEEK_API_KEY"        # 环境变量名；key 值绝不进仓库，仅运行时读取
```

- `LLM_API_KEY_ENV` 是**环境变量名**（非 key 值）；真实 key 由 `os.environ.get(LLM_API_KEY_ENV)` 运行时读取，**绝不写入仓库**。
- **模块 docstring 同步更新**：当前 docstring 写「不含任何 LLM provider / model / API key 等参数（这些随 llm.py / evaluator 事务引入）」已失准，改为反映「已含 OpenAI 兼容路径的 LLM 常量，key 仅从环境变量读取」。
- 默认值（DeepSeek 的 base_url / 模型名）为提议值，评审/优化可微调，但**三常量名与「key 仅环境变量」不可改**（裁定 #2）。

### 5.2 `llm.py` —— `LLMClient`（裁定 #1/#3/#4）

**为什么存在**：屏蔽 OpenAI 兼容 provider 的调用细节，对上暴露窄接口；是执行/评估/演化层的共同 LLM 底座（§2/§13）。

**窄接口（单方法、纯文本入出；裁定 #3）**：

```python
class LLMClient:
    def __init__(self, client=None):   # client: 可注入的 OpenAI 兼容 client（测试注入 fake）
        self._client = client

    def complete(self, prompt: str) -> str:   # 纯文本入 → 纯文本出
        ...
```

- **`complete(prompt: str) -> str`**：把 `prompt` 作为单条 user 消息发给底层 OpenAI 兼容 client，返回 assistant 文本（`resp.choices[0].message.content`）。这是对上暴露的**唯一方法**。
- **`client` 注入（裁定 #4 的扩展点，也是裁定 #3 的「第二 provider 扩展点」）**：`__init__(client=None)`。`client` 为 `None` 时**惰性构建**真实 OpenAI 兼容 client（`openai.OpenAI(base_url=config.LLM_BASE_URL, api_key=os.environ.get(config.LLM_API_KEY_ENV))`）；`client` 注入时直接用（测试注入 fake，**不构建真实 client、不 import openai**）。将来第二 provider 只要包装成同形 client 注入即可，**无需改 `LLMClient`、无需适配层**。
- **惰性 import openai**：`llm.py` **不在模块顶层 `import openai`**，只在「构建真实 client」的代码路径内局部 import。这样 mock 注入路径**完全不触碰 openai 模块**，测试可在未安装 openai SDK 的环境下运行（裁定 #4「mock-first」的强化）。
- **API key 缺失**：构建真实 client 时若 `os.environ` 无 `LLM_API_KEY_ENV`，抛 `ValueError`（清晰的配置错误），而非静默失败。
- **错误处理边界**：`complete()` 对 SDK 抛出的异常**不分类、不吞**，原样上抛——`error_type`（infra/task）分类属 `AgentExecutor`（§3.2），不在本事务。
- **不实现** `chat_json()`、tool calling、多轮编排（裁定 #3，见 §4 非目标）。

### 5.3 依赖（裁定 #5）

- `pyproject.toml`：`[project]` 的 `dependencies = []` → `dependencies = ["openai"]`。
- `requirements.txt`：由仅 `pytest` 一行，追加 `openai`（不写死版本号，或写一个宽松下限，由优化者定）。
- 仅新增 **`openai` 一个**运行时第三方依赖；不引入 anthropic / numpy（裁定 #5）。

## 6. 依赖（Dependencies）

- **运行时依赖（新）**：`openai`（SDK 客户端）；标准库 `os` / `typing`。
- **运行时依赖（既有）**：`config`（LLM 常量）。
- **测试依赖**：`pytest`（已具备）；测试不依赖 openai 已安装（惰性 import + fake 注入）。
- **顺序依赖**：`config.py`（加常量）→ `llm.py`（依赖 config + openai）→ `pyproject.toml`/`requirements.txt`（依赖声明）→ `tests/test_llm.py`。
- **前置条件**：本机 Python 3.13.9 + pytest 8.4.2；git 已初始化（不涉及本事务）；无需真实 API key（测试用 fake）。
- **对既有模块的依赖**：无（`llm.py` 只依赖 `config`，不被任何既有模块 import；是纯新增底座）。

## 7. 风险（Risks）

| 风险 | 缓解 |
|---|---|
| 1. **惰性 import 与注入边界**：若实现错误，测试仍会触发 `import openai` 或真实 client 构建，违背 mock-first | 测试断言「注入 fake 时 `openai` 不被 import、真实 client 不被构建」（可用 monkeypatch 探测 `openai` 导入）；§10 用例覆盖 |
| 2. **API key 读取边界**：key 缺失时行为未定义（静默 None 会导致 SDK 报难懂的错） | 明确：构建真实 client 时 key 缺失 → 抛 `ValueError`；测试用 monkeypatch 设置 / 删除 `DEEPSEEK_API_KEY` 覆盖 |
| 3. **依赖引入失控**（写成 `openai` + 顺手加 numpy/anthropic，或写死过宽版本） | 仅 `openai` 一个（裁定 #5）；评审者核对 `pyproject.toml`/`requirements.txt` diff |
| 4. **接口过宽**（把 `chat_json`/tool calling/多 provider 抽象带进来） | §4「明确非目标」逐条列出；`LLMClient` 只暴露 `complete()` 一个方法（裁定 #3） |
| 5. **`complete()` 返回值解析脆弱**（`resp.choices[0].message.content` 为 None / 结构不符） | 测试用 fake 返回规范结构；`content` 为 None 时按空串处理或上抛，由优化者钉死 |
| 6. **config docstring 失准**（加了 LLM 常量但 docstring 仍称「不含 LLM 参数」） | §5.1 明确同步更新 docstring，验收 §9.3 覆盖 |
| 7. **范围蔓延**（把 `AgentExecutor`/`Evaluator`/真实冒烟脚本带进自动测试） | §4 非目标明确；真实调用仅手工冒烟、不入 `tests/` |

## 8. 实施顺序（Implementation Order）

1. `evoagent/config.py`：追加 3 常量 + 更新 docstring。
2. `pyproject.toml` / `requirements.txt`：声明 `openai` 依赖。
3. `evoagent/llm.py`：`LLMClient.__init__`（client 注入）→ 惰性构建真实 client → `complete()`。
4. `tests/test_llm.py`：fake client + 各用例。
5. 运行验证命令（§10），确认全绿。

## 9. 验收标准（Acceptance Criteria）

1. **`config.py`**：新增 `LLM_BASE_URL` / `LLM_MODEL` / `LLM_API_KEY_ENV` 三常量；`LLM_API_KEY_ENV` 是环境变量名；**无任何 API key 明文入仓库**；模块 docstring 已不再声称「不含 LLM 参数」。
2. **`llm.py`**：存在且 `import evoagent.llm` 成功；`LLMClient` 只暴露 `complete(prompt: str) -> str` 一个方法（无 `chat_json`、无 anthropic、无多 provider 适配层）。
3. **注入扩展点**：`LLMClient(client=...)` 可注入 OpenAI 兼容 client；注入后 `complete()` 使用注入的 client，**不 import openai、不构建真实 client、不发请求**。
4. **`complete()` 语义**：把 prompt 作为单条 user 消息调用底层 client，返回 `resp.choices[0].message.content`（纯文本出）。
5. **key 读取**：未注入 client 时，从 `os.environ[LLM_API_KEY_ENV]` 读 key；缺失则抛 `ValueError`（清晰报错）。
6. **依赖**：`pyproject.toml` `dependencies == ["openai"]`；`requirements.txt` 含 `openai` 与 `pytest`；**未**引入 anthropic / numpy。
7. **测试**：`tests/test_llm.py` 全部 PASSED，且全量 `python -m pytest` 全绿（既有 63 项无回归），无失败、无跳过掩盖；**全程不发真实请求**。
8. **无越界**：不含 `AgentExecutor`/`tools.py`/`Evaluator`/`chat_json`/tool calling、真实 LLM 调用（除手工冒烟）、git 操作、其它第三方依赖。

## 10. 验证策略（Verification Strategy）

在项目根目录运行：

```
python -m pytest tests/test_llm.py -v
```

并确认全量回归：

```
python -m pytest -v
```

**用例要求（`test_llm.py`，全部 mock，不发真实请求）**：

- **注入 fake**：`LLMClient(client=fake)` 后 `complete("hello")` 返回 fake 预设文本；断言 fake 收到的 `messages == [{"role": "user", "content": "hello"}]` 且 `model == config.LLM_MODEL`。
- **未注入 + 惰性构建**：monkeypatch `os.environ[LLM_API_KEY_ENV]` 为某值，未注入 client 时 `complete()` 走真实构建路径（用 fake openai 模块或 monkeypatch 探测 `openai.OpenAI` 被以 `base_url=config.LLM_BASE_URL` 调用）；此用例若难以离线断言，可降级为「key 缺失抛 `ValueError`」的覆盖。
- **key 缺失**：monkeypatch 删除 `LLM_API_KEY_ENV` 环境变量，未注入 client 时 `complete()` 抛 `ValueError`。
- **mock-first 强化**：注入 fake 时断言 `openai` 未被 import（如 `sys.modules` 探测或 monkeypatch `builtins.__import__`），证明测试路径不触碰 SDK。
- **`content` 为 None**（若裁定按空串处理）：fake 返回 `content=None` 时 `complete()` 按约定返回空串或上抛，行为确定。

**手工冒烟（非自动测试，不入 `tests/`，编码者按需执行并记录到 `execution.md`）**：

```
# 设好环境变量后，在 REPL/脚本中真实调用一次
# export DEEPSEEK_API_KEY=...（绝不可写入仓库）
python -c "from evoagent.llm import LLMClient; print(LLMClient().complete('你好'))"
```

该冒烟**不是验收必需**（无 key 环境可跳过），仅用于人工确认真实路径可用；其输出 / 结果记入 `execution.md`，**不进入自动测试**。
