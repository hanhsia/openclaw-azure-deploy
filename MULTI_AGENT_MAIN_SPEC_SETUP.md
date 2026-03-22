# Main 入口多 Agent 配置说明

本文档记录了我在 OpenClaw Azure VM 上实际完成并验证通过的改动，用于实现以下目标：保留 `main` 作为唯一用户入口，同时把软件开发类任务委派给后台 agents 处理。

## 当前目标架构

- `main`：统一总入口，负责接收所有外部消息
- `spec`：开发任务编排者，默认按 OpenSpec 方式拆解开发任务
- `coder`：代码实现者，默认按 TDD 工作
- `qa`：测试与验证者
- `docs`：持续文档化 agent，负责在任务进行中不断记录进展和已验证行为
- `release`：交付与 check-in 准备者，负责收口发布材料和 GitHub 侧动作
- `deploy`：部署 agent，负责用 `az` 把可运行版本部署到 Azure Container Apps 供用户直接测试
- `ideas`：周期性 feature 提案 agent，结合当前项目现状向 `spec` 提出可落地的新能力方案
- Heartbeat 不再留给 `main`；模板会显式关闭默认 / `main` heartbeat，并把周期性 heartbeat 交给 `ideas`

## OpenClaw 里 agent 能力是怎么实现的

OpenClaw 里要把一个 agent 变成“会某件事”，实际上有三层：

1. `skills`
   - 作用：告诉 agent 什么时候该用什么 CLI、什么流程、什么命令模式。
   - 实现：`agents.list[].skills` 可以做每个 agent 的 skills 白名单；省略表示不过滤，空数组表示不加载任何 skills。
   - 来源：每个 agent 自己的 `<workspace>/skills`，以及共享的 `~/.openclaw/skills`、bundled skills。

2. `tools.profile` / `tools.allow` / `tools.deny`
   - 作用：决定模型最终能不能真的调用文件、运行时、session、消息等工具。
   - 实现：`agents.list[].tools.profile` 是基础工具集，之后再叠加 allow/deny。
   - 关键点：skill 只负责“教会”，tool policy 才负责“放权”。

3. `exec approvals`
   - 作用：控制 agent 在真实主机上运行命令时是否允许、是否需要审批、是否走 allowlist。
   - 存储：`~/.openclaw/exec-approvals.json`
   - 关键点：即使 tool policy 允许 `exec`，如果 exec approvals 不允许，命令仍然可能跑不起来。

换句话说：

- `skills` 决定 agent 会不会想到用某个能力。
- `tools` 决定 agent 有没有这个能力的调用权限。
- `exec approvals` 决定涉及主机命令时最终放不放行。

## 当前建议的每 agent 能力分配

- `spec`
  - skills：`openspec`
  - tools：`coding`
  - 目的：它本质上是调度者 / orchestrator，不是固定 workflow 引擎；会通过 `openspec` CLI 先生成或校验变更提案、规格、任务和验收标准，再根据任务状态灵活决定调用哪些 agents、调用顺序和迭代次数。

- `coder`
  - skills：`coding-agent`
  - tools：`coding`
  - 目的：会调用 coding-agent 相关流程，并具备代码读写与运行能力。

- `qa`
  - skills：空数组，不额外加载技能提示词
  - tools：`coding`
  - 目的：重点是本地执行测试、复现问题、查看日志，而不是使用额外编排型 skill。

- `release`
  - skills：`github`、`gh-issues`
  - tools：`coding`
  - 目的：既能做 GitHub 原生命令，也能在需要时使用 gh-issues 的编排能力，并负责最终发布收口。

- `docs`
  - skills：`github`
  - tools：`coding`，额外 deny `image`
  - 目的：保留文档读写和 GitHub 操作能力，在开发进行中持续同步进展、操作说明和已验证结论，不给无关图片能力。

- `release`
  - skills：`github`、`gh-issues`
  - tools：`coding`
  - 目的：既能做 GitHub 原生命令，也能在需要时使用 gh-issues 的编排能力，并负责最终发布收口。

