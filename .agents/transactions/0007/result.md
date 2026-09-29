# 事务 0007 结果（Result）

> 编码者（Coder）产出。记录变更文件、测试/验证、结果、局限与后续建议。

---

## 1. 变更的文件

**新建（2）：**

| 文件 | 内容 |
|---|---|
| `evoagent/eval/benchmark.py` | `Benchmark` + `load_tasks`/`load_tasks_by_name` + `BenchmarkReport`（dataclass + `to_dict`） |
| `tests/test_benchmark.py` | 7 用例（汇总口径 / 防污染①②③ / load_tasks 边界） |

**修改（3）：**

| 文件 | 变更 |
|---|---|
| `evoagent/config.py` | 追加 `BENCHMARKS_DIR`/`TEST_SCRIPT_TIMEOUT_SEC`（既有常量未动） |
| `evoagent/eval/evaluator.py` | 补 `_run_test_script` + `test_script` 分支 + `import subprocess`/`sys`（六分支未动） |
| `tests/test_evaluator.py` | 追加 5 个 `test_script` 用例；既有「未知 type」用例示例由 `test_script` 改为 `unknown_type`（§4.2 使其成为已知 type） |

未修改 `models.py`、`storage.py`、`store.py`、`experience.py`、`trace.py`、`executor.py`、`retriever.py`、`registry.py`、`llm.py`、`__init__.py`、`pyproject.toml`、`requirements.txt`、`docs/system_design.md`；未产生运行时数据文件。

## 2. 执行的验证命令及输出摘要

**命令 1：包导入**
```
python -c "import evoagent.eval.benchmark, evoagent.eval.evaluator"
```
输出：`import ok`

**命令 2：定向测试**
```
python -m pytest tests/test_evaluator.py tests/test_benchmark.py -v
```
输出摘要：`collected 20 items`，**`20 passed in 1.31s`**。

**命令 3：全量回归**
```
python -m pytest -v
```
输出摘要：`collected 104 items`，**`104 passed in 4.90s`**（既有 92 项无回归、无失败、无 skipped）。

**命令 4：SQL 唯一性人工复核**
```
grep -rn "import sqlite3" evoagent/
```
结果：真实 `import sqlite3` 语句仅 `evoagent/storage.py:13`；`benchmark.py` 无、也不访问 `storage.conn`。

## 3. 验证结果

**验收标准逐条：**

1. ✅ `config.py` 新增 `BENCHMARKS_DIR == "data/benchmarks"`、`TEST_SCRIPT_TIMEOUT_SEC == 5`；既有常量不变。
2. ✅ `test_script` 分支：子进程执行，`returncode==0`→`test_pass=True`（objective/跳过 judge/1.0）；非零/超时/异常→`test_pass=False`（0.0）；异常不逃逸；`value` 非字符串→无客观走 judge。
3. ✅ `Benchmark.run` 批量执行+评估返回 `BenchmarkReport`；`success_rate`（`passed is True 数 / passed 非 None 数`，None 不计分母）、`avg_total_score` 全任务均值、`to_dict()` JSON-ready。
4. ✅ 防污染①：真实 executor + 真实 TraceStore 跑后 `TraceStore.list()` 全部 `task_source=="benchmark"`。
5. ✅ 防污染②：`reference_answer="SENTINEL_XYZ"` 不进 executor `steps[0]`（llm_call）prompt。
6. ✅ 防污染③：`load_tasks_by_name` 分别加载 regression/extension；`Benchmark` 无导出经验接口。
7. ✅ 测试全绿（全量 104 passed），全程 mock、test_script 用无害脚本、不发真实 LLM 请求。
8. ✅ 无越界：不含 `SkillEvolver`/`Validator`/`EvolutionLoop`/`cli.py`/`tools.py`/win_rate A/B/report 文件 I/O/真实 LLM 请求。

**结论：成功。** 全部验收标准满足，全部测试通过。

## 4. 已知局限

- **`test_script` 仅「崩溃/超时隔离」**（进程隔离 + 超时），**非 OS 沙箱**——不防文件系统/网络写入；`test_script` 是 benchmark 作者（可信）判题脚本，此信任模型下足够；不可信脚本需 OS 级沙箱（§11.5）。
- **`reference_answer` 实际必填**：task §4.3 措辞「可选 reference_answer」与 `BenchmarkTask.from_dict` 的严格性（`d[f.name]`）不一致，实践中 benchmark JSON 须含 `reference_answer`（默认 `""`）；因「不改 models.py」未修复。
- `Benchmark` 不实现按 tag/difficulty 抽取（调用方可预过滤 `tasks` 再传 `run`，§11.4）。
- `BenchmarkReport` 不落盘（report.json/report.md 属 Validator A/B 报告，§11.3）。

## 5. 后续问题

1. `SkillEvolver`/`Validator`（win_rate A/B）+ `EvolutionLoop`——演化层，`0008`。
2. 防污染③的硬保证（EvolutionLoop 只挖 `task_source=="real"` 的 trace）登记为 `0008` 约束。
3. `tools.py` 与工具调用（执行层多轮 loop）。

## 6. 建议的下一步

建议下一个事务（`0008`）落地演化层：`SkillEvolver`（经验→候选版本）+ `Validator`（Benchmark A/B + win_rate + promote/回滚），随后 `EvolutionLoop`（主循环串联）。

## 7. 提交

- 提交信息：`0007: 落地 Benchmark 与 test_script 客观执行`
- 提交哈希：`5a511f5d31c66fc5de0c81ce6445304fbed0efa3`（`git rev-parse HEAD`，短哈希 `5a511f5`）
