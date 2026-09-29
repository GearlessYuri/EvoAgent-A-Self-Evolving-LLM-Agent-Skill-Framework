# 事务 0007 评审（Review）

> 评审者（Reviewer）产出。按 `roles/reviewer.md` 要求，每条发现归入「已确认的问题 / 可能存在的风险 / 需要验证的假设」三类之一。
> 评审依据：实际仓库（`0001`–`0006` 落地后的源码）+ `docs/system_design.md` + `.agents/` 状态文件 + `0006/result.md`，而非仅凭计划文本。

- 事务 ID：`0007`
- 评审日期：2026-09-29
- 评审对象：`plan.md`（规划者产出）

---

## 0. 评审方法与实际核实记录

| 核实项 | 方法 | 结果 |
|---|---|---|
| `Evaluator` 现状 | 读 `eval/evaluator.py` | 六分支；`otype not in ("exact","contains")` 时 `otype=None`（`evaluator.py:74-76` 注释「test_script 延后到 0007」）；exact/contains 的 `objective` dict 用 `matched` 键 |
| `AgentExecutor` 现状 | 读 `execution/executor.py` | `_render_prompt` 只用 `task.task`（`replace("{task}")` + few-shot）；`trace.task_source = task.task_source`（`executor.py:47`）——**答案隔离与来源隔离结构已就绪** |
| `config.py` | 读（0006 轮） | 无 `BENCHMARKS_DIR`、无 `TEST_SCRIPT_TIMEOUT_SEC` |
| `BenchmarkTask` 模型 | 读 `models.py` | 字段齐全（`task_id/task/rubric/objective_check/tags/difficulty/reference_answer=""`） |
| `eval/` 目录 | `find` | 无 `benchmark.py`（仅 `evaluator.py`/`experience.py`/`store.py`/`__init__.py`） |
| git / 测试现状 | `git log`/`git status`/`pytest` | HEAD `58d6e12`（main）；`git status --short` 非空（state 文件已改 + `0007/` 未跟踪，**工作树非干净**）；全量 `92 passed` |
| 设计 §7/§11/§3.3/§13 原文 | 读 | §7「exact/test_script → 不跑 judge」；§11 指标（success_rate/avg_total_score，win_rate 属 A/B）、防污染三规则；§3.3「跑一批返回汇总得分」「按 tag/difficulty 抽取」；§13 `data/benchmarks/{regression,extension}.json` |

---

## 1. 计划完整性核对（planner.md 要求的 10 小节）

10 个小节**全部具备、内容具体可执行**（遵循「文档精炼纪律」，简洁但非空话）：

| # | 要求小节 | 是否具备 | 是否具体 |
|---|---|---|---|
| 1 | 当前状态 | ✅ | ✅ 缺 benchmark.py、Evaluator test_script 未实现、config 无 benchmark 常量 |
| 2 | 问题 | ✅ | ✅ 缺「尺子」、防污染未代码化、test_script 缺失 |
| 3 | 目标 | ✅ | ✅ Benchmark + test_script + 防污染三规则 |
| 4 | 范围 | ✅ | ✅ 做/不做清晰；SkillEvolver 顺延 0008 有理由；report 文件 I/O 延后 |
| 5 | 拟议变更 | ✅ | ✅ 文件表 + §5.1/§5.2 细化 test_script 边界与 Benchmark/防污染 |
| 6 | 依赖 | ✅ | ✅ 标准库（json/subprocess/sys/uuid/typing）+ 既有 openai；无新第三方 |
| 7 | 风险 | ✅ | ✅ 6 条均附缓解（逃逸、防污染、误判、口径、蔓延） |
| 8 | 实施顺序 | ✅ | ✅ 5 步 |
| 9 | 验收标准 | ✅ | ✅ 8 条客观可判定（test_script 分支、防污染三条、报告口径、grep 分层） |
| 10 | 验证策略 | ✅ | ✅ 命令 + 用例清单 + grep 人工复核 |

结论：结构完整、无事实性硬错。主要问题集中在**test_script 契约/超时值是计划自创需钉死**、**验收 §9.4 与测试 mock 策略不一致**、以及**若干口径/边界未定**。

---

## 2. 已确认的问题（对照仓库核实成立）

### 2.1 验收 §9.4 与 §10 测试策略不一致：mock executor 无法验证「TraceStore 中的 trace」