- `deploy`
  - skills：空数组
  - tools：`coding`
  - 目的：负责在需要真实云端验证时，用 `az` 命令把 Web 应用部署到 Azure Container Apps，并回传访问地址、部署结果和剩余手工步骤。

- `ideas`
  - skills：空数组
  - tools：`minimal` + `sessions_list` / `sessions_history` / `sessions_send`
  - heartbeat：显式启用，默认每 `15m` 触发一次，`target: "none"`，只做内部提案，不对外发消息；但如果 `spec` / `coder` / `qa` / `docs` / `deploy` / `release` 仍在处理当前交付，就返回 `HEARTBEAT_OK`。
  - 目的：只允许看上下文、发建议，不给它代码执行和文件修改能力；它应定期把基于当前项目状态的 feature 提案发给 `spec`。

## 让这些能力真正生效还需要什么

1. skill 本身要可加载。
`openspec` skill 需要 `openspec` 在 PATH 里，并且会放在 `spec` 的 workspace skill 目录 `/data/workspace-spec/skills/openspec/SKILL.md`。`coding-agent` 需要 `claude` / `codex` / `opencode` / `pi` 之一在 PATH 里。`github` 需要 `gh` 在 PATH 里并已认证。`gh-issues` 需要 `curl`、`git`、`gh`，以及 `GH_TOKEN` 或对应 skills config。`deploy` 依赖 `az` 在 PATH 里，并已经登录到正确的 Azure 订阅；如果目标是 Container Apps，还要确保对应资源组、Container Apps Environment、镜像源或源码发布路径可用。

1. tool policy 要允许。
`main` 需要最少可用的读取、状态和 agent-to-agent 工具；`coder` / `qa` / `release` / `docs` / `deploy` 至少需要覆盖文件、运行时、web 和 sessions 的显式 allowlist。不要继续依赖全局 `tools.profile = coding`，否则 inherited profile 里的无关工具可能污染实际运行时。

1. 如果命令要在主机上执行，要检查 exec approvals。
`qa` 会跑 `pnpm test`、`pytest`、`npm test`；`release` / `docs` 会跑 `gh`、`git`；`deploy` 会跑 `az`、`docker` 或相关打包/发布命令。这些如果被 host 审批策略拦住，就需要在 `~/.openclaw/exec-approvals.json` 对应 agent 下放开或 allowlist。

## 为什么采用这个结构

这个结构的核心目的是把“通用助手”与“开发工作流”分开，而不是让所有请求都直接进入开发链路。

- 普通问答、个人助理、闲聊类请求由 `main` 直接处理。
- 软件开发类请求由 `main` 转交给 `spec`。
- `spec` 负责调度 `coder`、`qa`、`docs`、`release`、`deploy`、`ideas`。
- `docs` 在开发过程中持续记录里程碑、决策、验证结果和操作影响，而不是只在最后补文档。
- `ideas` 在稳定检查点或自身 heartbeat 节奏上向 `spec` 提出新 feature / 改进方案。
- `spec` 负责判断 `ideas` 提案的技术可行性、与当前优先级是否匹配，以及是否进入实施。
- 当用户需要真实云端测试时，`spec` 也可以调度 `deploy` 把当前可运行版本发布到 Azure Container Apps。
- 被 `spec` 采纳的 `ideas` 提案，会进入正常实施循环，例如 `coder` -> `qa` -> `docs` -> `release`，必要时再加 `deploy`。
- 用户最终看到的对话连续性仍然保留在共享的 `main` 会话里。

可以把当前主要链路理解为：

`main` -> `spec` -> `coder` / `qa` / `docs` / `release`

并行的长期辅助链路是：

- `spec` <-> `docs`：持续文档化当前进展
- `spec` <-> `deploy`：在需要真实云端验证时部署到 Azure Container Apps
- `ideas` -> `spec`：周期性提出 feature 提案
- `spec` -> `coder` / `qa` / `docs` / `release` / `deploy`：仅在判定可行且值得做时才正式实施

