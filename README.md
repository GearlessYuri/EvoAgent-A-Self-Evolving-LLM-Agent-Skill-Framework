# EvoAgent

基于执行反馈的自演进 Agent Skill 平台：把 Agent 能力拆成「可版本化、可检索、可评估、可演化」的 Skill，用一条闭环让技能自己变好。

## 架构概览

核心闭环（详见 `docs/system_design.md` §1）：

```
Task → Skill Retrieval → Agent Execution → Execution Trace → Evaluation → Experience → Skill Evolution → Validation → Skill Registry
```

- **正向流（运行时）**：任务进来 → 检索最相关 Skill → 执行并写 Trace → 评估打分。
- **逆向流（离线演化）**：低分 Trace → 提炼经验 → 演化候选版本 → Benchmark A/B 验证 → promote。

## 快速上手

安装：

```bash
pip install .
```

CLI 四子命令：

```bash
# 列出已注册的 active 技能（无需 LLM，可离线跑）
python -m evoagent.cli list

# 跑一个任务（需设置 API key）
python -m evoagent.cli run "审查这段代码"

# 触发一次演化（离线逆向流）
python -m evoagent.cli evolve

# 跑某个技能的 benchmark
python -m evoagent.cli bench <skill_id> [--set regression|extension]
```

跑 `run` 前需设置 API key（OpenAI 兼容 provider）：

```bash
# Linux / macOS
export DEEPSEEK_API_KEY=your_key_here
# Windows PowerShell
$env:DEEPSEEK_API_KEY = "your_key_here"
```

## 前置说明（重要）

- `evolve` 与 `bench` 依赖 **benchmark 任务集**（`data/benchmarks/regression.json`、`data/benchmarks/extension.json`）与**已注册的 skill**。
- 仓库当前**未播种种子技能与 benchmark 集**（冷启动内容待后续提供）；首次使用前需先自行 `register` 技能、撰写 benchmark JSON，否则 `evolve`/`bench` 会 `FileNotFoundError` 或空跑。本项目**不是开箱即用**，需先准备上述数据。

## 更多文档

- 系统设计：`docs/system_design.md`