- **已核实**：`AgentExecutor.run` 用 `self.trace_store.save(trace)` 落库（`executor.py:60/83`），`trace.task_source` 取自 `task.task_source`。验收 §9.4 写「跑后 **TraceStore 中**相关 trace 的 `task_source=="benchmark"`」——这需要**真实 executor + 真实 TraceStore**（落库后查询）才能验证；但 §10 的 `test_benchmark.py` 明确用「**mock AgentExecutor** + Evaluator」，mock 不写 TraceStore。
- **后果**：按 §10 的 mock 策略，§9.4 的「TraceStore 中 trace」无法验证；按 §9.4 的字面要求，又需要真实 executor。
- **建议**：优化者二选一并统一——(a) 用真实 `AgentExecutor` + `tmp_path` 的 `Storage`/`TraceStore` 做落库级验证；或 (b) 把 §9.4 改为「Benchmark 传给 `executor.run` 的 `Task.task_source == "benchmark"`（通过 mock 捕获 `task` 参数断言）」。后者更轻且已覆盖结构保证（`task_source` 的落库链由 executor+TraceStore 的既有测试覆盖）。

### 2.2 新增 config 常量未给值，且 `BENCHMARKS_DIR` 的消费者未定

- **已核实**：计划 §5 加 `BENCHMARKS_DIR`、`TEST_SCRIPT_TIMEOUT_SEC` 两常量，但**均未给值**；`load_tasks(path: str)` 用显式路径，**未说明 `BENCHMARKS_DIR` 是否作为其默认目录**（否则该常量是无消费者的死配置）。
- **建议**：优化者钉死——`BENCHMARKS_DIR="data/benchmarks"`（§13 一致）并明确 `load_tasks` 是否以其为默认根；`TEST_SCRIPT_TIMEOUT_SEC` 给具体秒数（见 §4.2）。

---

## 3. 可能存在的风险（有迹象，未完全核实）

### 3.1 「子进程隔离」是崩溃/超时保护，非文件系统/网络沙箱

- 计划 §5.1 用 `subprocess.run([sys.executable,"-c",script], input=output, timeout=...)` 提供**进程隔离（防崩溃/死循环 + 超时）**，但**不阻止**脚本读写宿主文件系统、访问网络。§7 风险 1 把「写宿主」列为被缓解项，实为**过强措辞**——subprocess+timeout 并不缓解「写宿主」。
- **判断**：`test_script` 是 benchmark 作者（可信）编写的判题脚本，非 agent 产出的不可信代码，故 subprocess+timeout 对当前信任模型**足够**；真正的沙箱（OS 级隔离）属过度工程。但应在 `task.md` 把措辞改为「崩溃/超时隔离」，不声称「防写宿主」，或登记「不可信脚本需 OS 沙箱」为已知局限。

### 3.2 `success_rate` 的分母口径未定

计划 §7 风险 4 写「`passed is True` 计分子，`passed is None` 不计入成功率分子但计入分母（**或由优化者定**）」——分母是否计入 `passed=None` 仍悬置。设计 §11 只写「success_rate：客观通过率」，未给口径。需钉死，否则验收 §9.3「口径正确」无法判定。

### 3.3 防污染规则 3（extension 只考不学）本质是「无导出 API」的结构性弱保证

计划 §5.2 规则 3 用「run 无任何导出经验的接口」来落实，验收 §9.6「run 无任何「导出经验」接口」靠「缺省」验证（grep/反射）。这是**结构上较弱**的保证——真正的隔离来自规则 1（`task_source=="benchmark"` 标签）+ 未来 `EvolutionLoop` 只挖 `task_source=="real"` 的 trace。建议把规则 3 的「代码可见性」定位为「配合规则 1 的标签，extension 结果与 regression 一样只产出报告、不进经验路径」，并登记「经验挖掘只在 real trace 上」为 `0008` 演化事务的硬约束。

### 3.4 `objective` dict 形状跨类型不一致（轻微）

现有 `exact`/`contains` 的 `objective` 用 `{"status", "type", "matched"}`；计划 §5.1 的 `test_script` 用 `{"status", "type": "test_script", "test_pass": bool}`。设计 §7 注释 `{status, matched, test_pass, ...}` 两者皆可，但需保持一致/文档化，避免 `objective` dict 的键在不同 type 下含义漂移。

### 3.5 §3.3「按 tag/difficulty 抽取」未体现（轻微）

设计 §3.3 写 Benchmark「支持按 tag/difficulty 抽取」。计划只有 `load_tasks(path)` + `run(tasks, skill)`，无按 tag/difficulty 过滤的接口。可由调用方（Validator）预过滤，或 `load_tasks` 加可选过滤参数——需优化者确认是否本事务覆盖，还是登记为非目标。

---

## 4. 需要验证的假设（附建议的确认方式）

### 4.1 `test_script` 的执行契约（计划自创，需钉死）

- 计划 §5.1 自创契约：`objective_check["value"]` 即脚本代码、脚本从 **stdin** 读 `final_output`、`returncode==0`→pass。设计 §11 仅写 `objective_check={"type":"test_script","value":...}`，**未定义** `value` 语义与脚本如何接收输出。§7 风险 2 已自识「无 stdin 约定」「value 缺省处理」。
- **建议确认方式**：优化者在 `task.md` 明确——`value` 是否为脚本源码字符串；stdin 传 `final_output`；exit code 0/non-0 的 pass/fail 语义；`value` 缺失/非字符串时视为「无客观」（与 0006 的未知 type 处理一致）。并补对应测试。

