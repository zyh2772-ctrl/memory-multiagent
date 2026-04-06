# Asset Loading Policy

## 1. 文档定位

本文档定义当前工作区提示词与代理资产的分层装载规则。

目标：

- 让根 `AGENTS.md` 只保留硬约束
- 把角色契约、技能资产、任务资产从主提示词里拆出来
- 减少主上下文膨胀与多层传达偏移

参考来源：

- `prompts.chat-main/AGENTS.md`
- `prompts.chat-main/CLAUDE.md`
- `prompts.chat-main/PROMPTS.md`
- `prompts.chat-main/scripts/seed-skills.ts`

---

## 2. 分层模型

当前工作区统一采用五层装载：

### Layer 0: Hard Constraints

文件：

- [AGENTS.md](/Users/zyh/Desktop/ceshi123/ollamashiyong/AGENTS.md)

只包含：

- recall first
- 主代理唯一入口
- 主代理唯一写回权
- recall 重新触发规则
- 预算与工程边界

禁止放入：

- 角色细节
- 技能正文
- 当前任务证据
- 长篇示例

### Layer 1: Operator Quick Reference

文件：

- [CLAUDE.md](/Users/zyh/Desktop/ceshi123/ollamashiyong/CLAUDE.md)

只包含：

- 常用命令
- 装载顺序
- 入口速查

它服务于“怎么操作”，不服务于“什么是硬约束”。

### Layer 2: Shared Contract

文件：

- [base_contract.md](/Users/zyh/Desktop/ceshi123/ollamashiyong/codex-global-multi-agent/prompts/shared/base_contract.md)

只包含：

- JSON 输出契约
- 上下文注入边界
- 恢复与 fallback 语义
- 子代理通用行为边界

### Layer 3: Role Contracts

目录：

- [roles](/Users/zyh/Desktop/ceshi123/ollamashiyong/codex-global-multi-agent/prompts/roles)
- [ROLES_AND_SKILLS.md](/Users/zyh/Desktop/ceshi123/ollamashiyong/codex-global-multi-agent/ROLES_AND_SKILLS.md)

每个角色文件只描述：

- Identity
- Capabilities
- Limitations
- Behavior
- Format

禁止把别的角色职责、任务实例或长期技能正文混入角色契约。

### Layer 4: Skill Assets

来源：

- 当前 Codex skills
- `gstack-main/.agents/skills`
- 其他显式安装的技能资产

规则：

- 技能资产按任务按需加载
- 技能不是默认全局提示词的一部分
- 技能应尽量自包含，避免把一次性任务状态写死到技能正文里

### Layer 5: Task Assets

只包含当前任务专属内容：

- 当前目标
- `context_package`
- 当前证据
- 失败摘要
- 当前验收口径
- 当前工作计划

规则：

- 任务资产不得反向写入 Layer 0-4
- 一次性样本、临时夹具、临时 query 不应固化为长期角色提示词

---

## 3. 标准装载顺序

主代理：

1. 读取 Layer 0
2. 按需查看 Layer 1
3. 在需要多代理输出时读取 Layer 2
4. 派发具体角色时附加对应 Layer 3
5. 仅在任务明确需要时追加 Layer 4
6. 最后再注入 Layer 5

子代理：

1. 不直接读取长期记忆
2. 只接收主代理裁剪后的 Layer 2 + Layer 3 + 必要 Layer 4 + 必要 Layer 5
3. 不共享完整主会话

---

## 4. 与 prompts.chat-main 的映射关系

`prompts.chat-main` 的可借鉴点不是“照搬内容”，而是“分层方式”：

- `AGENTS.md`
  - 对应本工作区的硬约束层
- `CLAUDE.md`
  - 对应本工作区的操作速查层
- `PROMPTS.md` / `prompts.csv`
  - 对应内容资产层，而不是运行时硬约束层
- `scripts/seed-skills.ts`
  - 对应技能资产按需导入，而不是把 skill 正文塞进主提示词

因此当前工作区的执行原则是：

- 学分层，不学堆料
- 学按需加载，不学全量注入
- 学资产边界，不学把内容库伪装成系统协议

---

## 5. 当前最小执行规则

1. 根 `AGENTS.md` 只保留真正必须自动生效的规则
2. 角色职责统一放在 `roles/*.md`
3. 共享协议统一放在 `shared/*.md`
4. 技能仅在任务显式需要时附加
5. 当前任务证据、context package、验收样本一律视为任务资产，不回写到长期角色提示词