这里要特别强调：

- 这不是一个写死顺序的 workflow 系统。
- `ideas -> spec -> coder -> qa -> docs -> release` 只是最常见的一条主链路。
- 实际运行中，`spec` 会根据当前任务状态灵活调度，比如先让 `qa` 复现问题、先让 `docs` 补充操作说明、先让 `deploy` 部署测试环境，或者多轮往返 `coder` / `qa`。
- 所以 `spec` 实际上就是整个开发域的调度者和编排者。

当前阶段不处理结构化“客户需求事件” webhook，因此 webhook 不是本轮改造的阻塞项。

## VM 上实际做了什么修改

### 1. 调整 direct message 会话模型

VM 被配置为让 direct message 共享 `main` 会话：

```json
{
  "session": {
    "dmScope": "main"
  }
}
```

这样可以让 Control UI、Feishu、Teams 的 direct message 继续共用同一条主会话上下文。

如果 VM 之前用的是 `per-channel-peer`，还可以额外清理旧 direct sessions，避免 Feishu 或 Teams 回落到旧会话。

### 2. 新增后台 agents

我在 VM 上新增了以下隔离 agent：

- `spec`，workspace 为 `/data/workspace-spec`
- `coder`，workspace 为 `/data/workspace-coder`
- `qa`，workspace 为 `/data/workspace-qa`
- `docs`，workspace 为 `/data/workspace-docs`
- `release`，workspace 为 `/data/workspace-release`
- `deploy`，workspace 为 `/data/workspace-deploy`
- `ideas`，workspace 为 `/data/workspace-ideas`

每个 agent 都有自己的 workspace、`agentDir` 和 session store，路径位于 `~/.openclaw/agents/<agentId>/` 下。

### 3. 开启跨 agent 协作能力

VM 的 `openclaw.json` 被更新为允许跨 agent 协作：

```json
{
  "tools": {
    "agentToAgent": {
      "enabled": true,
      "allow": ["main", "spec", "coder", "qa", "docs", "release", "deploy", "ideas"]
    },
    "sessions": {
      "visibility": "all"
    }
  }
}
```

### 4. 限制协作边界

我通过 `subagents.allowAgents` 给每个 agent 限定了可委派范围：

- `main` 只能委派给 `spec`
- `spec` 可以委派给 `coder`、`qa`、`docs`、`release`、`deploy`、`ideas`
- `coder` 只能回委派给 `spec`
- `qa` 只能回委派给 `spec`
- `docs` 只能回委派给 `spec`
- `release` 只能回委派给 `spec`
- `deploy` 只能回委派给 `spec`
- `ideas` 可以委派给 `spec`

这样做的目的不是让 worker 变弱，而是把“谁来协调下一跳”重新收回到 `spec`：

- `spec` 负责用 OpenSpec 和 `TASK_STATUS.md` 维护任务真相
- `coder` / `qa` / `docs` / `release` / `deploy` 负责各自专业执行，不再横向拉其他 worker 形成隐式链路
- 如果执行中发现缺失上下文、需求变化或需要别的专业介入，worker 先把 blocker 和建议下一跳回给 `spec`，再由 `spec` 决定后续调度

### 5. 干净上下文如何传递

要让 `coder`、`qa`、`docs` 等 agent 拿到“正确且尽量少污染”的上下文，关键不是把完整聊天历史都转发过去，而是把上下文拆成几层：

- 目标 agent 自己的 workspace / `AGENTS.md` / skills：保证它先用自己的角色规则起步，而不是继承 `spec` 的 persona
- `spec` 的 handoff：只发当前任务所需的 objective、输入、允许修改的文件、预期输出和验收标准
- 权威文件：优先让 worker 先读 `TASK_STATUS.md`、相关 OpenSpec artifacts、以及明确点名的源码/测试/文档文件，而不是依赖长对话摘要

