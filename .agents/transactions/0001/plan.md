# 事务 0001 计划（Plan）

> 规划者（Planner）产出。按 `roles/planner.md` 要求的小节组织。

---

## 1. 当前状态（Current State）

仓库当前为**纯文档仓库**，业务代码为零。经实际核实（`find` 遍历），仅存在：

- `.agents/` 多智能体协作工作区（角色定义、工作流 / 状态 / 事务协议、状态文件、事务目录占位）
- `docs/system_design.md`（完整系统设计）

**不存在**：`evoagent/` 源码包、`pyproject.toml`、`requirements.txt`、`tests/`、任何 `.py` 文件。

系统设计（§2 / §13）明确了分层与目录结构，其中**底座层**（`models.py` 数据结构 · `config.py` 配置 · `storage.py` 存储底座）是上层所有模块（存储门面、执行层、评估层、演化层、编排层）共同依赖的地基。设计（§5–§11）已给出全部数据结构的字段定义，§14 明确技术选型为 Python 3.10+ / `dataclasses` / `sqlite3` / `pytest`。

## 2. 问题（Problem）

**没有地基，后续一切模块都无法构建或测试。**

证据：

1. 设计的依赖关系是单向的：存储门面依赖 `storage.py`，执行 / 评估 / 演化层依赖 `models.py` 的数据对象作为「跨层合同」（§2）。
2. 当前仓库没有任何 `models.py` / `config.py` / `storage.py`，也没有可供上层 import 的包结构。
3. 没有 `pytest` 环境与任何测试，无法在任何后续事务中进行「可客观验证」的迭代。

因此，第一步必须先把**数据契约与持久化底座**落地，并用测试锁定其行为，后续事务才有稳定的依赖起点。

## 3. 目标（Objective）

建立项目骨架并落地**底座层**：

- 可安装 / 可导入的 `evoagent` 包骨架（`pyproject.toml` + 包目录）
- 全部数据契约：`models.py`（设计 §5–§11 的 9 个 dataclass，含序列化辅助）
- 集中配置：`config.py`（阈值 / 权重 / 路径 / LLM 参数常量）
- SQLite 存储底座：`storage.py`（连接 / 建表 / 通用 CRUD，全项目唯一写 SQL 处）
- 对应单元测试：`tests/test_models.py`、`tests/test_storage.py`

达成后，本事务的成果应能通过 `pytest` 验证，且不引入任何外部服务依赖（LLM 调用、网络等）。

## 4. 范围（Scope）

**做（In scope）**

- 项目元信息与依赖声明：`pyproject.toml`、`requirements.txt`（仅 `pytest` 等测试依赖；运行时依赖标准库 `sqlite3`）
- 包骨架：`evoagent/__init__.py`
- `evoagent/models.py`：设计 §5–§11 的全部 dataclass 及其序列化 / 反序列化辅助
- `evoagent/config.py`：设计提到的阈值（如检索兜底阈值、`passed` 阈值 0.6）、评估权重（0.7 / 0.3）、默认路径（`data/` 等）等常量
- `evoagent/storage.py`：`Storage` 类 —— SQLite 连接（WAL）、建表、通用 CRUD；建表覆盖设计 §5–§8 所述表（`skills` / `traces` / `trace_steps` / `evals` / `experiences`，以设计字段为准）
- `tests/test_models.py`：dataclass 序列化 / 反序列化 round-trip 测试
- `tests/test_storage.py`：建表 + 基础 CRUD 读写测试

**不做（Out of scope，明确非目标）**

- `llm.py`（LLM 薄封装）—— 需引入 openai / anthropic SDK 与 provider 决策，与本事务「纯数据 + 持久化」无关，留待后续事务
- 存储领域门面：`SkillRegistry` / `TraceStore` / `EvalStore`
- 执行层、评估层、演化层、编排层、`cli.py`、benchmark、任何业务逻辑
- 任何真实 LLM 调用或网络请求
- 新依赖（除 `pytest` 外不引入第三方库；不引入向量数据库 / 编排框架）

## 5. 拟议变更（Proposed Changes）

| 文件（新建） | 变更性质 |
|---|---|
| `pyproject.toml` | 包元信息 + 最小依赖声明，使 `evoagent` 可安装、`pytest` 可运行 |
| `requirements.txt` | 开发依赖（`pytest`）声明 |
| `evoagent/__init__.py` | 包初始化，暴露版本号 |
| `evoagent/models.py` | 定义 `FewShot` / `ToolSpec` / `Skill`（§5）、`TraceStep` / `ExecutionTrace`（§6）、`EvaluationResult`（§7）、`Experience`（§8）、`BenchmarkTask`（§11）共 9 个 dataclass；提供 `to_dict` / `from_dict` 序列化辅助 |
| `evoagent/config.py` | 集中常量：检索兜底阈值、评估融合权重、`passed` 阈值、默认数据目录、版本号、WAL 开关等 |
| `evoagent/storage.py` | `Storage` 类：`connect()`（开 WAL）、`init_schema()`（建表）、通用 `insert` / `query` / `update` / `delete` 底座 |
| `tests/test_models.py` | 各 dataclass 的 round-trip 序列化与字段默认值测试 |
| `tests/test_storage.py` | 建表成功 + 各表基础读写 round-trip 测试 |