### 4.2 `TEST_SCRIPT_TIMEOUT_SEC` 的具体值（计划自创）

设计 §7 未定义 test_script 超时。计划加常量但未给值。**建议确认方式**：优化者钉死一个保守秒数（如 5s），并保证超时用例（`while True: pass`）不会让全量测试过慢。

### 4.3 `BenchmarkReport` 结构（计划自创，需钉死）

计划 §5.2 提出 `BenchmarkReport`（benchmark.py 内 NamedTuple/dataclass，不进 models.py），含 `per_task`、`success_rate`、`avg_total_score`，`to_dict()` JSON-ready。**需钉死**：`per_task` 每项形状（`(task_id, passed, total_score)` 还是更丰富）、`success_rate`/`avg_total_score` 的口径与类型。设计 §11 给了指标名但未给结构，故此为自创，需确认（不进 models.py 已与 0003 先例一致，正确）。

### 4.4 `load_tasks` 的 JSON schema 与 `BENCHMARKS_DIR` 角色

`load_tasks` 把 JSON 反序列化为 `BenchmarkTask.from_dict`，但 JSON 文件的具体 schema（顶层是数组还是 `{"tasks": [...]}`、`objective_check`/`rubric`/`tags` 的表示）未定义。`BENCHMARKS_DIR` 是否作为默认根目录也未定（§2.2）。**建议确认方式**：优化者给出一个最小示例 JSON + 明确 `load_tasks` 默认路径语义。

### 4.5 已核实的前提（报告结果）

- **git**：HEAD `58d6e12` ✅ 与 context §3 一致；工作树非干净（state 文件 + `0007/`），context「工作树干净」已过时（轻微，与前序同类）。
- **测试**：全量 `92 passed` ✅ 与 project_state/context 一致。
- **结构衔接**：`Task(task_source="benchmark")` → `trace.task_source` 的落库链、`_render_prompt` 只用 `task.task`（答案隔离）**已核实存在**，计划 §5.2 的防污染①②是「已有结构的显式化 + 测试锁定」，非新建。
- **`test_script` 定论语义**：计划把 test_script 归为「定论、跳过 judge、`eval_basis="objective"`」，与设计 §7「exact/test_script → 不跑 judge」一致 ✅。

---

## 5. 总体结论

**该计划可以进入优化（Optimizer）阶段。** 计划结构完整（10 小节齐全且具体）、正确承接 `0006/result.md` §5.1 的 Benchmark+test_script 建议、`test_script` 定论语义与设计 §7 一致、防污染①②建立在**已核实的既有结构**（`task_source` 落库链 + `_render_prompt` 只用 task.task）之上、范围控制良好（SkillEvolver 顺延 0008 有充分理由、report 文件 I/O 延后、无新增第三方依赖、`BenchmarkReport` 不进 models.py 与先例一致）、分层正确（Benchmark 只编排 executor+evaluator，不直接写库）。**无事实性硬错。**

**进入 `task.md` 前，优化者必须裁定 / 钉死以下问题：**

1. **[必钉] 统一验收 §9.4 与测试策略**：真实 executor+tmp_path TraceStore 验证落库，或改验收为「mock 捕获 `Task.task_source=="benchmark"`」（§2.1）。
2. **[必钉] `test_script` 契约 + 超时值**：`value`=脚本源码、stdin=final_output、exit code 语义、`TEST_SCRIPT_TIMEOUT_SEC` 具体值（§4.1/§4.2）。
3. **[必钉] 口径**：`success_rate` 分母（`passed=None` 是否计入）、`BenchmarkReport` 结构与 `per_task` 形状、`objective` dict 键跨 type 一致（§3.2/§3.4/§4.3）。
4. **[必钉] config 常量**：`BENCHMARKS_DIR`/`TEST_SCRIPT_TIMEOUT_SEC` 的值与 `load_tasks` 默认路径语义（§2.2/§4.4）。
5. **[建议] 措辞与边界**：把「子进程隔离」措辞改为「崩溃/超时隔离」（不声称防写宿主，§3.1）；登记规则 3 的真正保证在 `0008` 演化事务只挖 real trace（§3.3）；确认 tag/difficulty 过滤是否本事务覆盖（§3.5）。

**未发现的问题**：无范围蔓延、无不必要抽象（`BenchmarkReport` 用 NamedTuple/dataclass 而非新 models.py dataclass，正确）、无新第三方依赖、回归风险低（`evaluator.py` 仅新增一个 `test_script` 分支与 helper，既有六分支不动；`config.py` 追加常量不动既有）。