OpenClaw 当前的 cross-agent spawn 已经会切到目标 agent 自己的 workspace，而不是继续沿用调用者 workspace；这意味着 `spec` 调 `coder` 时，`coder` 会加载自己的 workspace 规则。真正需要控制的是 handoff 内容本身，所以这里把 prompt 也收紧为“优先引用权威文件，不复述整段历史”。

这保证了协作是自由的，但不是无边界的。

当前边界设计对应的实际工作方式是：

- `docs` 不直接推动需求变更，只负责把已发生且已验证的事情持续记录下来。
- `ideas` 不直接推动编码，只能把提案交给 `spec`。
- `deploy` 不直接决定发哪一版，也不定义发布目标；它只负责把 `spec` 认可的版本部署到目标 Azure 环境。
- `spec` 是唯一有权把 `ideas` 的提案转成正式实施任务的开发控制点。

### 5. 更新各 workspace 的角色提示词

VM 上以下文件被更新：

- `/data/workspace/AGENTS.md`
- `/data/workspace-spec/AGENTS.md`
- `/data/workspace-coder/AGENTS.md`
- `/data/workspace-qa/AGENTS.md`
- `/data/workspace-docs/AGENTS.md`
- `/data/workspace-release/AGENTS.md`
- `/data/workspace-deploy/AGENTS.md`
- `/data/workspace-ideas/AGENTS.md`
- `/data/workspace/BOOT.md`

角色分工如下：

- `main` 负责识别请求是否属于开发任务
- `main` 保留最终用户会话和最终回复口径
- `spec` 负责开发任务编排，并优先采用 OpenSpec 风格拆解需求、范围和验收标准；同时负责审查 `ideas` 的 feature 提案并决定是否进入实施
- `coder` 负责代码修改，并默认按 TDD 执行
- `qa` 负责验证和缺陷发现
- `docs` 负责 README、运维说明、用户文档和任务过程中的阶段性进展记录
- `release` 负责交付准备、check-in 说明和 GitHub 收尾动作
- `deploy` 负责用 `az` 将当前可运行版本部署到 Azure Container Apps，便于用户直接测试
- `ideas` 负责按稳定检查点或周期性节奏提出新 feature / 优化方案，并把候选项交给 `spec`

### 5.1 任务状态总账与交接协议

为了让 `main` 能明确知道“当前任务在谁手里、卡在哪、下一步谁接手”，本轮改造还额外引入两条约束：

- `/data/workspace/TASK_STATUS.md` 作为活跃开发任务的状态总账，由 `spec` 维护。
- backend agents 回给 `spec` 时，必须使用统一的 `STATUS:` 头部，至少包含：`agent`、`state`、`task`、`current`、`blocker`、`next`。

约定的工作方式是：

- `spec` 在每次委派前，先把 `TASK_STATUS.md` 写成当前真实状态。
- `coder` / `qa` / `docs` / `release` / `deploy` / `ideas` 完成一个阶段、遇到阻塞或需要交接时，先回 `STATUS:`，再补细节。
- `main` 在回答“现在做到哪了”“卡在哪了”“谁在处理”这类问题时，优先在同一轮里读取 `TASK_STATUS.md` 或向 `spec` 要最新状态，而不是靠猜。

### 5.3 抑制无意义 announce 噪音

OpenClaw 上游在 `sessions_send` / `sessions_spawn` / subagent 收尾时，会自动插入一个 agent-to-agent announce step，用来决定是否把最终汇总继续回传。

这套多 agent 模板已经有自己的 `STATUS:` 协议，所以如果 announce step 里没有任何新增信息，就只会制造像 “Agent-to-agent announce step.” 这样的内部噪音。

当前模板会在 backend agent 提示词里显式要求：

- 如果收到 OpenClaw 的 agent-to-agent announce step，且没有超出已有 `STATUS:` / result 的新增信息，就精确回复 `ANNOUNCE_SKIP`
- 只有 announce step 确实需要补一条新的浓缩结论时，才继续输出内容

这样做的目标是让真正有价值的状态继续走 `STATUS:` 协议，而不是让内建 announce 机制重复回报一遍空结果。