## 6. 依赖（Dependencies）

- **运行时依赖**：仅 Python 标准库 `sqlite3`、`dataclasses`、`typing`（无第三方）
- **测试依赖**：`pytest`
- **语言 / 平台**：Python 3.10+（设计 §14 明确）
- **顺序依赖**：`models.py` → `config.py` → `storage.py`（`storage.py` 引用 models / config 的字段与路径）；测试最后写
- **前置条件**：本机需有 Python 3.10+ 与可用的 `pytest`；无其他事务在进行中（当前为唯一活动事务）

## 7. 风险（Risks）

| 风险 | 缓解 |
|---|---|
| **Schema 与设计漂移**：dataclass 字段 / 表结构与 §5–§8 不一致，导致后续门面层踩坑 | 字段名与类型严格对照设计原文；用 round-trip 序列化测试与建表断言锁定；评审者需对照设计逐字段核对 |
| **范围蔓延**：把 `llm.py` 或门面层顺手带进本事务 | 第 4 节「明确非目标」已列出；编码者执行时不得越界 |
| **Windows 环境无 pytest / Python 版本不符** | 验证策略明确运行命令；若环境缺失，编码者在 `execution.md` 中如实记录并给出安装说明，不得谎报通过 |
| **SQLite WAL / 路径初始化在 Windows 上的行为差异** | `config.py` 统一路径，`storage.py` 用 `pathlib` 处理；测试用临时目录（`tmp_path`）隔离 |
| **表清单不全**（设计 §13 注记与 §3.3 EvalStore 口径略有差异，如是否含 `experiences` 表） | 本计划按 §5–§8 全文列出的表（含 `experiences`）为准；评审者需据此核实并可在 `review.md` 中纠正 |

## 8. 实施顺序（Implementation Order）

1. 建立包骨架与元信息：`pyproject.toml`、`requirements.txt`、`evoagent/__init__.py`
2. 实现 `models.py`：9 个 dataclass + 序列化辅助（先于其他，作为「合同」）
3. 实现 `config.py`：集中常量（引用 models 中涉及的默认值）
4. 实现 `storage.py`：`Storage` 连接 / 建表 / 通用 CRUD
5. 编写 `tests/test_models.py`
6. 编写 `tests/test_storage.py`
7. 运行验证命令（见 §10），确认全绿后完成

## 9. 验收标准（Acceptance Criteria）

1. `evoagent` 包可被导入，`pyproject.toml` 定义完整、`pytest` 可收集测试。
2. `models.py` 完整定义设计 §5–§11 的 9 个 dataclass，字段名与类型与设计一致。
3. 所有 dataclass 支持 `to_dict` / `from_dict` round-trip（序列化再反序列化后字段值不丢、类型正确）。
4. `storage.py` 能创建 SQLite 数据库并建立设计所述全部表（`skills` / `traces` / `trace_steps` / `evals` / `experiences`），且是全项目唯一写 SQL 的模块。
5. `config.py` 集中了设计中的关键阈值与权重（检索兜底阈值、评估权重 0.7 / 0.3、`passed` 阈值 0.6、默认数据路径）。
6. `tests/test_models.py` 与 `tests/test_storage.py` 全部通过。
7. **不**引入任何第三方运行时依赖、不进行任何真实 LLM 调用、不包含任何上层业务逻辑。

## 10. 验证策略（Verification Strategy）

在项目根目录运行：

```
python -m pytest tests/test_models.py tests/test_storage.py -v
```

（若环境无 pytest，先 `pip install -r requirements.txt`。）

验证要点：

- 测试全部 `PASSED`，无失败、无跳过掩盖。
- `test_storage.py` 使用临时目录 `tmp_path` 建库，验证：建表成功后，向 `skills`（或等价）表插入一条记录并查询回来，字段一致。
- `test_models.py` 验证每个 dataclass 的 round-trip 序列化及关键默认值（如 `ExecutionTrace.error_type` 默认空、`retrieval_fallback` 默认 `False`）。
- 复核 `evoagent/` 内无任何 `import sqlite3` 出现在 `storage.py` 之外的模块（分层约束，§2）。
