# 事务 0004 结果（Result）

> 编码者（Coder）产出。记录变更文件、测试/验证、结果、局限与后续建议。

---

## 1. 变更的文件

**新建（2）：**

| 文件 | 内容 |
|---|---|
| `evoagent/llm.py` | `LLMClient`：窄接口单方法 `complete()`，client 可注入，惰性 import openai，key 缺失抛 `ValueError` |
| `tests/test_llm.py` | mock-first 5 个用例（注入 fake / content=None / key 缺失 / 惰性构建 / 注入路径不 import openai） |

**修改（3）：**

| 文件 | 变更 |
|---|---|
| `evoagent/config.py` | 追加 `LLM_BASE_URL`/`LLM_MODEL`/`LLM_API_KEY_ENV` 三常量 + 更新 docstring（既有常量未动） |
| `pyproject.toml` | `dependencies=[]` → `["openai>=1.0"]` + 依赖注释更新 |
| `requirements.txt` | 追加 `openai>=1.0` |

未修改 `models.py`、`storage.py`、`registry.py`、`trace.py`、`store.py`、`retriever.py`、`__init__.py`、`.gitignore`、`docs/system_design.md`；未产生运行时数据文件。

## 2. 执行的验证命令及输出摘要

**命令 1：包导入**
```
python -c "import evoagent.llm; from evoagent.llm import LLMClient"
```
输出：`import ok`

**命令 2：定向测试**
```
python -m pytest tests/test_llm.py -v
```
输出摘要：`collected 5 items`，**`5 passed in 1.83s`**。

**命令 3：全量回归**
```
python -m pytest -v
```
输出摘要：`collected 68 items`，**`68 passed in 3.45s`**（既有 63 项无回归、无失败、无 skipped）。

**命令 4：明文 key 人工复核**
```
grep -rn "api_key\|API_KEY\|sk-" evoagent/config.py evoagent/llm.py
```
结果：仅 `LLM_API_KEY_ENV`（环境变量名）与 `os.environ.get(config.LLM_API_KEY_ENV)` 取值；**无任何 key 明文、无 `sk-` 前缀值**。

**命令 5：docs 未修改复核**
`git status` 中无 `docs/system_design.md`。

## 3. 验证结果

**验收标准逐条：**

1. ✅ `config.py` 新增 `LLM_BASE_URL`/`LLM_MODEL`/`LLM_API_KEY_ENV`；`LLM_API_KEY_ENV` 是环境变量名；无 key 明文入仓库；docstring 已不再声称「不含 LLM 参数」。
2. ✅ `llm.py` 存在且可导入；`LLMClient` 只暴露 `complete(prompt: str) -> str` 一个公开方法（无 chat_json/anthropic/多 provider）。
3. ✅ 注入扩展点：`LLMClient(client=fake)` 后 `complete()` 用 fake，不 import openai、不构建真实 client、不发请求。
4. ✅ `complete()` 语义：单条 user 消息调用 `chat.completions.create(model=config.LLM_MODEL, messages=[...])`，返回 `resp.choices[0].message.content`；`None` → `""`。
5. ✅ key 读取：`os.environ.get(config.LLM_API_KEY_ENV)`；缺失/空串 → `ValueError`。
6. ✅ 依赖：`dependencies == ["openai>=1.0"]`，注释已更新（无「不引入第三方」残留）；`requirements.txt` 含 `pytest` 与 `openai>=1.0`；未引入 anthropic/numpy。
7. ✅ 测试全绿（全量 68 passed），全程不发真实请求。
8. ✅ 无越界：不含 AgentExecutor/tools.py/Evaluator/chat_json/tool calling、真实 LLM 调用（手工冒烟未执行）、anthropic/numpy/其它第三方依赖。

**结论：成功。** 全部验收标准满足，全部测试通过。

## 4. 已知局限

- **`complete() -> str` 丢弃 token/cost/latency**（§11.10 已登记的扩展点）：设计 §6 `ExecutionTrace.usage = {total_tokens, total_cost, total_latency_ms}` 需要 LLM 响应的 `.usage`/计时，而当前 `complete()` 只回文本。下一个消费者 `AgentExecutor` 事务将需二选一：(a) 扩展 `complete()` 返回更丰富对象、(b) 新增伴生方法（如 `complete_with_usage()`）、(c) 执行层绕过分层直调 SDK（应避免）。
- `chat_json()` 未实现（裁定 #3 收窄），属评估层 `Evaluator`（LLM-as-judge）未来需求。
- 真实调用仅手工冒烟验证（本事务无 key 环境未执行），未进入自动测试。

## 5. 后续问题

1. `AgentExecutor` 事务需解决 `usage` 采集与 `complete() -> str` 的接口张力（见 §4）。
2. `Evaluator` 的 LLM-as-judge 需要 `chat_json()`（结构化 JSON 输出），届时扩展 `llm.py`。
3. 手工冒烟：设好 `DEEPSEEK_API_KEY` 后运行 `LLMClient().complete('你好')` 确认真实路径。

## 6. 建议的下一步

建议下一个事务（`0005`）落地 `AgentExecutor`（依赖已就绪的 `SkillRetriever`/`SkillRegistry`/`LLMClient`/`Task`/`TraceStore`），并在其中解决 `usage` 采集扩展点；或先做 `Evaluator`（含 `chat_json` 扩展）。

## 7. 提交

- 提交信息：`0004: 落地 OpenAI 兼容 LLM 薄封装 llm.py`
- 提交哈希：`e6a8b543109a798338b09d517a6721502319ee66`（`git rev-parse HEAD`，短哈希 `e6a8b54`）