这样做的目标不是增加更多 agent，而是把多 agent 协作里的状态流转固定下来，避免 `main` 只能看到一串模糊对话而不知道现在是谁在执行、阻塞点在哪里。

### 5.2 为不同 agent 分配 skills 和工具能力

除了更新 `AGENTS.md` 里的角色提示词，VM 上的 `~/.openclaw/openclaw.json` 也被更新为按 agent 分配 skills 和 tools，并移除了 inherited 的顶层 `tools.profile`：

- `spec`
  - `skills: ["openspec"]`
  - `tools.allow`: 显式包含文件、运行时、web、sessions、subagents、`session_status`
  - workspace skill：`/data/workspace-spec/skills/openspec/SKILL.md`

- `coder`
  - `skills: ["coding-agent"]`
  - `tools.allow`: 显式包含文件、运行时、web、sessions、subagents、`session_status`

- `qa`
  - `skills: []`
  - `tools.allow`: 显式包含文件、运行时、web、sessions、subagents、`session_status`

- `release`
  - `skills: ["github", "gh-issues"]`
  - `tools.allow`: 显式包含文件、运行时、web、sessions、subagents、`session_status`

- `docs`
  - `skills: ["github"]`
  - `tools.allow`: 显式包含文件、运行时、web、sessions、subagents、`session_status`

- `release`
  - `skills: ["github", "gh-issues"]`
  - `tools.allow`: 显式包含文件、运行时、web、sessions、subagents、`session_status`

- `deploy`
  - `skills: []`
  - `tools.allow`: 显式包含文件、运行时、web、sessions、subagents、`session_status`

- `ideas`
  - `skills: []`
  - `tools.profile: minimal`
  - `tools.allow: ["sessions_list", "sessions_history", "sessions_send"]`

这里要注意三件事：

- `skills` 负责告诉 agent 什么时候应该用哪种 CLI / 工作流。
- `tools.profile` / `allow` / `deny` 决定模型最终能不能真的调用对应工具。
- 如果涉及真实主机命令，最终还要受 `~/.openclaw/exec-approvals.json` 约束。

### 6. 启用 hooks 并加入 `BOOT.md`

本轮改造会启用以下 bundled hooks：

- `boot-md`
- `session-memory`
- `command-logger`

其中：

- `boot-md` 会在 gateway 启动时执行 workspace 根目录的 `BOOT.md`
- `session-memory` 会在 `/new` 或重置后把上下文写入 memory 文件
- `command-logger` 会把命令事件记录到 `~/.openclaw/logs/commands.log`

`BOOT.md` 在当前架构里不是“总控大脑”，而是给 `main` 的启动检查单。真正的总控仍然是 `main`，开发域总控是 `spec`。

在当前版本里，`ideas` 的“每隔一段时间触发一次”已经通过 OpenClaw 的 per-agent heartbeat 显式实现：

- 模板会把 `agents.defaults.heartbeat` 设为 `{ "every": "0m" }`，避免 `main` 继续吃 upstream 默认 heartbeat。
- 模板会给 `ideas` 单独配置 heartbeat，默认每 `15m` 触发一次，且 `target: "none"`，不会向用户外发 heartbeat 消息。
- `/data/workspace-ideas/HEARTBEAT.md` 会作为 ideas 的 heartbeat checklist；如果 `spec` / `coder` / `qa` / `docs` / `deploy` / `release` 仍在活跃交付，就返回 `HEARTBEAT_OK`；只有在交付环稳定或空闲时，才升级一个值得做的具体提案给 `spec`。
- `ideas` 产出的内容仍然先回到 `spec`，不直接进入编码。

也就是说：当前脚本已经把链路角色配好了，但“固定时间间隔自动触发”还不是 OpenClaw 内建定时器，而是下一层自动化能力。

### 7. 已完成的轻量验证

脚本在 VM 上应用完成后，已经跑过一轮轻量验证，确认以下结果：

