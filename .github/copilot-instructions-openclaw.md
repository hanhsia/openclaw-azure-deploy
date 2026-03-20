# OpenClaw Azure VM Multi-Agent Workspace Instructions

本仓库是 OpenClaw 的 Azure VM 部署模板仓库，不是 OpenClaw 上游源码仓库。

## 作用范围

- 你当前维护的是 Azure 部署模板、部署脚本、测试和运维说明。
- `./openclaw` 目录仅供参考，用来查看上游实现、命令行为和最新能力；不要修改这个目录。
- 如果问题涉及 OpenClaw 产品行为、命令语义、agent 能力、路由规则或配置字段，优先以以下来源为准：
  - 上游源码：`./openclaw`
  - 官方文档：https://docs.openclaw.ai
- OpenClaw 变化很快。不要仅凭本仓库现有模板内容猜测最新行为；先核对上游代码或官方文档，再决定是否要同步 Azure 模板。

## 当前 Azure VM 背景

- 目标机器通过以下方式访问：
  - `ssh -i "$env:USERPROFILE\.ssh\id_ed25519" azureuser@openclaw-ven56myijhy4i.southeastasia.cloudapp.azure.com`
- 这台 VM 上运行的是已部署的 OpenClaw 网关，部署模板负责把 OpenClaw 安装到 VM 并完成基础配置。
- 当前关注点不是修改上游 OpenClaw 源码，而是让这台 VM 上的 OpenClaw 以稳定、可验证的方式支持多 agent 协同工作。

## 多 Agent 目标拓扑

默认把该 VM 的 OpenClaw 多 agent 架构视为以下目标状态，并围绕它编写、更新和验证部署逻辑：

- `main`：唯一对外入口，负责承接所有用户消息。
- `spec`：开发任务编排者，负责拆解需求、定义验收标准、调度其他开发域 agents。
- `coder`：代码实现者，默认按 TDD 工作。
- `qa`：测试与验证者，负责复现、回归、验证和缺陷定位。
- `docs`：持续文档化 agent，负责在任务进行中记录已验证行为、运维步骤和变更影响。
- `release`：交付收口 agent，负责整理提交说明、发布材料和 GitHub 侧收尾动作。
- `deploy`：部署 agent，负责在需要真实环境验证时执行 Azure 侧部署或验证动作。
- `ideas`：提案 agent，负责在稳定检查点向 `spec` 提出可落地的新功能或改进建议。

工作原则：

- `main` 只做入口和最终对话连续性维护，不直接承担完整开发执行链路。
- 软件开发类请求优先路由到 `spec`，由 `spec` 决定如何调用 `coder`、`qa`、`docs`、`release`、`deploy`、`ideas`。
- `ideas` 只负责提案，不直接推动编码。ideas 的提案需要经过 `spec` 验证可行性和优先级后，才能进入正式的开发流程。
- `docs` 需要在任务进行中持续更新文档或进展记录，不要等到最后一次性补文档。
- `deploy` 只负责部署和环境验证，不决定需求优先级。
- 其他 agent 之间可以互相调用，但必须通过 `spec` 协调，不能无边界直接互相委派。


## OpenClaw 多 Agent 配置约束

当用户要求你实现、修复或验证这台 VM 上的多 agent 协作时，默认检查并维护以下配置约束：

- 每个 agent 必须有独立的 workspace、`agentDir` 和 session store。
- 不要复用不同 agent 的 `agentDir`，避免认证信息和 session 污染。
- `main` 应保持为默认入口 agent。
- `tools.agentToAgent.enabled` 应显式开启，并只 allow 需要参与协作的 agent 集合。
- `tools.sessions.visibility` 应满足多 agent 协作所需的可见性。
- 每个 agent 的 `subagents.allowAgents` 必须有限制，不能无边界互相委派。
- `skills` 负责提示能力边界，`tools.profile` / `tools.allow` / `tools.deny` 负责真实工具权限，涉及宿主机命令时还要检查 exec approvals。
- 如果 direct message 需要继续汇总到统一入口，优先保持 `session.dmScope = "main"`。

## 处理 VM 上多 Agent 请求时的默认流程

只要请求涉及这台已部署 VM 的 OpenClaw 多 agent 配置、验证或故障排查，按下面顺序工作：

1. 先看上游信息，再看模板。
   - 先从 `./openclaw` 和 https://docs.openclaw.ai 确认 OpenClaw 当前支持的配置字段、agent 路由语义、CLI 命令和限制。

