# 事务 0001 结果（Result）

> 编码者（Coder）产出。记录变更文件、测试/验证、结果、局限与后续建议。

---

## 1. 变更的文件（全部为新建）

| 文件 | 内容 |
|---|---|
| `pyproject.toml` | PEP 621 元信息（`name="evoagent"`、`version="0.1.0"`、`requires-python=">=3.10"`），`dependencies=[]`（无运行时第三方依赖），setuptools 打包 `evoagent` |
| `requirements.txt` | 仅 `pytest` |
| `evoagent/__init__.py` | 暴露 `__version__ = "0.1.0"` |
| `evoagent/models.py` | 8 个 dataclass（`FewShot` `ToolSpec` `Skill` `TraceStep` `ExecutionTrace` `EvaluationResult` `Experience` `BenchmarkTask`）+ 递归序列化 `to_dict` / `from_dict` |
| `evoagent/config.py` | `DATA_DIR` / `DB_PATH` / `RETRIEVAL_FALLBACK_THRESHOLD=0.3` / `OBJECTIVE_WEIGHT=0.7` / `JUDGE_WEIGHT=0.3` / `PASS_THRESHOLD=0.6` / `SQLITE_WAL_ENABLED=True`；**无** LLM 参数 |
| `evoagent/storage.py` | `Storage`：`connect()`（mkdir -p + WAL）、`init_schema()`（5 表）、通用参数化 CRUD `insert` / `query` / `update` / `delete` |
| `tests/test_models.py` | 8 个 dataclass round-trip、嵌套 round-trip、`passed` 三态、None/空集区分、默认值用例 |
| `tests/test_storage.py` | 建表 / schema 锁定（`PRAGMA table_info`）/ CRUD round-trip / WAL，全部 `tmp_path` 隔离 |

未修改任何已存在文件；未产生 `data/`、egg-info、`__pycache__`、`.pytest_cache` 等残留。

## 2. 执行的验证命令及输出摘要

**命令 1：包导入**
```
python -c "import evoagent; print('import ok, version =', evoagent.__version__)"
```
输出：`import ok, version = 0.1.0`

**命令 2：单元测试**
```
python -m pytest tests/test_models.py tests/test_storage.py -v
```
输出摘要：`collected 26 items`，**`26 passed in 0.90s`**，无失败、无 skipped、无 error。

**命令 3：SQL 唯一性人工复核**
```
grep -rn "import sqlite3" evoagent/
```
结果：真实 `import sqlite3` 语句**仅**出现在 `evoagent/storage.py`（第 13 行）；`models.py` / `config.py` / `__init__.py` 均无（`storage.py` 前两处命中为其 docstring 中的文字性描述，非 import 语句）。

## 3. 验证结果

- **验收标准逐条**：
  1. ✅ 包可导入，`pyproject.toml` 定义完整，pytest 可收集（26 项）。
  2. ✅ 8 个 dataclass 字段名 / 类型与 §4.1 一致，无增删（含 `BenchmarkTask` 字段顺序调整，见 execution.md §2.3）。
  3. ✅ 各 dataclass 递归 round-trip 通过；嵌套 dataclass 类型正确；`None`/空集区分；`passed` 三态精确保留。
  4. ✅ `Storage` 可对任意路径（含 `tmp_path`）建库并建齐 5 表；`storage.py` 是唯一 `import sqlite3` 的模块。
  5. ✅ `trace_steps` 含 `truncated`（INTEGER 默认 0）；各表关键列经 `PRAGMA table_info` 断言锁定。
  6. ✅ `config.py` 定义全部要求常量，且不含任何 LLM provider/model/key 常量。
  7. ✅ `requirements.txt` 仅 `pytest`；`pyproject.toml` 无运行时第三方依赖；未引入 openai/anthropic/numpy。
  8. ✅ `test_models.py` 与 `test_storage.py` 全部 PASSED，无跳过掩盖。
  9. ✅ 无上层业务逻辑、无真实 LLM 调用 / 网络请求、未 `git init`。

**结论：成功。** 全部验收标准满足，全部测试通过。

## 4. 已知局限

- **通用 `query` 不自动反序列化 JSON**：JSON 字段（`metrics` / `usage` / `objective` / `rubric_scores`）经 `insert`/`update` 序列化为 TEXT 后，`query` 以 JSON 字符串返回原始值；反序列化（`json.loads`）需由后续领域门面层在读取时完成（通用 CRUD 无法判定哪列是 JSON）。此为 §4.5「反序列化」侧的后置，不影响本事务验收。
- 本事务未实际执行 `pip install -e .`（避免在源码树生成 build/egg-info 残留）；可安装性由 PEP 621 + `[build-system]` + `packages=["evoagent"]` 结构支撑，未在隔离环境实测。
- 系统设计遗留的 `Task` dataclass 缺口（§11 非目标 4）与「git 追踪 JSON diff」前提（§11 非目标 8）仍待后续事务处理。

## 5. 后续问题

1. 领域门面层（`SkillRegistry` / `TraceStore` / `EvalStore`）落地时需在各自门面内实现 JSON 字段的 `json.loads` 反序列化，并落实 `trace_steps.content` 4000 字符截断 + `truncated=True`（归属 TraceStore）。
2. 实现 `Task` 前需先回补系统设计的 `Task` 字段定义（当前设计仅 `BenchmarkTask` 有定义）。
3. Skill 内容 JSON 归档与版本 diff 依赖 git，需在 SkillRegistry 事务前决策 `git init`。

## 6. 建议的下一步

建议下一个事务（`0002`）落地**存储领域门面层**：`SkillRegistry` / `TraceStore` / `EvalStore`（直接消费本事务的 `Storage` 与 `models.py` 数据契约），并在门面内补齐 JSON 反序列化与截断逻辑。亦可并行评估 `evoagent/llm.py` 的 provider 选型（届时引入 openai/anthropic SDK 与 LLM 配置常量）。