- `openclaw agents list --bindings` 能看到 `main`、`spec`、`coder`、`qa`、`docs`、`release`、`deploy`、`ideas`
- `openclaw config get session.dmScope --json` 返回 `main`
- `openclaw config get tools.sessions.visibility --json` 返回 `all`
- `openclaw config get tools.agentToAgent --json` 返回已启用且 allow 了全部参与协作的 agents
- `/data/workspace/TASK_STATUS.md` 已存在，且包含 `Owner`、`State`、`Current Step`、`Blocker`、`Next Handoff`
- `main`、`spec` 和 backend agents 的 `AGENTS.md` 都包含状态总账 / `STATUS:` 交接协议约束
- hooks 状态为 `boot-md`、`session-memory`、`command-logger` 全部 ready

这说明当前 VM 上已经不是“只有角色描述”，而是 skills、tool policy、hooks、角色提示词，以及任务状态总账都已经同时生效。

## 什么没有修改

这些 live 改动没有动 Azure 部署模板本身。

- 没有修改 `bootstrapScript.template.sh`
- 没有修改 `azuredeploy.json`

## 一键脚本

可以使用 [scripts/configure_main_spec_multiagent.py](scripts/configure_main_spec_multiagent.py) 把同样的改动应用到一台已部署完成的 VM 上。

### 脚本会做什么

1. 通过 SSH 连接到 VM
2. 验证登录 shell 中 `openclaw` 是否可用
3. 创建缺失的后台 agents：`spec`、`coder`、`qa`、`docs`、`release`、`deploy`、`ideas`
4. 更新 `~/.openclaw/openclaw.json`
5. 用专门的 `main` 提示词覆盖 `/data/workspace/AGENTS.md`
6. 写入 `/data/workspace/BOOT.md`，并在缺失时初始化 `/data/workspace/TASK_STATUS.md`
7. 显式关闭默认 / `main` heartbeat，并给 `ideas` 写入独立 heartbeat 配置与 `/data/workspace-ideas/HEARTBEAT.md`
8. 用角色专用提示词覆盖 backend agents 的 `AGENTS.md`
9. 在 `~/.openclaw/openclaw.json` 里写入 per-agent `skills` 和 `tools` 能力分配，并移除 inherited 的顶层 `tools.profile`
10. 启用 `boot-md`、`session-memory`、`command-logger`
11. 如果传入 `--reset-main-session`，先备份 `~/.openclaw/agents/main/sessions/`，再对 `agent:main:main` 执行官方 `sessions.reset`
12. 重启 `openclaw-gateway`
13. 执行一轮不会污染 live 会话的轻量验证

### 可选的旧会话清理

如果目标 VM 之前使用的是 `per-channel-peer`，而你希望后续 direct message 全部统一收敛到共享的 `main` 会话，可以这样运行脚本：

```bash
python scripts/configure_main_spec_multiagent.py \
  --host <vmPublicFqdn> \
  --prune-legacy-direct-sessions
```

这个可选参数会删除所有 `agent:main:*` 的 direct sessions，但保留 `agent:main:main`，并删除对应 transcript 文件。

## 使用方法

### Windows PowerShell

```powershell
python .\scripts\configure_main_spec_multiagent.py `
  --host openclaw-ven56myijhy4i.southeastasia.cloudapp.azure.com `
  --ssh-key "$env:USERPROFILE\.ssh\id_ed25519"
```

### Bash

```bash
python scripts/configure_main_spec_multiagent.py \
  --host openclaw-ven56myijhy4i.southeastasia.cloudapp.azure.com \
  --ssh-key ~/.ssh/id_ed25519
```

### 可选参数

- `--user azureuser`：SSH 用户名，默认值是 `azureuser`
- `--skip-dm-scope-main`：不强制设置 `session.dmScope = main`
- `--prune-legacy-direct-sessions`：删除旧 direct sessions，只保留 `agent:main:main`
- `--reset-main-session`：备份 `~/.openclaw/agents/main/sessions/` 后，重置当前 `agent:main:main` 会话
- `--skip-validation`：跳过最后的轻量验证

