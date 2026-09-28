# 事务 0004 最终任务规格说明（Task）

> 优化者（Optimizer）产出。本文件是编码者实现的**唯一依据**，自包含：编码者无需阅读 `plan.md` / `review.md` 即可执行。
> 依据：`plan.md` + `review.md` + `docs/system_design.md` + 事务 `0001`–`0003` 落地后的实仓源码 + 实仓核实 + 用户 5 条裁定。
>
> 说明：本仓库事务文件实际位于 `.agents/transactions/0004/`（顶层 `transactions/` 不存在）。下文路径均以 `.agents/transactions/0004/` 为准。

---

## 1. 目标（Objective）

落地底座层最后一块 `evoagent/llm.py` —— OpenAI 兼容的 LLM 薄封装，并首次引入运行时第三方依赖 `openai`：

- `evoagent/config.py`：追加 3 个 LLM 常量（`LLM_BASE_URL` / `LLM_MODEL` / `LLM_API_KEY_ENV`）并更新模块 docstring
- `evoagent/llm.py`：`LLMClient`（窄接口、单方法 `complete()`、纯文本入出、可注入 mock client）
- `pyproject.toml` / `requirements.txt`：声明 `openai` 依赖
- `tests/test_llm.py`：mock-first 单测（全程不发真实请求）

**落实的用户 5 条裁定（既定输入，不再讨论）**：① 只走 OpenAI 兼容路径、不做 anthropic / 多 provider 适配层；② `config.py` 加 `LLM_BASE_URL`/`LLM_MODEL`/`LLM_API_KEY_ENV`（环境变量名），key 仅从环境变量读取、绝不进仓库；③ 窄接口单方法、纯文本入出、留注入扩展点、不写抽象；④ mock-first 全单测不发真实请求，真实调用仅手工冒烟；⑤ 运行时新增 `openai` 一个第三方依赖。

## 2. 上下文（Context）

- 事务 `0001`（底座）、`0002`（门面）、`0003`（检索器）已落地，全量 63 项测试通过，git `main`@`db105a5`。
- **实仓现状（已核实）**：
  - `evoagent/llm.py` **不存在**。
  - `evoagent/config.py` **无任何 LLM 常量**；其模块 docstring 明示「不含任何 LLM provider / model / API key 等参数（这些随 `llm.py` / evaluator 事务引入）」——本事务正是该延后项的兑现时点。
  - `evoagent/models.py` 已含 9 个 dataclass（`Task` 无 `task_id` + §5–§11 的 8 个），本事务**不触碰**。
  - `pyproject.toml`：`dependencies = []`，且第 10 行注释「本事务不引入任何第三方运行时依赖；仅标准库 + 开发期 pytest（见 requirements.txt）」——加 `openai` 后此注释失准，须同步更新（见 §4.3）。
  - `requirements.txt`：仅 `pytest`。
  - `openai 2.38.0` 已安装（v1.x 客户端 API：`openai.OpenAI(...)`、`resp.choices[0].message.content`）。
  - 现有测试对 `config` 无内容断言（`test_trace.py` 仅用 `TRACE_CONTENT_MAX_CHARS`），加 LLM 常量**零回归**。
- **设计分层（§2）**：`llm.py` 属底座层，只依赖 `config`，是纯新增底座，无既有模块 import 它。
- **环境**：Python 3.13.9（≥3.10）、pytest 8.4.2。

## 3. 范围（Scope）

**做（In scope）**

1. `evoagent/config.py`：追加 3 个 LLM 常量 + 更新模块 docstring（§4.1）。
2. `evoagent/llm.py`：`LLMClient`（§4.2）。
3. `pyproject.toml`：`dependencies` 由 `[]` 改为 `["openai>=1.0"]`，并同步更新依赖注释（§4.3）。
4. `requirements.txt`：追加 `openai>=1.0`（§4.3）。
5. `tests/test_llm.py`（§4.4）。

**不做（Out of scope，明确非目标）** —— 详见 §11。

## 4. 需求（Requirements）

### 4.1 `evoagent/config.py` —— 3 个 LLM 常量 + docstring

在既有常量之后追加（**不改动**任何既有常量名 / 值）：

```python
# ── LLM（事务 0004 引入，OpenAI 兼容路径） ────────────────────────────────
LLM_BASE_URL = "https://api.deepseek.com"   # OpenAI 兼容 provider base_url（可覆盖）
LLM_MODEL = "deepseek-chat"                 # 默认模型
LLM_API_KEY_ENV = "DEEPSEEK_API_KEY"        # 环境变量名；key 值绝不进仓库，仅运行时读取
```

