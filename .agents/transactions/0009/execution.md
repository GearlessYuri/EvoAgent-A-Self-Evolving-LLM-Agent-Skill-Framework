# 事务 0009 执行报告（Execution）

> 编码者（Coder）产出。记录实际执行的步骤、重要实现决策及理由、与 `task.md` 的偏差、遇到的问题。

---

## 1. 实际执行的步骤

1. **阅读依据与核实**：阅读 `task.md`（完整）、`plan.md`/`review.md`/`context.md`（决策背景）、`project_state.md`、`active_transaction.md`、`docs/system_design.md`（§4 区域）。读实仓源码（`config.py`、`pyproject.toml`、各层模块接口），确认与 task.md §2 一致（`evolution/` 无 `loop.py`、无 `cli.py`、根无 `README.md`、`pyproject.toml` `packages=["evoagent"]`、`docs` 缺 `Task`、`config` 无 `MIN_EVOLUTION_SAMPLES`）。
2. **按依赖顺序实现 7 子项**：`config.py`（追加 `MIN_EVOLUTION_SAMPLES`）→ `loop.py`（`EvolutionLoop`）→ `cli.py`（`build_components` + `main` + `__main__` 入口）→ `pyproject.toml`（`packages.find`）→ `docs/system_design.md`（回补 `Task`）→ `README.md` → `test_loop.py`/`test_cli.py`。
3. **验证**：`import evoagent.cli/loop` 成功；`python -m pytest tests/test_loop.py tests/test_cli.py -v` → 11 passed；全量 `python -m pytest -v` → **126 passed**；`grep -rn "import sqlite3" evoagent/` 复核；`find_packages(include=["evoagent*"])` 与干净环境 `pip install .` + 四子包 import 成功；`git diff docs/system_design.md` 仅一处新增。
4. **收尾提交**：按 §10 授权执行（见下）。

## 2. 重要的实现决策及理由

### 2.1 `EvolutionLoop`（§4.2 精确实现）
`run(tasks) -> list[ValidationResult]`：`TraceStore.list()` 内存过滤（`task_source=="real"` 且 `error_type!="infra"` 且存在 `passed is False` 的 eval）→ 按 `skill_id` 分组 → `get_active` → 逐条 `extractor.extract` 拼经验 → `evolver.evolve` → `validator.validate`；样本 `< MIN_EVOLUTION_SAMPLES` 跳过、`get_active=None` 跳过、`extract` 空跳过、单 skill 异常捕获跳过不阻塞。只调六模块，不重实现。

### 2.2 `cli.py`（§4.3 精确实现 + 入口）
`build_components(db_path=None)` 是唯一 `import Storage`/`connect()`/`init_schema()` 的组合根，返回 `SimpleNamespace`；`main(argv=None) -> int` 四子命令（`list`/`run`/`evolve`/`bench`），`run` 正确映射 `retrieval_fallback=r.fallback`。**补了 `if __name__ == "__main__": raise SystemExit(main())`**（见 §3 偏差）。

### 2.3 打包修复（§4.4）
`pyproject.toml` 的 `[tool.setuptools] packages=["evoagent"]` → `[tool.setuptools.packages.find] include=["evoagent*"]`，自动纳入 4 子包；`find_packages` 与 `pip install .` 后四子包 import 均验证通过。

### 2.4 设计回补（§4.5）+ README（§4.6）
`docs/system_design.md` 在 §4 标题后、正向流列表前插入 `Task` dataclass（与 `models.py` 逐字段一致，仅此一处）；`README.md` 含一句话说明、架构概览、快速上手（安装 + 四子命令 + `DEEPSEEK_API_KEY`）、seed 数据前置说明（如实标注非开箱即用）、指向设计文档。

## 3. 与 task.md 的偏差

| 项 | 说明 | 是否范围外 |
|---|---|---|
| `loop.py` docstring 措辞 | §4.2 的 docstring 含「不 import sqlite3 / Storage」字面串，与 §9/§10 grep 冲突；改为「只编排下层模块，不重实现」（同 0005–0008 处理） | 否（注释措辞） |
| `cli.py` 补 `__main__` 入口 | §4.3 的代码块省略了 `if __name__ == "__main__": raise SystemExit(main())`，但 §9.3/§4.6 明确要求 `python -m evoagent.cli list` 可跑；补该标准入口以兑现验收 | 否（§9.3 的必要项） |
| 打包验证用 `--system-site-packages --no-deps --no-build-isolation` | 干净环境 `pip install .` 需联网下载 openai/setuptools；改用系统 site-packages + 跳过依赖 + 不隔离构建，规避联网，仍验证「子包被正确打包并 import」（四子包 import 测试本就不触碰 openai 模块） | 否（验证方式等价，结果记入 result.md） |

无功能性偏差：`config.py` 仅追加 1 常量；`loop.py`/`cli.py`/`README.md` 新建；`pyproject.toml` 仅改 `packages.find`；`docs/system_design.md` 仅 §4.5 一处新增；未改其余 `evoagent/*`/`tests/*`。

## 4. 遇到的问题

无阻塞性问题。仅两点实现说明：① `cli.py` 需补 `__main__` 入口（§4.3 代码块遗漏）；② 打包验证避开联网（见 §3）。
