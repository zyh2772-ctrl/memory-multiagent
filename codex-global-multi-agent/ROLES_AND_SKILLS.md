# Roles And Skills

## 1. 文档定位

本文档是当前工作区多代理角色契约与技能挂载的轻量索引。

用途：

- 明确正式角色在哪里定义
- 明确每个角色默认消费哪些上下文块
- 明确技能属于按需资产，而不是默认主提示词的一部分

硬约束仍以：

- [AGENTS.md](/Users/zyh/Desktop/ceshi123/ollamashiyong/AGENTS.md)
- [base_contract.md](/Users/zyh/Desktop/ceshi123/ollamashiyong/codex-global-multi-agent/prompts/shared/base_contract.md)

为准。

---

## 2. 正式角色索引

### Planner

- 契约文件：
  - [planner.md](/Users/zyh/Desktop/ceshi123/ollamashiyong/codex-global-multi-agent/prompts/roles/planner.md)
- 默认上下文块：
  - `Relevant Preferences`
  - `Workspace Facts`
  - `Prior Decisions`
  - `Task Continuation State`
  - `Known Risks`
- 典型职责：
  - 拆任务
  - 识别证据缺口
  - 设计最小验收路径

### Retriever

- 契约文件：
  - [retriever.md](/Users/zyh/Desktop/ceshi123/ollamashiyong/codex-global-multi-agent/prompts/roles/retriever.md)
- 默认上下文块：
  - `Workspace Facts`
  - `Retrieved Facts`
- 典型职责：
  - 收集证据
  - 标注来源
  - 区分证据与推断

### Verifier

- 契约文件：
  - [verifier.md](/Users/zyh/Desktop/ceshi123/ollamashiyong/codex-global-multi-agent/prompts/roles/verifier.md)
- 默认上下文块：
  - `Prior Decisions`
  - `Known Risks`
  - `Retrieved Facts`
- 典型职责：
  - 审计证据覆盖度
  - 识别不一致
  - 标记推断边界

### Implementer

- 契约文件：
  - [implementer.md](/Users/zyh/Desktop/ceshi123/ollamashiyong/codex-global-multi-agent/prompts/roles/implementer.md)
- 默认上下文块：
  - `Task Continuation State`
  - `Prior Decisions`
- 典型职责：
  - 落最小实现
  - 维持方案一致性
  - 暴露实现风险与回归面

### Synthesizer

- 契约文件：
  - [synthesizer.md](/Users/zyh/Desktop/ceshi123/ollamashiyong/codex-global-multi-agent/prompts/roles/synthesizer.md)
- 默认上下文块：
  - `Relevant Preferences`
  - `Workspace Facts`
  - `Prior Decisions`
  - `Task Continuation State`
  - `Known Risks`
  - `Retrieved Facts`
- 典型职责：
  - 汇总结论
  - 收束 next steps
  - 组织最终结构化提案

### Compactor

- 契约文件：
  - [compactor.md](/Users/zyh/Desktop/ceshi123/ollamashiyong/codex-global-multi-agent/prompts/roles/compactor.md)
- 默认上下文块：
  - `Workspace Facts`
  - `Prior Decisions`
  - `Known Risks`
  - `Retrieved Facts`
- 典型职责：
  - 生成 `compression_proposal_v1`
  - 保留压缩证据链与回滚依据
  - 在证据不足时输出结构化 `defer` 结果

---

## 3. 技能资产挂载规则

技能来源：

- Codex 内置 skills
- `gstack-main/.agents/skills`
- 其他显式安装的本地技能

规则：

1. 技能按任务按需加载
2. 技能不是默认主提示词的一部分
3. 技能只能补能力，不替代角色契约
4. 任务资产不得写回技能正文

典型挂载方式：

- 规划型任务：
  - 优先 `Planner` + 必要的计划/审计类技能
- 浏览/取证型任务：
  - 优先 `Retriever` / `Verifier` + 浏览或调查类技能
- 实现型任务：
  - 优先 `Implementer` + 代码实现或测试技能

---

## 4. 当前最小执行原则

1. 角色定义看本文件和 `prompts/roles/*.md`
2. JSON 契约看 `shared/base_contract.md` 与 schema
3. 技能只在当前任务明确需要时追加
4. 当前任务的 `context_package`、验收样本、失败摘要属于任务资产，不进入长期角色提示词
