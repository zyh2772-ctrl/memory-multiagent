# 记忆系统 + 多代理协调（公开版）

> 这是可公开分享的版本，已移除本地数据库和敏感配置，并简化了路径说明。

## 项目概览

`ollamashiyong-memory-multiagent` 包含两部分：

- **codex-global-memory/**：长期记忆系统（基于 SQLite / OpenMemory），提供 facts 存储、检索与写回协议
- **codex-global-multi-agent/**：多代理协调与运行时协议（Planner / Retriever / Verifier / Synthesizer 等角色）

它们通常作为上游组件，通过统一网关 / 主代理运行时（另一个仓库）接入推理链路。

## 仓库结构（简要）

- `codex-global-memory/openmemory/`
  - `openmemory_db_compat.py`：与 OpenMemory / mem0 兼容的 DB 接入层
  - `Dockerfile.openmemory-mcp` / `docker-compose.yml`：部署示例
  - *不包含* `.env` 与本地 `openmemory.db`，仅保留代码与示例配置

- `codex-global-multi-agent/`
  - `prompts/`：各角色的 Prompt 与 shared contract
  - `schemas/`：`subagent_contract.schema.json` 等协议定义
  - `runs/`：Planner / Retriever / Verifier 等阶段的离线运行记录（可作为测试样例）
  - `scripts/validate_and_merge.py`：将多阶段 JSON 结果进行验证和合并

## 运行与集成（示例）

1. 准备环境

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt  # 按实际依赖补充
```

2. 启动记忆系统（示意）

- 在 `codex-global-memory/openmemory` 下，根据你的部署方式：
  - 本地运行：使用 Python/uvicorn 启动 API
  - Docker：使用 `Dockerfile.openmemory-mcp` 或 `docker-compose.yml`

3. 运行多代理验证脚本

在 `codex-global-multi-agent` 下，你可以使用现有的 `runs/*.json` 作为输入，调用：

```bash
python3 scripts/validate_and_merge.py \
  runs/planner_v11.json \
  runs/retriever_v11.json \
  runs/verifier_v11.json \
  runs/synthesizer_v11.json \
  runs/failure_probe_v11.json \
  --max-stage-context-tokens 1200 \
  --max-long-term-tokens 1200 \
  --output runs/validation_report_v11.json
```

根据需要你可以替换上述 JSON 路径为你自己的运行结果。

## 脱敏说明

- 已删除本地 OpenMemory `.env`、`openmemory.db` 以及 `data/openmemory.db` 等数据库文件
- `.gitignore` 中默认忽略上述敏感文件，防止误提交
- 保留的 JSON 运行记录仅包含结构化协议内容，不含你的个人隐私数据
- 对指向你本机的绝对路径（如 `/Users/zyh/...`）建议在后续清理中整体替换为相对路径或占位符

## 与网关仓库的关系

- 网关仓库（例如 `ollamashiyong-gateway`）负责 HTTP 接入与模型路由
- 本仓库提供：
  - 长期记忆读写与 schema（memory）
  - 多代理角色、协议与验收工具（multi-agent）
- 二者通过主代理运行时的协议集成：
  - 主代理在需要时调用记忆系统的检索与写回
  - 多代理模块负责将复杂任务拆解为多个阶段，并产出结构化 JSON 结果

