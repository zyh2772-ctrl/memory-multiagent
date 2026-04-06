# Memory Write Policy

## 状态所有权

1. 主代理独占 `RunState`
2. 主代理独占长期记忆查询与写入权限
3. 子代理只提交候选结果和 `state_delta`
4. 子代理不得直接修改全局技能配置

## 子代理边界

1. 子代理不可直接写长期记忆
2. 子代理不可直接查询 OpenMemory
3. 子代理不可直接执行 `update` / `invalidate`
4. 子代理只能提交带来源的候选提案

## 主代理职责

1. 审核 `state_delta`
2. 去重与合并
3. 决定是否写入长期记忆
4. 决定是否更新或失效旧记忆
5. 维护 `fallback_history`
6. 生成审计记录

## 审批流

每条结构化提案必须经过：

1. `proposal`
2. `verify evidence`
3. `conflict check`
4. `approve / reject / defer`
5. `writeback`
6. `audit record`

## 作用域审批门槛

### `task`

- 默认允许自动审批
- 允许 `model_inference`
- 仍然必须保留 `source`

### `workspace`

- 必须有 `evidence_ids`
- `model_inference` 默认拒绝
- `update / invalidate` 必须有更强证据

### `user_global`

- 审批门槛最高
- 默认要求明确用户陈述或已批准长期约束
- 缺少证据时直接 `defer`

## 熵减策略

当新证据与旧记忆冲突时，主代理必须执行以下三选一：

1. `update`
   旧记忆仍然有效，但内容需要修正
2. `invalidate`
   旧记忆被更高质量证据推翻，应标记为过时
3. `append`
   新信息只是补充，不与旧记忆冲突

默认禁止无脑追加。

## 来源治理

推荐 `source`：

- `observed_fact`
- `tool_output`
- `user_claim`
- `approved_decision`
- `model_inference`

规则：

1. `model_inference` 默认只允许写入 `task`
2. `workspace` / `user_global` 级提案必须附带可追溯 `evidence_ids`
3. 无法区分来源的旧字符串提案默认进入人工复核队列

## 审计记录

每次写回至少保留：

- `kind`
- `scope`
- `identity`
- `proposal_type`
- `approved_by`
- `evidence_ids`
- `source_files`
- `reason`