### 清理被旧探针污染的 main 会话

如果当前 `main` 会话已经被旧的 role probe / validation prompt 污染，推荐使用：

```bash
python scripts/configure_main_spec_multiagent.py \
  --host <vmPublicFqdn> \
  --reset-main-session
```

这个选项会先在远端写入一个类似下面的备份包：

- `~/.openclaw/agents/main/main-session-reset.<timestamp>.tgz`

然后调用官方网关控制面：

```bash
openclaw gateway call sessions.reset --json --params '{"key":"agent:main:main"}'
```

效果是：

- `agent:main:main` 获得新的 `sessionId`
- 旧 transcript 由 OpenClaw 按 reset 机制归档为 `.jsonl.reset.*`
- 之后 `main` 会从新的干净会话继续，但仍保留新的 `AGENTS.md` / `BOOT.md` / `TASK_STATUS.md` 约束

## 当前执行顺序

基于已经完成的多 agent 骨架，当前建议顺序如下：

1. 入口权限收紧：当前跳过，因为这台 OpenClaw 只给你本人使用
2. OpenSpec CLI：已安装，但需要写入 `spec` 的职责和流程
3. 新建 `spec/coder/qa/release/deploy`：已完成后即可形成完整开发与测试部署链路
4. 补强 `AGENTS.md`：当前脚本会升级为第二版，加入 OpenSpec、TDD、GitHub、docs、ideas
5. 启用 `boot-md`、`session-memory`、`command-logger`：本脚本会完成
6. 写 `BOOT.md`：本脚本会完成
7. webhook：当前跳过，不处理结构化客户需求事件
8. 固定 `coder` 为 TDD：本脚本会完成
9. 让 `docs` 进入持续文档化链路：本脚本会完成
10. 增加 `deploy`，负责把当前版本部署到 Azure Container Apps：本脚本会完成角色约束
11. 让 `ideas` 周期性向 `spec` 提案：本脚本会通过 per-agent heartbeat 完成定时触发，并避免 `main` 再使用 heartbeat
12. 让 `release` 使用 GitHub skill：本脚本会完成职责约束

## 验证命令

脚本执行完成后，可以用下面几条命令检查结果。

```bash
ssh -i ~/.ssh/id_ed25519 azureuser@<vmPublicFqdn> \
  "bash -lc '. /etc/profile >/dev/null 2>&1 || true; openclaw agents list --bindings'"
```

```bash
ssh -i ~/.ssh/id_ed25519 azureuser@<vmPublicFqdn> \
  "bash -lc '. /etc/profile >/dev/null 2>&1 || true; openclaw config get tools.agentToAgent --json'"
```

```bash
ssh -i ~/.ssh/id_ed25519 azureuser@<vmPublicFqdn> \
  "bash -lc 'sed -n "'"'1,80p'"'"' /data/workspace/TASK_STATUS.md'"
```

预期结果：

- `main` 仍然是默认入口 agent
- `spec/coder/qa/docs/release/deploy/ideas` 已存在并可用
- `TASK_STATUS.md` 已存在并包含当前 owner / blocker / next handoff 字段
- `main` 的提示词会要求把活跃 agent、当前步骤、阻塞点和下一跳明确告诉用户
- `main` 的提示词会要求在同一轮内先刷新状态板，再回答开发任务进展问题
- `spec` 的提示词会要求维护 `TASK_STATUS.md` 并把 backend handoff 归一化成状态信息
- backend agents 的提示词会要求先输出 `STATUS:` 头部，再给出细节

## 回滚说明

脚本在修改 VM 之前会写入远端备份：

- `~/.openclaw/openclaw.json.main-spec.bak.<timestamp>`
- 每个被覆盖的 prompt 文件会保存为 `<workspace>/AGENTS.md.main-spec.bak.<timestamp>`
- 如果启用了旧 direct session 清理，还会保存 session store 备份

如果你需要回滚，恢复相应备份文件后重启 gateway 即可：

```bash
systemctl --user restart openclaw-gateway
```