- `LLM_API_KEY_ENV` 是**环境变量名**（非 key 值）；真实 key 由运行时 `os.environ` 读取，**绝不写入仓库**。
- **更新模块 docstring**：当前首段「…不含任何 LLM provider / model / API key 等参数（这些随 `llm.py` / evaluator 事务引入）」已失准，须改为反映「已含 OpenAI 兼容路径的 LLM 常量（`LLM_BASE_URL` / `LLM_MODEL` / `LLM_API_KEY_ENV`），API key 仅通过环境变量在运行时读取、绝不以明文进入仓库」。措辞可微调，但**不得**再声称「不含 LLM 参数」。

### 4.2 `evoagent/llm.py` —— `LLMClient`

**为什么存在**：屏蔽 OpenAI 兼容 provider 的调用细节，对上暴露窄接口；是执行 / 评估 / 演化层的共同 LLM 底座（§2/§13）。

**窄接口（单方法、纯文本入出；裁定 #3）** —— 精确实现如下（`from . import config`）：

```python
"""LLM 薄封装（OpenAI 兼容路径）。窄接口：单方法 `complete()` 文本入出。

只依赖 `config`；不实现 anthropic、多 provider 适配层、chat_json、tool calling。
`openai` 仅在构建真实 client 时惰性 import，注入路径完全不触碰 openai 模块。
"""

import os

from . import config


class LLMClient:
    """OpenAI 兼容 LLM 客户端。`client` 可注入（测试注入 fake，不 import openai）。"""

    def __init__(self, client=None):
        self._client = client  # None = 惰性构建真实 client

    def _get_client(self):
        if self._client is not None:
            return self._client
        api_key = os.environ.get(config.LLM_API_KEY_ENV)
        if not api_key:
            raise ValueError(
                f"环境变量 {config.LLM_API_KEY_ENV} 未设置，无法初始化 LLM client"
            )
        import openai  # 惰性 import：仅在构建真实 client 时
        self._client = openai.OpenAI(base_url=config.LLM_BASE_URL, api_key=api_key)
        return self._client

    def complete(self, prompt: str) -> str:
        resp = self._get_client().chat.completions.create(
            model=config.LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
        )
        content = resp.choices[0].message.content
        return content if content is not None else ""
```

**语义钉死（裁定）**：

- **`complete(prompt: str) -> str` 是对上暴露的唯一方法**。把 `prompt` 作为单条 `user` 消息调用底层 OpenAI 兼容 client，返回 `resp.choices[0].message.content`（纯文本出）。**无 `chat_json`、无 anthropic、无多 provider 适配层**。
- **`client` 注入（裁定 #3/#4 的扩展点）**：`__init__(client=None)`。`client` 为 `None` 时惰性构建真实 client；注入时直接用（测试注入 fake，不构建真实 client、不 `import openai`）。将来第二 provider 只需包装成同形 client 注入，无需改 `LLMClient`。
- **惰性 import openai**：`llm.py` **不在模块顶层 `import openai`**，只在 `_get_client()` 的「构建真实 client」路径内局部 `import openai`。注入路径完全不触碰 openai 模块。
- **API key 缺失（裁定 #2 + 统一口径）**：用 `os.environ.get(config.LLM_API_KEY_ENV)` 取值；`api_key` 为 `None` 或空串（`not api_key`）→ 抛 `ValueError`（清晰配置错误），**不**静默失败。key 校验在 `import openai` 之前，故「key 缺失」路径不触碰 openai。
- **`content` 为 `None`（裁定）**：`resp.choices[0].message.content` 为 `None` 时返回**空串 `""`**（保证 `complete()` 恒返回 `str`，不因 None 崩溃）。
- **错误处理边界**：`complete()` 对 SDK 抛出的异常**不分类、不吞**，原样上抛——`error_type`（infra/task）分类属 `AgentExecutor`（§3.2），不在本事务。

### 4.3 依赖（裁定 #5 + 版本下界）

- `pyproject.toml`：`dependencies = []` → `dependencies = ["openai>=1.0"]`；**同步更新**第 10 行注释「本事务不引入任何第三方运行时依赖；仅标准库 + 开发期 pytest（见 requirements.txt）」为反映「运行时第三方依赖 `openai`（OpenAI 兼容 SDK）；开发期依赖 pytest（见 requirements.txt）」的措辞（不得残留「不引入任何第三方运行时依赖」）。
- `requirements.txt`：由仅 `pytest` 一行，改为两行：

  ```
  pytest
  openai>=1.0
  ```

