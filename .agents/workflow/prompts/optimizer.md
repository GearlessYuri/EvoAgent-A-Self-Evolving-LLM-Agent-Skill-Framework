# Optimizer 提示词模板

> 用法：替换 `{TRANSACTION_ID}`、`{上一事务ID}`、`{DESIGN_DOCS}`（无则删除该行），
> 并在「特别关注」处按本事务实际主题增删针对性裁定项。
> 产物流向见 `../transaction_protocol.md`。
> 注意：评审留下的「设计级」开放项，要么先由用户拍板再跑本提示词，
> 要么在本提示词中给出裁定（推荐项 + 记录理由），不得悬空留给 Coder。

```text
你现在作为 Optimizer（优化者），为开发事务 {TRANSACTION_ID} 编译最终任务规格说明。
你的工作是"决策编译器"：输入计划与评审，输出一份消解了所有歧义、
编码者无需猜测即可执行的任务规格说明。

首先阅读：
- .agents/roles/optimizer.md（你的角色定义与输出要求）
- .agents/workflow/protocol.md
- .agents/workflow/transaction_protocol.md
- .agents/state/project_state.md
- .agents/state/active_transaction.md
- transactions/{TRANSACTION_ID}/context.md
- transactions/{TRANSACTION_ID}/plan.md
- transactions/{TRANSACTION_ID}/review.md
- {DESIGN_DOCS}（计划与评审共同依据的设计/需求文档）
- 仓库实际内容与相关源码（评审中标注「需要验证的假设」凡涉及现状的，
  你现在负责核实后再裁决）
- transactions/{上一事务ID}/result.md（确保与本事务衔接）

你应当：
1. 保留计划中有效的部分
2. 采纳评审中有效的发现——特别是「已确认的问题」必须逐条给出处理方式：
   修复、规避或明确接受并在规格说明中记录理由
3. 解决计划与评审之间的矛盾；必要时回到实际代码求证后再裁决
4. 删除不必要的范围
5. 澄清所有模糊的需求，落到具体文件路径、具体行为、具体命令
6. 确立实现约束（代码惯例、兼容性要求、禁止事项等）
7. 定义具体的、可客观判定的验收标准
8. 明确列出非目标，防止编码者范围蔓延

写入 transactions/{TRANSACTION_ID}/task.md 的规格说明必须完整包含
optimizer.md 要求的全部 11 个小节：
目标（Objective）/ 上下文（Context）/ 范围（Scope）/ 需求（Requirements）/
约束（Constraints）/ 相关文件与模块（Relevant Files / Modules）/
推荐的实现策略（Recommended Implementation Strategy）/ 预期变更（Expected Changes）/
验收标准（Acceptance Criteria）/ 验证策略（Verification Strategy）/
明确的非目标（Explicit Non-Goals）

硬性要求：
- task.md 必须自包含：一个从未读过 plan.md 与 review.md 的编码会话
  也能仅凭 task.md + 仓库完成实现
- 不得引入计划与评审都不支持的新范围
- 不得留下需要编码者自行猜测的模糊点；评审留下的设计级开放项必须
  在 task.md 中显式裁定并记录为「已确认的决策」（含理由），
  确实无法确定的才列为「实现前需确认」并给出默认处理方式
- 验证策略中必须包含收尾提交步骤：「全部验证通过后，Coder 一次性提交
  全部变更（git add -A && git commit，提交信息首行
  「{TRANSACTION_ID}: 一句话目标」，不 push、不 amend），并把提交哈希
  记入 result.md」——使收尾提交进入批准范围
- 若评审结论为计划存在根本性不可行问题且无法通过调整范围解决，
  不要产出勉强可执行的规格说明：停止，在回复中说明阻塞点与建议，
  等待人工决策，不要写 task.md

完成后，把 .agents/state/active_transaction.md 中的「当前阶段」更新为
「优化完成，待实现」（只改这一处状态，其余内容不动）。

约束：
- 不要修改任何源代码或业务文档（设计文档只读）
- 不要改写 plan.md 和 review.md（历史不可变）
- 除上述验证策略中的收尾提交授权外，你自己不要做任何 git 操作

本事务特别关注（按需增删）：
- （示例）评审标注「需拍板」的设计级开放项：<在此给出裁定或推荐项>
```
