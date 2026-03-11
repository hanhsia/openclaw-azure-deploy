# OpenClaw Azure Teams Testing

[中文](#zh-cn) | [English](#en)

<a id="zh-cn"></a>
# 中文

本文档用于手工测试 OpenClaw Azure 部署模板中的 Microsoft Teams 集成是否按预期工作。

## 测试范围

- Azure 模板已创建 Teams 相关资源
- 虚拟机已安装 `@openclaw/msteams` 插件
- OpenClaw 已加载 Teams 配置
- Azure Bot 的 Messaging Endpoint 可访问
- Teams 私聊（DM）可正常收发消息
- Teams `pairing` 流程可正常批准

## 前置条件

开始测试前，请确保以下事项已完成：

1. 已使用 [azuredeploy.json](/c:/Users/hanxia/repos/openclaw-azure-deploy/azuredeploy.json) 完成部署。
2. 部署参数中已填写 `msteamsAppId` 和 `msteamsAppPassword`。
3. Teams app manifest/package 已在 Teams 侧上传并安装，且至少包含 `personal` scope。
4. 你可以通过 SSH 登录虚拟机。

## 已验证的最小手测闭环

如果你现在只是想按最新验证结果手工走通一次，直接按下面顺序操作：

1. 部署模板并记下 `vmPublicFqdn` 和 OpenClaw 公网 URL。
2. 在 Azure Bot 资源里确认 Messaging Endpoint 为 `https://<你的域名>/api/messages`，且 Teams Channel 已启用。
3. 用 [teams-app-package/build-app-package.ps1](/c:/Users/hanxia/repos/openclaw-azure-deploy/teams-app-package/build-app-package.ps1) 生成 Teams app package，并上传到 Teams。
4. 在虚拟机上执行 `openclaw gateway status`，确认 gateway 正常。
5. 在 Teams 中给 bot 发第一条私聊消息。
6. 回到虚拟机执行 `openclaw pairing list msteams --json`，确认已经出现 pending pairing request。
7. 直接执行 `openclaw-approve-teams-pairing`，这里不需要手工传入 code。
8. 回到同一个 Teams 私聊窗口，再发第二条消息。
9. 确认第二条消息开始可以正常收到 bot 回复。

当前已验证的实际行为是：

1. 第一条 Teams DM 在默认 `pairing` 模式下通常不会直接收到 pairing code，也不会立即收到正常回复。
2. 只要 pending request 已经创建，`openclaw-approve-teams-pairing` 无参模式就可以直接批准最新请求。
3. 批准之后，同一用户发第二条 DM 时，消息链路可以正常工作。
4. `--notify` 对应的“批准后主动通知首条 DM 用户”当前仍可能失败，这是 OpenClaw 上游问题，不代表 Azure 部署模板失效。

## 零、如何在 Teams 侧部署 Bot

如果你还没有把 bot 真正部署到 Teams 客户端里，先完成这一节，再继续后面的测试。

### A. 准备 Microsoft App 凭据

当前模板会自动创建 Azure Bot 资源，因此这里不需要你手工再创建一个 Bot Service。

但在部署模板之前，你仍然需要先准备好 Teams 使用的身份凭据，也就是：

1. Microsoft App ID
2. Client secret value

对于当前部署模板：

1. `msteamsAppId` 对应 Microsoft App ID
2. `msteamsAppPassword` 对应 client secret value
3. tenant ID 由模板自动取当前 Azure tenant 并写入 OpenClaw 配置

### B. 确认模板已创建 Azure Bot 资源

部署完成后，在 Azure Portal 中确认模板已经创建了 Azure Bot 资源：

1. 打开当前部署生成的 `Microsoft.BotService/botServices`
2. 确认它存在且状态正常
3. 确认 Teams Channel 已启用

### C. 配置 Azure Bot 的 Messaging Endpoint

进入 Azure Bot 资源的 `Configuration` 页面，设置：

```text
https://<你的域名>/api/messages
```

这里的域名应当对应当前模板部署出的公网域名或你配置的自定义 hostname。

通常模板已经会创建 Bot Service 并启用 Teams Channel，但这里仍然建议你部署后人工核对一次。

### D. 核对 Teams Channel

在 Azure Bot 资源的 `Channels` 页面：

1. 打开 `Microsoft Teams`
2. 确认它已经存在且处于启用状态
3. 如果门户提示还需要确认或保存，完成一次保存

如果 Teams channel 没启用，后面 Teams 客户端里即使装了 app 也不会正常工作。

### E. 生成本地 Teams app package

当前仓库已经补了一套本地 app package 模板，不需要你先手工拼 ZIP。

直接使用：

1. [teams-app-package/build-app-package.ps1](/c:/Users/hanxia/repos/openclaw-azure-deploy/teams-app-package/build-app-package.ps1)
2. [teams-app-package/manifest.template.json](/c:/Users/hanxia/repos/openclaw-azure-deploy/teams-app-package/manifest.template.json)
3. [teams-app-package/README.md](/c:/Users/hanxia/repos/openclaw-azure-deploy/teams-app-package/README.md)

最小示例：

```powershell
./teams-app-package/build-app-package.ps1 `
  -AppId "<Azure Bot App ID>" `
  -BotDomain "<你的域名或 Azure FQDN>"
```

脚本会自动：

1. 生成 `manifest.json`
2. 生成占位 `outline.png` 和 `color.png`
3. 打出最终 ZIP 包

如果你的目标是“通过导入方式测试”，优先使用默认的 `import-test` 模板。

它会：

1. 只保留 `personal` scope
2. 去掉 `team` 和 `groupChat` scope
3. 去掉容易触发管理员审批的 RSC 权限

这样更适合 Teams 客户端里的 `Upload a custom app` / `上传自定义应用` 测试。

如果你需要更完整的 team/groupChat 能力，再显式改用 quickstart manifest：

```powershell
./teams-app-package/build-app-package.ps1 `
  -TemplateName quickstart `
  -AppId "<Azure Bot App ID>" `
  -BotDomain "<你的域名或 Azure FQDN>"
```

原来的固定字段 quickstart manifest：

1. 应用名固定为 `OpenClaw`
2. 描述和 developer name 已预填
3. 你通常只需要提供 App ID 和域名

如果你仓库根目录的 `.env` 已按 [/.env.example](/c:/Users/hanxia/repos/openclaw-azure-deploy/.env.example) 填好，甚至可以直接执行：

```powershell
./teams-app-package/build-app-package.ps1
```

脚本会自动从 `.env` 读取：

1. `TEST_MSTEAMS_APP_ID`
2. `TEST_MSTEAMS_BOT_DOMAIN` 或 `TEST_OPENCLAW_PUBLIC_URL`
3. 可选的 package ID、version、developer 信息

如果你跑的是仓库里的 Azure 集成测试，`TEST_MSTEAMS_BOT_DOMAIN` 不需要预先手填。
测试会在部署成功后，从 `openclawPublicUrl` 自动提取 host，再自动生成适合导入测试的 Teams app package，并落到仓库内固定目录：

```text
teams-app-package/test-output/AzureCloud/OpenClaw.zip
```

对应的 manifest 目录也会保留，方便你直接检查或上传。

如果你希望部署完成后不要立刻删除资源组，以便继续做 Teams 上传和联调，把 `.env` 里的 `TEST_KEEP_RESOURCE_GROUP=1`。
这样集成测试还会额外写出：

```text
teams-app-package/test-output/AzureCloud/deployment.json
```

里面会保留本次部署的资源组名、公开 URL、bot 名称和生成包路径，便于后续自动化步骤复用。

默认输出路径：

```text
teams-app-package/dist/OpenClaw.zip
```

如果你仍然想在 Teams Developer Portal 里编辑，也建议先用这份模板生成一版，再导入或对照修改。

### E.1 E2E 测试时 `.env` 里建议补齐的字段

如果你的目标是做 Teams bot 到 OpenClaw 的端到端测试，建议在仓库根目录 `.env` 中至少准备这些值：

1. `TEST_RUN_INTEGRATION=1`
2. `TEST_GLOBAL_SUBSCRIPTION_ID`
3. `TEST_SSH_PUBLIC_KEY`
4. `TEST_AZURE_OPENAI_ENDPOINT`
5. `TEST_AZURE_OPENAI_DEPLOYMENT`
6. `TEST_AZURE_OPENAI_API_KEY`
7. `TEST_MSTEAMS_APP_ID`
8. `TEST_MSTEAMS_APP_PASSWORD`

如果你是手工在本地生成 app package，再补这些：

1. `TEST_MSTEAMS_BOT_DOMAIN`
2. `TEST_MSTEAMS_PACKAGE_ID`
3. `TEST_MSTEAMS_PACKAGE_VERSION`
4. `TEST_MSTEAMS_APP_NAME`
5. `TEST_MSTEAMS_DEVELOPER_NAME`
6. `TEST_MSTEAMS_DEVELOPER_WEBSITE_URL`
7. `TEST_MSTEAMS_PRIVACY_URL`
8. `TEST_MSTEAMS_TERMS_URL`

如果你部署完成后还想做运行态验证，也建议记录：

1. `TEST_OPENCLAW_PUBLIC_URL`
2. `TEST_OPENCLAW_GATEWAY_TOKEN`

如果你跑的是集成测试，这里的 `TEST_MSTEAMS_BOT_DOMAIN` 可以留空，由测试在部署完成后自动推导。

变量名模板见 [/.env.example](/c:/Users/hanxia/repos/openclaw-azure-deploy/.env.example)。

### F. 确认 app package/manifest 关键字段

无论你是通过 Developer Portal 还是手写 manifest，都至少要保证：

1. `bots[].botId` 必须等于 Azure Bot App ID
2. `webApplicationInfo.id` 必须等于 Azure Bot App ID
3. `bots[].scopes` 至少包含你要测试的 surface
4. `supportsFiles: true` 建议开启，便于 DM 文件场景

如果你要测 team/channel，建议同时带上 RSC 权限，例如：

1. `ChannelMessage.Read.Group`
2. `ChannelMessage.Send.Group`
3. `Member.Read.Group`
4. `Owner.Read.Group`
5. `ChannelSettings.Read.Group`
6. `TeamMember.Read.Group`
7. `TeamSettings.Read.Group`
8. `ChatMessage.Read.Chat`

### G. 上传 Teams App Package

生成 ZIP 后：

1. 打开 Teams 客户端
2. 进入 `Apps`
3. 打开 `Manage your apps`
4. 上传生成出来的 ZIP 包

也可以改走 Developer Portal 的 `Distribute` 页面上传同一个 ZIP。

上传后，至少先把 app 安装到 `Personal` 范围，再开始 DM 测试。

### H. 推荐的最小部署闭环

如果你只是为了完成最小可测闭环，按这个顺序最稳：

1. 准备 App ID 和 client secret
2. 用这两个值部署当前 ARM 模板
3. 部署完成后确认模板已创建 Azure Bot 资源
4. 检查 Messaging Endpoint 和 Teams Channel
5. 用本仓库模板生成 Teams app package
6. 在 Teams 或 Developer Portal 上传 app package
7. 在 Teams 中安装到 `Personal` scope
8. 再开始做 DM 和 pairing 测试

## 一、Azure 侧基础检查

在 Azure Portal 中检查：

1. `Microsoft.BotService/botServices` 资源已经创建。
2. Bot 的 Teams Channel 已启用。
3. Bot 的 Messaging Endpoint 指向：

```text
https://<你的域名>/api/messages
```

如果这里就不正确，后续 Teams 测试都会失败。

## 二、虚拟机运行态检查

SSH 登录虚拟机后执行：

```bash
openclaw plugins list
openclaw gateway status
sudo cat /data/openclaw.json
```

预期结果：

1. `plugins list` 中能看到 `@openclaw/msteams`
2. `gateway status` 显示服务正常
3. `/data/openclaw.json` 中存在 `msteams` 配置，且 webhook 路径为 `/api/messages`

如果失败，继续排查：

```bash
sudo systemctl status openclaw-gateway caddy --no-pager
sudo journalctl -u openclaw-gateway -n 100 --no-pager
sudo journalctl -u caddy -n 100 --no-pager
```

## 三、先做 Bot Web Chat 冒烟测试

建议先在 Azure Bot 资源中使用 `Test in Web Chat` 测一条消息。

目的：

1. 验证 Bot 到 OpenClaw webhook 的基本链路是否通
2. 避免把 Teams 客户端安装问题误判成服务端问题

如果 Web Chat 都不通，先不要继续测 Teams。

## 四、Teams DM 基础测试

在 Teams 中找到你的 bot，发起一条私聊消息。

这一步的预期要看当前 `dmPolicy`：

1. 如果是 `open`，应直接回复。
2. 如果是默认 `pairing`，第一次消息通常不会直接进入正常对话，而是生成待批准 pairing 请求。
3. 按当前已验证行为，第一次消息也可能不会把 pairing code 主动回发给 Teams 用户；这不影响后续用 SSH 手工批准。

## 五、Teams Pairing 测试

当前模板已在虚拟机中安装一个便捷命令：

```bash
openclaw-approve-teams-pairing
```

它有两种用法。

### 方式 A：自动批准最新待处理请求

```bash
openclaw-approve-teams-pairing
```

适用场景：

1. 你刚刚用 Teams 给 bot 发过第一条 DM
2. 当前只有一个最新待处理 pairing 请求
3. 这是当前推荐的手测方式；按最新验证结果，这里不需要先抄出 code

### 方式 B：显式传入 pairing code

```bash
openclaw-approve-teams-pairing <CODE>
```

适用场景：

1. 你已经拿到了明确的 pairing code
2. 你不想批准“最新请求”，而想批准特定请求

脚本内部会执行：

```bash
openclaw pairing approve msteams <code> --notify
```

注意：

1. `--notify` 目前可能打印“批准成功，但主动通知失败”的告警。
2. 这不影响 pairing 本身成功，也不影响同一用户后续第二条 DM 正常进入对话。
3. 因此人工测试时，不要把“没有收到批准通知”误判成“批准失败”。

批准成功后，让同一个 Teams 用户再发第二条私聊消息。

预期结果：

1. 第二条消息开始可以正常得到回复
2. gateway 日志中不再出现该用户被拦截为未授权 DM

如果要看待处理请求，也可以手工执行：

```bash
openclaw pairing list msteams
openclaw pairing list msteams --json
```

## 六、浏览器 Pairing 与 Teams Pairing 的区别

这两个配对不是一回事：

1. 浏览器控制台配对：

```bash
openclaw-approve-browser
```

它批准的是 Control UI 浏览器设备。

2. Teams 私聊配对：

```bash
openclaw-approve-teams-pairing
```

它批准的是 Teams DM 发送者。

不要混用这两个命令。

## 七、建议的最小验收顺序

推荐按这个顺序测试：

1. Azure Bot `Test in Web Chat`
2. Teams 私聊首条消息
3. 在虚拟机执行 `openclaw pairing list msteams --json`
4. 执行 `openclaw-approve-teams-pairing`
5. Teams 私聊第二条消息
6. 验证可持续对话

如果你想做一个最直接的命令行回归，可以在 SSH 会话里按下面顺序执行：

```bash
openclaw gateway status
openclaw pairing list msteams --json
openclaw-approve-teams-pairing
openclaw pairing list msteams --json
sudo journalctl -u openclaw-gateway -n 100 --no-pager
```

预期点：

1. 第一条消息后，第一次 `pairing list` 能看到 pending request。
2. 批准后，再次 `pairing list` 不应再包含刚才那条 pending request。
3. 日志里可能出现 notify 失败告警，但在第二条 DM 之后应能看到正常 dispatch 记录。

只有前面的链路稳定后，再继续测 group chat 或 team/channel。

## 八、常见失败原因

### 1. Bot 在 Teams 中可见，但完全不回复

常见原因：

1. Messaging Endpoint 配置错误
2. Caddy 或 gateway 未启动
3. Teams app package 没有正确安装到 personal scope
4. 首条 DM 进入了 pairing 流程，但你还没批准
5. 你只发了第一条 DM，就在等待 bot 主动把 pairing code 发回来；按当前已验证行为，这一步不稳定，应该直接去 SSH 执行 `openclaw-approve-teams-pairing`

### 2. `openclaw-approve-teams-pairing` 提示没有待处理请求

常见原因：

1. 你还没有先给 bot 发第一条私聊
2. 当前 `dmPolicy` 不是 `pairing`
3. Teams 消息根本没有打到 webhook

### 3. 浏览器能进 Dashboard，但 Teams 不通

说明：

浏览器配对通过，只能证明 Control UI 正常，不代表 Teams Bot 链路正常。

## 九、如果只想先测通链路

如果你当前目标只是“先确认 Teams 能通”，最稳妥的方法是：

1. 先测 Web Chat
2. 再测 Teams DM
3. 如果 pairing 干扰判断，可以临时把 `dmPolicy` 调整为 `open` 做联调
4. 链路确认没问题后，再切回 `pairing`

---

<a id="en"></a>
# English

This document describes how to manually validate the Microsoft Teams integration in the OpenClaw Azure deployment template.

## Scope

- Teams-related Azure resources are created by the template
- The VM has the `@openclaw/msteams` plugin installed
- OpenClaw has loaded the Teams configuration
- The Azure Bot Messaging Endpoint is reachable
- Teams direct messages work end to end
- Teams DM pairing can be approved successfully

## Prerequisites

Before testing, make sure the following are already done:

1. Deployment completed using [azuredeploy.json](/c:/Users/hanxia/repos/openclaw-azure-deploy/azuredeploy.json)
2. `msteamsAppId` and `msteamsAppPassword` were provided during deployment
3. The Teams app manifest/package has been uploaded and installed on the Teams side, with at least `personal` scope
4. You can SSH into the VM

## Verified minimal manual flow

If you want to reproduce the latest known-good manual path, use this exact order:

1. Deploy the template and record `vmPublicFqdn` and the OpenClaw public URL.
2. In the Azure Bot resource, confirm the Messaging Endpoint is `https://<your-hostname>/api/messages` and the Teams channel is enabled.
3. Generate the Teams app package with [teams-app-package/build-app-package.ps1](/c:/Users/hanxia/repos/openclaw-azure-deploy/teams-app-package/build-app-package.ps1), then upload it into Teams.
4. On the VM, run `openclaw gateway status` and confirm the gateway is healthy.
5. Send the first direct message to the bot in Teams.
6. Back on the VM, run `openclaw pairing list msteams --json` and confirm a pending pairing request exists.
7. Run `openclaw-approve-teams-pairing` directly. You do not need to pass a pairing code for the normal single-request path.
8. Return to the same Teams DM and send a second message.
9. Confirm the bot replies starting from the second message.

The currently verified behavior is:

1. Under the default `pairing` policy, the first Teams DM usually does not immediately produce a normal reply.
2. The first DM may also fail to proactively return the pairing code to the Teams user.
3. As long as the pending request exists, `openclaw-approve-teams-pairing` without arguments can approve the latest request.
4. After approval, the second DM from the same user should flow normally.
5. The approval-time proactive notify can still fail due to an upstream OpenClaw issue; that does not mean the Azure deployment is broken.

## 0. How to deploy the bot on the Teams side

If the bot has not actually been deployed into the Teams client yet, complete this section first before running the rest of the tests.

### A. Prepare the Microsoft App credentials

This template automatically creates the Azure Bot resource, so you do not need to manually create a separate Bot Service here.

However, before deployment you still need to prepare the Teams identity credentials:

1. Microsoft App ID
2. Client secret value

For this deployment template:

1. `msteamsAppId` maps to the Microsoft App ID
2. `msteamsAppPassword` maps to the client secret value
3. The tenant ID is taken from the current Azure tenant and written into OpenClaw automatically by the template

### B. Confirm the template-created Azure Bot resource exists

After deployment, confirm that the template-created Azure Bot resource exists:

1. Open the deployed `Microsoft.BotService/botServices` resource
2. Verify it exists and is healthy
3. Verify the Teams channel is present

### C. Configure the Azure Bot Messaging Endpoint

In the Azure Bot `Configuration` page, set:

```text
https://<your-hostname>/api/messages
```

The hostname should match the public DNS name or custom hostname produced by this deployment.

The template is expected to create the Bot Service and enable the Teams channel, but you should still verify this manually after deployment.

### D. Verify the Teams channel

In the Azure Bot `Channels` page:

1. Open `Microsoft Teams`
2. Verify it already exists and is enabled
3. If the portal still asks you to confirm or save, complete that step once

If the Teams channel is not enabled, the Teams client-side app will not work correctly.

### E. Generate a local Teams app package

This repository now includes a local app package template, so you do not need to hand-build the ZIP first.

Use these files directly:

1. [teams-app-package/build-app-package.ps1](/c:/Users/hanxia/repos/openclaw-azure-deploy/teams-app-package/build-app-package.ps1)
2. [teams-app-package/manifest.template.json](/c:/Users/hanxia/repos/openclaw-azure-deploy/teams-app-package/manifest.template.json)
3. [teams-app-package/README.md](/c:/Users/hanxia/repos/openclaw-azure-deploy/teams-app-package/README.md)

Minimal example:

```powershell
./teams-app-package/build-app-package.ps1 `
  -AppId "<Azure Bot App ID>" `
  -BotDomain "<your domain or Azure FQDN>"
```

The script automatically:

1. Generates `manifest.json`
2. Generates placeholder `outline.png` and `color.png`
3. Builds the final ZIP package

If your goal is import-based testing, use the default `import-test` manifest first.

It intentionally:

1. keeps only `personal` scope
2. removes `team` and `groupChat` scopes
3. removes resource-specific permissions that often force admin approval

That makes it a better fit for `Upload a custom app` testing in the Teams client.

If you need broader team/group chat features later, explicitly switch to the quickstart manifest:

```powershell
./teams-app-package/build-app-package.ps1 `
  -TemplateName quickstart `
  -AppId "<Azure Bot App ID>" `
  -BotDomain "<your domain or Azure FQDN>"
```

The broader quickstart manifest with most fields fixed:

1. App name is `OpenClaw`
2. Description and developer name are prefilled
3. In most cases you only need App ID and domain

If the repo root `.env` already follows [/.env.example](/c:/Users/hanxia/repos/openclaw-azure-deploy/.env.example), you can even run:

```powershell
./teams-app-package/build-app-package.ps1
```

The script will read these values from `.env` automatically:

1. `TEST_MSTEAMS_APP_ID`
2. `TEST_MSTEAMS_BOT_DOMAIN` or `TEST_OPENCLAW_PUBLIC_URL`
3. Optional package ID, version, and developer metadata

If you run the repository Azure integration test, `TEST_MSTEAMS_BOT_DOMAIN` does not need to be filled ahead of time.
The test derives the host from `openclawPublicUrl` after deployment and generates an import-friendly Teams app package automatically into a stable path in the repo:

```text
teams-app-package/test-output/AzureCloud/OpenClaw.zip
```

The manifest directory is also preserved for inspection.

If you want the resource group to remain available after the test so that Teams upload and live validation can continue, set `TEST_KEEP_RESOURCE_GROUP=1` in `.env`.
The integration test will also write:

```text
teams-app-package/test-output/AzureCloud/deployment.json
```

That file keeps the resource group name, public URL, bot name, and generated package paths for follow-up automation.

Default output path:

```text
teams-app-package/dist/OpenClaw.zip
```

If you still prefer Teams Developer Portal, use the generated manifest as the baseline.

### E.1 Recommended `.env` values for Teams-to-OpenClaw E2E testing

If your goal is end-to-end testing for Teams bot access into OpenClaw, the repo root `.env` should contain at least:

1. `TEST_RUN_INTEGRATION=1`
2. `TEST_GLOBAL_SUBSCRIPTION_ID`
3. `TEST_SSH_PUBLIC_KEY`
4. `TEST_AZURE_OPENAI_ENDPOINT`
5. `TEST_AZURE_OPENAI_DEPLOYMENT`
6. `TEST_AZURE_OPENAI_API_KEY`
7. `TEST_MSTEAMS_APP_ID`
8. `TEST_MSTEAMS_APP_PASSWORD`

If you generate the app package manually on your machine, add:

1. `TEST_MSTEAMS_BOT_DOMAIN`
2. `TEST_MSTEAMS_PACKAGE_ID`
3. `TEST_MSTEAMS_PACKAGE_VERSION`
4. `TEST_MSTEAMS_APP_NAME`
5. `TEST_MSTEAMS_DEVELOPER_NAME`
6. `TEST_MSTEAMS_DEVELOPER_WEBSITE_URL`
7. `TEST_MSTEAMS_PRIVACY_URL`
8. `TEST_MSTEAMS_TERMS_URL`

For post-deployment runtime checks, it is also useful to record:

1. `TEST_OPENCLAW_PUBLIC_URL`
2. `TEST_OPENCLAW_GATEWAY_TOKEN`

For integration tests, `TEST_MSTEAMS_BOT_DOMAIN` may stay empty because the test derives it from deployment output automatically.

See [/.env.example](/c:/Users/hanxia/repos/openclaw-azure-deploy/.env.example) for the variable skeleton.

### F. Verify required manifest/package fields

Whether you use Developer Portal or a hand-written manifest, verify at least:

1. `bots[].botId` matches the Azure Bot App ID
2. `webApplicationInfo.id` matches the Azure Bot App ID
3. `bots[].scopes` includes the surfaces you plan to test
4. `supportsFiles: true` is enabled if you want DM file scenarios

If you want to test team/channel flows, include RSC permissions such as:

1. `ChannelMessage.Read.Group`
2. `ChannelMessage.Send.Group`
3. `Member.Read.Group`
4. `Owner.Read.Group`
5. `ChannelSettings.Read.Group`
6. `TeamMember.Read.Group`
7. `TeamSettings.Read.Group`
8. `ChatMessage.Read.Chat`

### G. Upload the Teams app package

After the ZIP is generated:

1. Open the Teams client
2. Go to `Apps`
3. Open `Manage your apps`
4. Upload the generated ZIP package

You can also upload the same ZIP through the `Distribute` page in Teams Developer Portal.

Install it into `personal` scope first before starting DM tests.

### H. Recommended minimal deployment loop

If you want the shortest path to a testable setup, use this order:

1. Prepare the App ID and client secret
2. Deploy this ARM template with those values
3. Confirm the template-created Azure Bot resource exists
4. Verify Messaging Endpoint and Teams Channel after deployment
5. Generate the Teams app package from the template in this repo
6. Upload the app package in Teams or Developer Portal
7. Install it into `personal` scope
8. Only then start DM and pairing tests

## 1. Azure-side checks

In Azure Portal, verify:

1. The `Microsoft.BotService/botServices` resource exists
2. The Teams channel is enabled on the Bot resource
3. The Messaging Endpoint points to:

```text
https://<your-hostname>/api/messages
```

If this is wrong, the rest of the Teams test will fail.

## 2. VM runtime checks

SSH into the VM and run:

```bash
openclaw plugins list
openclaw gateway status
sudo cat /data/openclaw.json
```

Expected results:

1. `@openclaw/msteams` appears in `plugins list`
2. `gateway status` shows a healthy service
3. `/data/openclaw.json` contains `msteams` config with `/api/messages`

If not, inspect:

```bash
sudo systemctl status openclaw-gateway caddy --no-pager
sudo journalctl -u openclaw-gateway -n 100 --no-pager
sudo journalctl -u caddy -n 100 --no-pager
```

## 3. Start with Azure Web Chat smoke test

Use `Test in Web Chat` in the Azure Bot resource before testing Teams.

Purpose:

1. Validate the core Bot-to-webhook path
2. Separate server-side failures from Teams client-side setup failures

If Web Chat does not work, do not continue to Teams yet.

## 4. Basic Teams DM test

Open a direct message to the bot in Teams and send one message.

Expected behavior depends on `dmPolicy`:

1. If `open`, the bot should respond directly.
2. If the default `pairing` policy is active, the first message will usually create a pending pairing request instead of entering the normal reply flow.
3. Based on the latest verified behavior, the first message may also fail to send the pairing code back to the user proactively. This does not block manual approval from SSH.

## 5. Teams pairing test

The VM now includes a helper command:

```bash
openclaw-approve-teams-pairing
```

It supports two modes.

### Option A: approve the latest pending request automatically

```bash
openclaw-approve-teams-pairing
```

Use this when:

1. You have just sent the first Teams DM to the bot
2. There is only one latest pending pairing request
3. This is the recommended manual test path now; you do not need to copy the pairing code first

### Option B: pass the pairing code explicitly

```bash
openclaw-approve-teams-pairing <CODE>
```

Internally it runs:

```bash
openclaw pairing approve msteams <code> --notify
```

Note:

1. `--notify` can currently print a warning where approval succeeds but the proactive notification fails.
2. That does not mean the pairing approval failed.
3. For manual testing, treat the second DM after approval as the real success criterion.

After approval, send a second DM from the same Teams user.

Expected results:

1. The second message should be processed normally
2. Gateway logs should no longer show that sender as an unauthorized DM sender

You can also inspect pending requests manually:

```bash
openclaw pairing list msteams
openclaw pairing list msteams --json
```

## 6. Browser pairing vs Teams pairing

These are different:

1. Browser dashboard pairing:

```bash
openclaw-approve-browser
```

This approves the Control UI browser device.

2. Teams DM pairing:

```bash
openclaw-approve-teams-pairing
```

This approves the Teams DM sender.

Do not mix the two.

## 7. Recommended minimal acceptance flow

Use this order:

1. Azure Bot `Test in Web Chat`
2. First Teams DM
3. On the VM, run `openclaw pairing list msteams --json`
4. Run `openclaw-approve-teams-pairing`
5. Second Teams DM
6. Verify continued conversation

If you want a concise SSH-side regression sequence, run:

```bash
openclaw gateway status
openclaw pairing list msteams --json
openclaw-approve-teams-pairing
openclaw pairing list msteams --json
sudo journalctl -u openclaw-gateway -n 100 --no-pager
```

Expected checks:

1. After the first DM, the first `pairing list` should show a pending request.
2. After approval, the second `pairing list` should no longer show that pending request.
3. The logs may still contain a notify failure warning, but after the second DM you should see normal dispatch activity.

Only after this is stable should you move on to group chat or team/channel tests.

## 8. Common failure cases

### 1. Bot is visible in Teams but never replies

Common causes:

1. Messaging Endpoint is wrong
2. Caddy or gateway is not running
3. The Teams app package was not installed correctly in personal scope
4. The first DM entered pairing, but approval was never completed
5. You sent only the first DM and waited for the bot to proactively send the pairing code back; with the currently verified behavior, you should instead go to SSH and run `openclaw-approve-teams-pairing`

### 2. `openclaw-approve-teams-pairing` says no pending request exists

Common causes:

1. No first DM was sent to the bot yet
2. `dmPolicy` is not `pairing`
3. Teams messages are not reaching the webhook at all

### 3. Dashboard works, but Teams does not

This usually means the Control UI path is healthy, but the Teams Bot path is not.

## 9. If you only want to validate the path quickly

If your goal is just to prove that Teams works at all:

1. Start with Web Chat
2. Then test Teams DM
3. If pairing makes diagnosis noisy, temporarily switch `dmPolicy` to `open`
4. Once the path is confirmed, switch it back to `pairing`