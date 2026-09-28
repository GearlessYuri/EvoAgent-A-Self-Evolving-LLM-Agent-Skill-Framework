# 事务 0002 结果（Result）

> 编码者（Coder）产出。记录变更文件、测试/验证、结果、局限与后续建议。

---

## 1. 变更的文件

**新建（9）：**

| 文件 | 内容 |
|---|---|
| `evoagent/skills/__init__.py` | 空包（docstring） |
| `evoagent/skills/registry.py` | `SkillRegistry`：register / get / get_active / list / promote / rollback / deprecate + JSON 归档 |
| `evoagent/execution/__init__.py` | 空包 |
| `evoagent/execution/trace.py` | `TraceStore`：save（含 4000 截断）/ get / list |
| `evoagent/eval/__init__.py` | 空包 |
| `evoagent/eval/store.py` | `EvalStore`：save_eval / get_eval / list_evals / save_experience / list_experiences |
| `tests/test_registry.py` | 13 个用例 |
| `tests/test_trace.py` | 7 个用例 |
| `tests/test_eval_store.py` | 6 个用例 |

**修改（3）：**

| 文件 | 变更 |
|---|---|
| `evoagent/config.py` | 追加 `SKILLS_DIR = "data/skills"`、`TRACE_CONTENT_MAX_CHARS = 4000`（既有常量未动） |
| `evoagent/storage.py` | `skills` 表 DDL 追加 `name` / `description` / `tags` 三列（带默认值）；通用 CRUD 与方法签名未动 |
| `tests/test_storage.py` | `test_skills_columns` 追加对 `name`/`description`/`tags` 的断言 |

未修改 `models.py`、`__init__.py`、`pyproject.toml`、`requirements.txt`、`.gitignore`、`docs/system_design.md`；未产生 `data/` 或 build/egg-info 残留。

## 2. 执行的验证命令及输出摘要

**命令 1：包导入**
```
python -c "import evoagent.skills.registry, evoagent.execution.trace, evoagent.eval.store"
```
输出：`packages import ok`

**命令 2：新门面测试**
```
python -m pytest tests/test_registry.py tests/test_trace.py tests/test_eval_store.py -v
```
输出摘要：`collected 26 items`，**`26 passed in 1.53s`**。

**命令 3：全量回归**
```
python -m pytest -v
```
输出摘要：`collected 52 items`，**`52 passed in 1.60s`**（0001 既有 `test_models.py`/`test_storage.py` 26 项 + 本事务 26 项，无回归、无失败、无 skipped）。

**命令 4：SQL 唯一性人工复核**
```
grep -rn "import sqlite3" evoagent/
```
结果：真实 `import sqlite3` 语句仅 `evoagent/storage.py:13`；其余命中为 `storage.py` docstring 内两处文字描述。三个门面文件均无（也无 `storage.conn` 访问）。

## 3. 验证结果

**验收标准逐条：**

1. ✅ `evoagent/skills/`、`evoagent/execution/`、`evoagent/eval/` 三包存在且可导入；根包仍可导入。
2. ✅ `storage.py` 仍是全项目唯一 `import sqlite3` / 写 SQL 的模块；三门面只调 `Storage`（grep 验证）。
3. ✅ `config.py` 新增 `SKILLS_DIR == "data/skills"`、`TRACE_CONTENT_MAX_CHARS == 4000`；既有常量不变。
4. ✅ `skills` 表含 `name`/`description`/`tags` 三列（`tags` 默认 `'[]'`）；`test_storage.py` 断言已覆盖。
5. ✅ `SkillRegistry`：register/get 往返（`metrics` dict、`tags` list、`few_shots`/`tools` 为 dataclass）、JSON 归档仅 3 内容字段、尊重 status（`draft` 保留 / `""` 默认 active）、promote/rollback/deprecate 单 active 不变量、`list(tags=...)` 交集过滤；不实现 `metrics` 增量回写。
6. ✅ `TraceStore`：save/get 往返（`steps` 为 `list[TraceStep]`、`usage` dict/None）、4000 截断（直查 `trace_steps` 表断言 `truncated`）、`list` 按 skill/status/since（`started_at`）过滤返回摘要。
7. ✅ `EvalStore`：`save_eval`/`get_eval` 往返（`objective`/`rubric_scores` dict、`passed` 三态精确保留）、`save_experience`/`list_experiences` 往返。
8. ✅ 三个新测试文件全部 PASSED；既有测试无回归（全量 52 passed）。
9. ✅ 无越界：不含检索/执行/评估/演化/编排逻辑、`llm.py`、`Task`、真实 LLM 调用/网络请求、新第三方运行时依赖、git 提交。

**结论：成功。** 全部验收标准满足，全部测试通过。

## 4. 已知局限

- **`pyproject.toml` 未含子包**：`packages=["evoagent"]` 不打包 `skills`/`execution`/`eval`，`pip install .` 装不出门面（task.md §11.9 已裁定本事务不修）。测试从源码树运行不受影响，留待引入 `cli.py`/真实安装时统一处理。
- **`metrics` 增量回写未实现**（§11.4）：使用次数/成功率由 traces/evals 聚合查询，属后续报告层。
- **`Task` dataclass 设计缺口**（§11.3）：`ExecutionTrace.task_id`/`task_source` 仅为字符串字段，`Task` 字段定义待执行层事务前回补。
- **`truncated` 不进数据契约**（§11.7）：`get()` 重建的 `TraceStep` 不含截断标志，Evaluator 若要感知截断需后续决策（本事务按裁定走 DB 层直查验证）。

## 5. 后续问题

1. 上层执行层（`SkillRetriever` / `AgentExecutor`）落地前，需先回补系统设计的 `Task` dataclass 字段定义。
2. 引入 `cli.py` / 真实安装时，需更新 `pyproject.toml` 的 `packages` 以纳入三个子包。
3. Skill 内容 JSON 归档的 git diff 能力依赖 `data/skills/*.json` 纳入版本控制（`.gitignore` 已不忽略 `data/`，属预期）。

## 6. 建议的下一步

建议下一个事务（`0003`）落地**执行层**：`evoagent/llm.py`（LLM 薄封装，届时引入 provider 决策与 openai/anthropic SDK、补 `config.py` 的 LLM 参数）或 `SkillRetriever`（依赖 `SkillRegistry.list`/`get_active` 与 `description`/`tags` 检索字段）。亦可先补 `Task` 设计缺口再进入执行层。