- **版本下界（裁定）**：写 `openai>=1.0`——代码用 v1.x API（`openai.OpenAI(...)` / `resp.choices[0].message.content`），设下界避免旧版 `openai<1.0`（`openai.ChatCompletion` 接口）直接报错。
- 仅新增 **`openai` 一个**运行时第三方依赖；**不**引入 anthropic / numpy（裁定 #5）。

### 4.4 测试要求

`tests/test_llm.py` 全部 mock、全程**不发真实请求**。fake client 的最小接口：`client.chat.completions.create(model=..., messages=...) -> resp`，其中 `resp.choices[0].message.content` 为文本（`str` 或 `None`）。可用 `types.SimpleNamespace` 构造，例如：

```python
from types import SimpleNamespace

def _fake_client(response_text):
    calls = []
    def create(model=None, messages=None, **kwargs):
        calls.append({"model": model, "messages": messages})
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=response_text))]
        )
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))), calls
```

（该 helper 为推荐写法，实现可自由变体，但 fake 必须暴露上述 `chat.completions.create` 接口，且能记录调用参数。）

用例清单见 §10。

## 5. 约束（Constraints）

1. **语言 / 运行时**：Python 3.10+（本机 3.13.9）。
2. **运行时依赖**：标准库（`os`/`typing`）+ **`openai>=1.0`（唯一新增第三方）**。**不**引入 anthropic / numpy / 其它第三方。
3. **分层**：`llm.py` 只依赖 `config`，不依赖任何既有模块，也不被任何既有模块 import；`storage.py` 仍是全项目唯一 `import sqlite3`/写 SQL 处（`llm.py` 不 import sqlite3）。
4. **不改既有**：除 §4.1/§4.3 外，不改 `models.py`/`storage.py`/`registry.py`/`trace.py`/`store.py`/`retriever.py`/`__init__.py`；不改 `config.py` 既有常量。
5. **不越界**：不实现 `AgentExecutor`/`tools.py`/`Evaluator`/`ExperienceExtractor`/`SkillEvolver`、`chat_json()`、tool calling、多轮编排、多 provider 适配层、错误分类（infra/task）。
6. **安全**：API key 绝不以明文进仓库（仅环境变量名 `LLM_API_KEY_ENV` 进 `config.py`）。
7. **命名**：类 `PascalCase`、方法/函数 `snake_case`、常量 `UPPER_SNAKE_CASE`；三常量名 `LLM_BASE_URL`/`LLM_MODEL`/`LLM_API_KEY_ENV` 不可改。
8. **错误处理**：仅抛标准异常（`ValueError`）；不自定义异常类、不吞 SDK 异常。

## 6. 相关文件 / 模块（Relevant Files / Modules）

**本事务新建：**

| 文件 | 内容 |
|---|---|
| `evoagent/llm.py` | `LLMClient`（§4.2） |
| `tests/test_llm.py` | mock-first 单测（§4.4/§10） |

**本事务修改：**

| 文件 | 变更 |
|---|---|
| `evoagent/config.py` | 追加 3 个 LLM 常量 + 更新 docstring（§4.1） |
| `pyproject.toml` | `dependencies=["openai>=1.0"]` + 更新依赖注释（§4.3） |
| `requirements.txt` | 追加 `openai>=1.0`（§4.3） |

**只读参照（不修改）：** `evoagent/models.py`、`evoagent/storage.py`、`evoagent/skills/registry.py`、`evoagent/skills/retriever.py`、`evoagent/execution/trace.py`、`evoagent/eval/store.py`、`docs/system_design.md`、`.agents/transactions/0001/`–`0004/` 的历史产物（`plan.md`/`review.md` 等不可改）。

## 7. 推荐的实现策略（Recommended Implementation Strategy）

依赖关系：`config.py`（加常量 + docstring）→ `pyproject.toml`/`requirements.txt`（依赖声明）→ `llm.py`（`LLMClient`）→ `tests/test_llm.py` → 验证 → 收尾提交。

1. **`config.py`**：追加 3 常量 + 更新 docstring。
2. **依赖声明**：`pyproject.toml` `dependencies=["openai>=1.0"]` + 注释更新；`requirements.txt` 追加 `openai>=1.0`。
3. **`llm.py`**：按 §4.2 的精确代码实现 `LLMClient.__init__` / `_get_client`（惰性 import + key 校验）→ `complete()`。
4. **`tests/test_llm.py`**：按 §10 用例清单写。
5. **验证**：运行 §10 命令，确认全绿。
6. **收尾提交**：按 §10 末尾执行。