2. 再确认 VM 现状，不要臆测。
   - 通过 SSH 登录目标 VM。
   - 优先检查 `~/.openclaw/openclaw.json`、各 agent workspace 下的 `AGENTS.md`、以及 `~/.openclaw/agents/<agentId>/...` 结构。
   - 优先使用已验证的命令观察状态，例如：
     - `openclaw agents list --bindings`
     - `openclaw channels status --probe`
     - `systemctl --user status openclaw-gateway`

3. 只把“已在 VM 上验证过的需求”回写到模板。
   - 如果发现 VM 手工改动有效，而模板尚未覆盖，应该把改动沉淀到部署模板、脚本或测试中。
   - 如果只是上游行为变化，但模板还未验证，不要直接猜测性改模板。

4. 修改模板后必须补验证。
   - 部署模板的目标是可重复部署，不是一次性修机。
   - 任何影响 agent 拓扑、OpenClaw 安装、bootstrap 配置、Control UI、Teams/Feishu、插件、网关服务或路由行为的改动，都要补或更新测试。

## 编写和修改本仓库时的固定边界

- 不要修改 `./openclaw`。
- 不要把 VM 上的临时修复停留在手工步骤里；能模板化的要模板化，能测试化的要测试化。
- 不要把 OpenClaw 上游实现细节硬编码成过时假设；必要时在测试里体现当前行为。
- 如果更改了 branch，注意同步所有文档、脚本或模板里引用的 branch 名称，避免 URL 失效。
- 做 E2E 测试时，旧资源和新资源位于不同 resource group，不会互相干扰；删除旧资源后不用等待，可直接创建新资源继续验证。

## bootstrapScript 维护规则

- 不要手改 `azuredeploy.json` 里的 `variables.bootstrapScript`。
- `variables.bootstrapScript` 的真实维护源是：
  - `bootstrapScript.template.sh`
  - `openclaw-browser-url.template.sh`
  - `openclaw-approve-browser.template.sh`
  - `openclaw-approve-teams-pairing.template.sh`
- 不要把 `azuredeploy.json` 里抽取出来的 shell 内容反向当成源文件回写。
- 如果需要改 bootstrap：
  - 先改上述模板源文件。
  - 再运行 `python scripts/sync_bootstrap_script.py sync`。
- 该命令会校验 shell 语法、渲染 helper 脚本、生成 `generated/` 下的 ARM 产物，并同步更新 `azuredeploy.json`。
- 模板中的注释可以保留给人看，但生成后的 ARM 内容应从 `#!/usr/bin/env bash` 开始，不能依赖额外头部注释。
- OpenClaw 运行时配置应主要在 `bootstrapScript.template.sh` 中通过 `openclaw onboard`、`openclaw config` 和相关脚本完成，ARM 层只负责传 Azure 特有输入。
- `azuredeploy.json` 中的 bootstrap 仍然是 ARM `format()` 字符串；如果往内嵌 shell/JS 里新增字面量 `{` 或 `}`，必须正确转义，否则 ARM 校验会在部署前失败。

## 测试要求

- 每次 OpenClaw feature update 或部署行为更新后，都要考虑是否需要新增或更新测试，确保部署模板仍能覆盖该能力。
- 修改 bootstrap 或模板同步逻辑后，至少运行：
  - `python -m pytest tests/test_templates.py`
- 如果改动影响部署流程、VM 配置、插件安装、agent 拓扑、渠道配置或真实 Azure 集成，补充运行对应的 Python 测试，并在必要时更新集成测试断言。
- 对于这类仓库，测试的重点是“部署后 VM 上实际会发生什么”，而不是只验证静态字符串是否变化。

## 搜索与取证习惯

- 搜索本工作区时，默认包含 `.gitignore`、其他 ignore 文件和 workspace exclude 规则忽略掉的文件。
- 终端搜索优先使用 `rg -uu`。
- 工具搜索优先使用 `includeIgnoredFiles: true`，这样生成产物、忽略目录和测试输出也能被纳入排查范围。

## 回答用户时的优先级

- 先说明上游真实行为，再说明这个 Azure 模板是否已经实现。
- 如果用户问的是“当前 VM 是否已经这样配置”，先查 VM 现状再回答。
- 如果用户问的是“如何让模板支持这个能力”，优先给出可模板化、可测试、可重复部署的实现方案。
- 如果用户同时提到 OpenClaw 行为和 Azure 部署行为，先区分“上游能力”与“本仓库是否已同步实现”这两个问题，不要混为一谈。