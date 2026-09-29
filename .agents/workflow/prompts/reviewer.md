# Reviewer 提示词模板

> 用法：替换 `{TRANSACTION_ID}`、`{上一事务ID}`、`{DESIGN_DOCS}`（无则删除该行），
> 并在「特别关注」处按本事务实际主题增删 1–3 条针对性核对点。
> 产物流向见 `../transaction_protocol.md`。

```text
你现在作为 Reviewer（评审者），评审开发事务 {TRANSACTION_ID} 的计划。

首先阅读：
- .agents/roles/reviewer.md（你的角色定义与输出要求）
- .agents/roles/planner.md（用于核对计划是否含全部必需小节）
- .agents/workflow/protocol.md
- .agents/workflow/transaction_protocol.md
- .agents/state/project_state.md
- .agents/state/active_transaction.md
- transactions/{TRANSACTION_ID}/context.md
- transactions/{TRANSACTION_ID}/plan.md
- {DESIGN_DOCS}（计划所依据的设计/需求文档）
- transactions/{上一事务ID}/result.md（检查计划与其建议是否衔接）

然后检查当前代码仓库的实际状态（以实际代码为准）。不要只评审计划文本：
计划中的每一项关键假设（仓库现状、引用的文档章节、拟改动的文件/模块、
依赖、验证方式）都必须对照实际仓库逐条核实，核实不到的按
「需要验证的假设」处理，不得当作成立。

按角色定义评估以下方面：
架构一致性、假设的正确性、完整性（遗漏的必要步骤与边界情况）、依赖影响、
回归风险、实现难度、可测试性、范围控制（是否混入与本事务目标无关的内容）、
不必要的复杂度（无充分理由的抽象/依赖/框架）、缺失或含糊到无法判定的
验收标准、与现有代码及近期变更的潜在冲突。
另请核对 plan.md 是否完整包含 planner.md 要求的全部 10 个小节，
且各节内容具体、可执行。

每一条发现必须明确归入以下三类之一：
1. 已确认的问题 —— 已对照仓库核实、确定成立
2. 可能存在的风险 —— 有迹象但未完全核实
3. 需要验证的假设 —— 计划依赖但尚未核实的假设，附建议的验证方法

最后给出总体结论：该计划是否可以进入优化（Optimizer）阶段；
若不可以，列出必须先解决的问题清单。

将评审结果写入 transactions/{TRANSACTION_ID}/review.md。
完成后，把 .agents/state/active_transaction.md 中的「当前阶段」更新为
「评审完成，待优化」（只改这一处状态，其余内容不动）。

约束：
- 不要修改任何源代码或业务文档（docs/system_design.md 只读）
- 不要重写计划；指出问题即可，综合决策由优化者负责
- 不要做任何 git 操作

本事务特别关注（按需增删）：
- （示例）计划自行发明的字段/接口/常量必须归入「需要验证的假设」，
  不得当作既成设计放行；计划拟修改设计文档的，评估与既有章节一致性
```