## 8. 预期变更（Expected Changes）

| 文件 | 变更性质 |
|---|---|
| `evoagent/config.py` | 修改：追加 3 个 LLM 常量 + docstring 更新（既有常量不动） |
| `evoagent/llm.py` | 新建 |
| `pyproject.toml` | 修改：`dependencies` 改为 `["openai>=1.0"]` + 注释更新 |
| `requirements.txt` | 修改：追加 `openai>=1.0` |
| `tests/test_llm.py` | 新建 |

（不修改 `models.py`、`storage.py`、`registry.py`、`trace.py`、`store.py`、`retriever.py`、`__init__.py`、`.gitignore`、`docs/system_design.md`；不产生运行时数据文件。）

## 9. 验收标准（Acceptance Criteria）

1. **`config.py`**：新增 `LLM_BASE_URL`/`LLM_MODEL`/`LLM_API_KEY_ENV` 三常量；`LLM_API_KEY_ENV` 是环境变量名（非 key 值）；**无任何 API key 明文进仓库**；模块 docstring 已不再声称「不含 LLM 参数」。
2. **`llm.py`**：存在且 `import evoagent.llm` 成功；`LLMClient` 只暴露 `complete(prompt: str) -> str` 一个公开方法（无 `chat_json`、无 anthropic、无多 provider 适配层）。
3. **注入扩展点**：`LLMClient(client=fake)` 后 `complete()` 使用注入的 fake，**不 `import openai`、不构建真实 client、不发请求**。
4. **`complete()` 语义**：把 `prompt` 作为单条 `{"role":"user","content":prompt}` 调用底层 client 的 `chat.completions.create(model=config.LLM_MODEL, messages=[...])`，返回 `resp.choices[0].message.content`；`content` 为 `None` 时返回 `""`。
5. **key 读取**：未注入 client 时用 `os.environ.get(config.LLM_API_KEY_ENV)` 读 key；缺失或空串 → 抛 `ValueError`（清晰报错）。
6. **依赖**：`pyproject.toml` `dependencies == ["openai>=1.0"]` 且第 10 行注释已更新（不含「不引入任何第三方运行时依赖」）；`requirements.txt` 含 `pytest` 与 `openai>=1.0`；**未**引入 anthropic / numpy。
7. **测试**：`tests/test_llm.py` 全部 PASSED，全量 `python -m pytest` 全绿（既有 63 项无回归），无失败、无跳过掩盖；**全程不发真实请求**。
8. **无越界**：不含 `AgentExecutor`/`tools.py`/`Evaluator`/`chat_json`/tool calling、真实 LLM 调用（除手工冒烟）、anthropic/numpy、其它第三方依赖。

## 10. 验证策略（Verification Strategy）

在项目根目录运行：

```
python -m pytest tests/test_llm.py -v
```

并确认全量回归：

```
python -m pytest -v
```

**用例要求（`test_llm.py`，全部 mock，不发真实请求）：**

- **注入 fake**：`LLMClient(client=fake)` 后 `complete("hello")` 返回 fake 预设文本；断言 fake 收到的 `messages == [{"role": "user", "content": "hello"}]` 且 `model == config.LLM_MODEL`。
- **`content` 为 None**：fake 返回 `content=None` 时 `complete()` 返回 `""`。
- **key 缺失**：`monkeypatch.delenv(config.LLM_API_KEY_ENV, raising=False)` 后，未注入 client 的 `LLMClient().complete("x")` 抛 `ValueError`（且此路径不 import openai）。
- **未注入 + 惰性构建（保留，不降级）**：`monkeypatch.setenv(config.LLM_API_KEY_ENV, "test-key")`；`monkeypatch.setattr(openai, "OpenAI", fake_factory)`（fake_factory 返回能回文本的 fake client）；`LLMClient().complete("hi")` 返回 fake 文本，且断言 `fake_factory` 被以 `base_url=config.LLM_BASE_URL`、`api_key="test-key"` 调用。
- **惰性 import 强化（稳健方式）**：对注入路径，`monkeypatch` 拦截 `builtins.__import__`（若请求 `"openai"` 则抛 `AssertionError`），再 `LLMClient(client=fake).complete("hi")` 正常返回——证明注入路径不 import openai。**不要**用 `"openai" not in sys.modules` 做全局断言（进程级全局态，脆弱）。

**额外人工复核（非 pytest，编码者确认并记入 `execution.md`）：**

```
grep -rn "api_key\|API_KEY\|sk-" evoagent/config.py evoagent/llm.py
```

