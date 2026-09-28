# 事务 0004 上下文（Context）

> 本文件是事务开始时的「时间胶囊」，记录当时的项目状态与触发背景，使本事务脱离当前项目状态也可被独立理解。
> 按 `workflow/transaction_protocol.md` 维护。

- 事务 ID：`0004`
- 创建日期：2026-09-28
- 事务性质：第四个开发事务（承接已关闭的 `0001` 底座层、`0002` 门面层、`0003` 检索器）

---

## 1. 触发原因

`0003` 已落地执行层第一步 `SkillRetriever` 与 `Task` 数据契约。系统**存储层完整、检索入口就绪**，但**底座层的最后一块 `llm.py`（LLM 薄封装）仍缺失**——而它是执行层 `AgentExecutor`（§3.2）、评估层 `Evaluator`（§7 LLM-as-judge）、`ExperienceExtractor`（§3.3）、演化层 `SkillEvolver`（§3.4）的**共同硬依赖**。

`config.py` 的模块 docstring 至今写着「不含任何 LLM provider / model / API key 等参数（这些随 `llm.py` / evaluator 事务引入）」——即 LLM 参数本就约定在本事务引入。`0003/result.md` 的「建议的下一步」也把 `AgentExecutor` 或 `llm.py` 列为后续候选。

本事务是**第一次引入第三方运行时依赖**（openai SDK），须在「最小依赖」原则下，用 mock-first 方式保证可测试性。

## 2. 事务开始时的项目状态快照

摘自当时的 `state/project_state.md`：

- **项目标识 / 用途**：EvoAgent —— 基于执行反馈的自演进 Agent Skill 平台。
- **架构摘要**：已落地底座层（`models.py` 9 个 dataclass、`config.py` 常量、`storage.py` 5 表）、存储门面层（`SkillRegistry`/`TraceStore`/`EvalStore`）、执行层检索器（`SkillRetriever`）。尚未落地 `llm.py`、`AgentExecutor`/`tools.py`、评估/演化/编排层、`cli.py`。
- **已实现能力**：9 个数据契约、SQLite 底座、三门面、检索器；63 项单元测试全部通过。
- **当前开发阶段**：底座层、门面层、检索器已落地（`0001`–`0003` 关闭）；执行层其余部分及评估/演化/编排层尚未开始。
- **已知约束**：运行时仅标准库，唯一第三方依赖是开发期 `pytest`（本事务将首次引入运行时第三方 `openai`）。
- **已知局限**：`docs/system_design.md` 仍缺 `Task` 字段定义（`0003` 已在 `models.py` 补齐，文档回补待后续）；`pyproject.toml` 未含子包；`metrics` 增量回写未实现。
- **当前事务**：无（`0003` 已关闭，下一个 ID 为 `0004`）。

## 3. 经核实的实际仓库现状（以实际代码 / 文件为准）

**git 状态**：`main` 分支，HEAD = `db105a5`「0003: 回填提交哈希到 result.md」（父 `0c2d591`、`810b9d1`、`78d505e`）；`git status --short` 为空（工作树干净）。

**关键事实（已核实）**：

1. `evoagent/llm.py` **不存在**（`find` 确认 `evoagent/` 下仅 `__init__.py`/`models.py`/`config.py`/`storage.py`/`skills/`/`execution/`/`eval/`）。
2. `evoagent/config.py` **无任何 LLM 常量**；其模块 docstring 明示「不含任何 LLM provider / model / API key 等参数（这些随 `llm.py` / evaluator 事务引入）」。
3. `evoagent/models.py` 已含 **9 个** dataclass（`Task` + §5–§11 的 8 个），`_Serializable` 递归序列化就绪。
4. `evoagent/skills/retriever.py` 已就绪（`SkillRetriever`/`DEFAULT_SKILL`/`RetrievalHit`/`RetrievalResult`），执行层检索入口可用。
5. `pyproject.toml`：`dependencies = []`（**无任何运行时第三方依赖**）、`packages=["evoagent"]`。
6. `requirements.txt`：仅 `pytest`。
7. `test_models.py` 模块 docstring 仍写「8 个 dataclass」（`0003` 未顺手改，已登记为范围外观察）——与 `models.py` 的「9 个」失准。

## 4. 已定决策（用户已拍板，本事务给定输入，原文记录，不再讨论）

> 以下 5 条为既定前提，计划必须遵照，不得再列为开放项或提出相反方案。

1. **协议**：`llm.py` 只实现 OpenAI 兼容路径——openai SDK 作客户端 + 可配置 `base_url`，适配 DeepSeek 等 OpenAI 兼容的国产 provider；**不实现 anthropic SDK，不做多 provider 适配层**。
2. **配置**：`config.py` 新增 `LLM_BASE_URL`、`LLM_MODEL`、`LLM_API_KEY_ENV`（环境变量名，如 `DEEPSEEK_API_KEY`）；API key 本身**绝不进仓库**，只从环境变量读取。
3. **接口**：对上暴露窄接口（单方法、纯文本入出），为将来可能的第二 provider 留扩展点，但**不为想象中的需求写抽象**。
4. **测试**：mock-first——`llm.py` 设计可注入的 mock client，**全部单测不发真实请求**；真实 API 调用仅作为手工冒烟验证，不进自动测试。
5. **依赖**：运行时新增 openai SDK **一个**第三方依赖（设计 §14 已列入），计划须说明 `requirements.txt` 与 `pyproject.toml` 的相应变化。

## 5. 本事务将引用的系统设计章节

- §2 分层视图：`llm.py` 属底座层（`models.py` 数据结构 · `llm.py` LLM 薄封装 · `config`）
- §13 目录结构：`evoagent/llm.py` —— `class LLMClient.complete() / chat_json()`
- §14 技术选型：`openai / anthropic SDK，llm.py 薄封装（可插拔、依赖少）`
- §3.2 `AgentExecutor`（`llm.py` 的消费者之一，本事务不实现）
- §7 `Evaluator` 的 LLM-as-judge（`chat_json` 结构化输出的潜在需求，本事务按裁定 #3 不实现，留待评估层事务）

## 6. 与既有决策的衔接

- `0001`/`0002` 曾裁定「`config.py` 不预置 LLM 参数、依赖仅 `pytest`（openai/anthropic/numpy 延后）」——本事务正是该延后项的**兑现时点**，引入 `openai`（仅一个）并按裁定 #2 补 LLM 常量，不推翻该决策、不引入 anthropic/numpy。
