# 事务 0004 执行报告（Execution）

> 编码者（Coder）产出。记录实际执行的步骤、重要实现决策及理由、与 `task.md` 的偏差、遇到的问题。

---

## 1. 实际执行的步骤

1. **阅读依据与核实**：阅读 `task.md`（完整）、`plan.md`/`review.md`/`context.md`（决策背景）、`project_state.md`、`active_transaction.md`、`docs/system_design.md`（§2/§3.2/§7/§13/§14）。读实仓源码（`config.py`、`pyproject.toml`、`requirements.txt`），确认与 task.md §2 一致（`config.py` 无 LLM 常量、docstring 明示「不含 LLM 参数」；`pyproject.toml` `dependencies=[]` + 第 10 行注释；`requirements.txt` 仅 `pytest`）。
2. **按依赖顺序实现**：`config.py`（docstring + 3 LLM 常量）→ `pyproject.toml`/`requirements.txt`（`openai>=1.0` 依赖声明）→ `llm.py`（`LLMClient`，按 §4.2 精确代码）→ `tests/test_llm.py`（5 用例）。
3. **验证**：`import evoagent.llm` 成功；`python -m pytest tests/test_llm.py -v` → 5 passed；全量 `python -m pytest -v` → **68 passed**；`grep -rn "api_key\|API_KEY\|sk-" evoagent/config.py evoagent/llm.py` 复核（无明文 key）。
4. **收尾提交**：按 §10 授权执行（见下）。

## 2. 重要的实现决策及理由

### 2.1 `llm.py` 按 §4.2 精确实现（窄接口 + 惰性 import + 注入扩展点）
`LLMClient` 只暴露 `complete(prompt: str) -> str` 一个公开方法（纯文本入出）；`__init__(client=None)` 注入扩展点；`openai` 仅在 `_get_client()` 的「构建真实 client」分支内局部 `import`（注入路径完全不触碰 openai 模块）；`content=None` 时返回 `""` 保证恒返回 `str`；SDK 异常不分类、原样上抛。

### 2.2 key 仅读环境变量、校验先于 import
`os.environ.get(config.LLM_API_KEY_ENV)` 取值；`None` 或空串（`not api_key`）→ 抛 `ValueError`，且校验在 `import openai` **之前**，故 key 缺失路径不触碰 openai。`config.py` 只存环境变量名 `LLM_API_KEY_ENV`，绝无 key 明文。

### 2.3 依赖声明与注释同步更新
`pyproject.toml` `dependencies=["openai>=1.0"]`（下界对齐 v1.x API），第 10 行注释由「不引入任何第三方运行时依赖」改为「运行时第三方依赖 openai…」；`requirements.txt` 追加 `openai>=1.0`。仅 `openai` 一个新增第三方，未引入 anthropic/numpy。

### 2.4 mock-first 测试
`tests/test_llm.py` 全程不发真实请求。fake client 用 `types.SimpleNamespace` 构造（暴露 `chat.completions.create` 并记录调用参数）；覆盖注入路径、`content=None`、key 缺失、惰性构建（monkeypatch `openai.OpenAI` 断言传参）、注入路径不 import openai（`builtins.__import__` 拦截，非 `sys.modules` 全局断言）。

## 3. 与 task.md 的偏差

无功能性偏差。`config.py` 仅追加 3 常量 + 更新 docstring（既有常量未动）；`pyproject.toml` 仅改依赖 + 注释；`requirements.txt` 仅追加一行；未改 `models.py`/`storage.py`/`registry.py`/`trace.py`/`store.py`/`retriever.py`/`__init__.py`；未改 `docs/system_design.md`。

## 4. 遇到的问题

无阻塞性问题。**手工冒烟未执行**：task.md §10 的手工冒烟（`LLMClient().complete('你好')`）标注为「非验收必需、无 key 环境可跳过」；本机无 `DEEPSEEK_API_KEY` 环境变量，故按 §10 跳过，真实路径可用性以「惰性构建」单测（monkeypatch `openai.OpenAI` 断言 `base_url`/`api_key` 传参）兜底。