结果中 `config.py`/`llm.py` 不得出现任何真实 key 明文（只允许 `LLM_API_KEY_ENV` 环境变量名与 `os.environ.get(...)` 取值）；并确认 `git status` 中无 `docs/system_design.md` 改动。

**手工冒烟（非自动测试、非验收必需，不入 `tests/`，编码者按需执行并记录到 `execution.md`）：**

```
# 设好环境变量后（绝不可写入仓库）：
# python -c "from evoagent.llm import LLMClient; print(LLMClient().complete('你好'))"
```

无 key 环境可跳过；仅用于人工确认真实路径可用。

**收尾提交（用户已授权，必须执行）**：

全部验证通过后，Coder **一次性提交全部变更**：

```
git add -A && git commit -m "0004: 落地 OpenAI 兼容 LLM 薄封装 llm.py"
```

- 提交信息**首行**必须以 `0004: ` 开头 + 一句目标概括（上例为建议措辞，可用同义简洁一句话）。
- **不 push、不 amend、不建分支、不 force-push**（仅本地提交）。
- **把提交哈希记入 `result.md`**（`git rev-parse HEAD` 取哈希）。

## 11. 明确的非目标（Explicit Non-Goals）

本任务**不做**以下任何事（防止范围蔓延）：

1. **anthropic SDK**、任何多 provider 适配层、抽象 provider 接口（裁定 #1/#3）。
2. **`chat_json()`**：设计 §13 虽列了它，但裁定 #3 收窄为「单方法、纯文本入出」；`chat_json` 属 `Evaluator`（§7 LLM-as-judge）的未来需求，留待评估层事务。
3. **tool calling / 结构化输出 / 多轮消息编排**：`AgentExecutor`（§3.2）的未来需求。
4. **错误分类**（§3.2 `error_type` infra/task）：归属 `AgentExecutor`，`llm.py` 只透传异常、不分类、不吞。
5. **`AgentExecutor` / `tools.py` / `Evaluator` / `ExperienceExtractor` / `SkillEvolver` / 任何上层模块**。
6. **真实 LLM 调用 / 网络请求**：仅手工冒烟（§10，非验收必需），不进自动测试（裁定 #4）。
7. **numpy、anthropic 等其它依赖**：仅 `openai>=1.0` 一个（裁定 #5）。
8. **修改 `docs/system_design.md`**（只读）。
9. **除收尾提交（§10）外的任何 git 操作**：不 push、不 amend、不建分支、不 force-push、不拆多次提交。
10. **`complete() -> str` 的 usage 扩展**：本事务按裁定 #3 只回文本，**丢弃** token/cost/latency。此为**已登记的已知局限与后续决策点**——设计 §6 `ExecutionTrace.usage = {total_tokens, total_cost, total_latency_ms}` 需要 LLM 响应的 `.usage`/计时，而当前 `complete()` 不提供；`AgentExecutor`（下一个消费者）事务将需二选一：(a) 扩展 `complete()` 返回更丰富对象、(b) 新增伴生方法（如 `complete_with_usage()`）、(c) 执行层绕过分层直调 SDK（**应避免**）。本事务不实现，但编码者须在 `result.md` 的「已知局限」中记录此扩展点。

---

### 已确认的决策（记录以备查；无「实现前需确认」的阻塞项）

| 裁定点 | 结论 |
|---|---|
| LLM 默认配置 | **DeepSeek 默认**：`LLM_BASE_URL="https://api.deepseek.com"`、`LLM_MODEL="deepseek-chat"`、`LLM_API_KEY_ENV="DEEPSEEK_API_KEY"`。理由：用户裁定 #1「适配 DeepSeek 等 OpenAI 兼容 provider」、#2「如 DEEPSEEK_API_KEY」已点名 DeepSeek。三值均为**可覆盖默认值**，常量名不可改 |
| `content=None` | 返回 `""`（保证 `complete()` 恒返回 `str`） |
| key 取值口径 | `os.environ.get(LLM_API_KEY_ENV)`；`None` 或空串 → `ValueError`；校验在 `import openai` 之前 |
| openai 版本下界 | `openai>=1.0`（v1.x API，本机 2.38.0 满足） |
| `pyproject.toml` 注释 | 依赖注释随 `dependencies` 一并更新，不残留「不引入第三方」 |
| `complete() -> str` 与 usage 张力 | 登记为已知局限 + 后续决策点（§11.10），本事务不扩展 |
| 测试边界 | 保留「未注入路径 monkeypatch `openai.OpenAI` 断言传参」；惰性 import 用 `builtins.__import__` 拦截，不用 `sys.modules` 全局断言 |
