# OpenClaw Azure One-Click Deployment

[中文](#zh-cn) | [English](#en)

Azure 全球用户 / Azure Global users:

[![Deploy to Azure](https://aka.ms/deploytoazurebutton)](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2Fhanhsia%2Fopenclaw-azure-deploy%2Fmain%2Fazuredeploy.json/createUIDefinitionUri/https%3A%2F%2Fraw.githubusercontent.com%2Fhanhsia%2Fopenclaw-azure-deploy%2Fmain%2FcreateUiDefinition.json)

Azure 中国区用户 / Azure China users:

[![Deploy to Azure China](https://aka.ms/deploytoazurebutton)](https://portal.azure.cn/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2Fhanhsia%2Fopenclaw-azure-deploy%2Fmain%2Fazuredeploy.json/createUIDefinitionUri/https%3A%2F%2Fraw.githubusercontent.com%2Fhanhsia%2Fopenclaw-azure-deploy%2Fmain%2FcreateUiDefinition.json)

---

<a id="zh-cn"></a>
# 中文部署指南

## 1. 准备 SSH 密钥

如果您已有 SSH 密钥对，可以跳过此步骤。

**Windows（PowerShell）：**
```powershell
ssh-keygen -t ed25519 -C "openclaw-azure"
Get-Content $env:USERPROFILE\.ssh\id_ed25519.pub
```

**macOS / Linux：**
```bash
ssh-keygen -t ed25519 -C "openclaw-azure"
cat ~/.ssh/id_ed25519.pub
```

复制输出的公钥内容，稍后粘贴到部署表单中。

## 2. （可选）准备 Azure OpenAI 信息

如果您希望部署后立即使用 Azure OpenAI，请根据认证方式准备以下信息：

| 参数 | API Key 模式 | Managed Identity 模式（推荐） |
|------|------------|--------------------------|
| Azure OpenAI 终结点 | 必填 | 必填 |
| 模型部署名称 | 必填 | 必填 |
| API 密钥 | 必填 | 无需 |
| Azure OpenAI 资源组名称 | 无需 | 跨资源组时填写 |

Managed Identity 模式下，模板会自动尝试为 VM 分配 `Cognitive Services OpenAI User` 角色。如果部署用户权限不足，角色分配会失败，但 VM 和 OpenClaw 仍然正常部署完成（Azure 门户可能显示"部分失败"）。用户只需后续手动补上角色即可，不需要重新部署（详见第 5 步）。

> **Azure China 用户注意：** Azure China 环境不提供 Azure OpenAI 资源，因此 Managed Identity 模式在 Azure China 中不可用。Azure China 用户请选择 API Key 模式或跳过 Azure OpenAI 配置。

不需要 Azure OpenAI 则全部留空。

## 3.（可选）准备通道集成信息

**飞书（Azure China / Azure Global 均可）：** 在飞书开放平台创建企业自建应用，开启机器人能力，添加 `im.message.receive_v1` 事件订阅并选择 WebSocket 长连接模式，发布应用后获取：
- **Feishu App ID** 和 **Feishu App Secret**（两个参数要么全填，要么全部留空）

**Microsoft Teams（Azure China / Azure Global 均可）：**

1. 在 Azure 门户中，进入 **Microsoft Entra ID** → **应用注册** → **新注册**：
   - 名称：任意（如 `openclaw-teams-bot`）
   - 受支持的帐户类型：选择**仅此组织目录中的帐户（单租户）**
   - 重定向 URI：留空
   - 点击**注册**
2. 注册完成后，记录**应用程序(客户端) ID** — 即 **Teams Bot App ID**。
3. 进入**证书和密码** → **新客户端密码**，添加密码并记录密码值 — 即 **Teams Bot App Password**。

部署时提供以上两个参数（要么全填，要么全部留空）。模板会自动创建 Azure Bot Service 并关联 Teams Channel，无需手动配置。模板自动使用当前 Azure tenant 作为 Teams tenant ID，无需手动填写。

## 4. 部署到 Azure

### 方式 A：一键部署（推荐）

1. 点击上方的 **Deploy to Azure** 按钮，登录 Azure 账号。
2. 选择或创建一个**资源组 (Resource Group)**。
3. 填写表单参数：
   - `vmName`：虚拟机名称
   - `adminUsername`：SSH 用户名（默认 `azureuser`）
   - `sshPublicKey`：粘贴第 1 步获得的 SSH 公钥内容
   - `vmSize`：虚拟机规格（默认 `Standard_B2as_v2`）
   - Azure OpenAI 相关参数（可选，见第 2 步）
   - 飞书 / Teams 通道参数（可选，见第 3 步）
4. 点击**查看 + 创建** → **创建**，等待部署完成。
5. 部署完成后，点击左侧**输出 (Outputs)**，记录：
   - `vmPublicFqdn`：虚拟机公网域名（用于 SSH 登录）
   - `vmPrincipalId`：VM 托管标识 ID（Managed Identity 模式需要）

### 方式 B：Azure CLI 部署

```bash
# Azure 中国区用户先执行: az cloud set --name AzureChinaCloud
az login

az group create --name rg-openclaw --location southeastasia

# API Key 模式
az deployment group create \
  --name openclaw-deploy \
  --resource-group rg-openclaw \
  --template-uri https://raw.githubusercontent.com/hanhsia/openclaw-azure-deploy/main/azuredeploy.json \
  --parameters \
    vmName=my-openclaw \
    sshPublicKey="ssh-ed25519 AAAA..." \
    azureOpenAiAuthMode=key \
    azureOpenAiEndpoint="https://your-resource.cognitiveservices.azure.com/" \
    azureOpenAiDeployment="gpt-5.2" \
    azureOpenAiApiKey="your-api-key"

# Managed Identity 模式（推荐）：省略 azureOpenAiApiKey，改 azureOpenAiAuthMode=managedIdentity
# 不接入 Azure OpenAI：省略所有 azureOpenAi* 参数
```

查看部署输出：
```bash
az deployment group show \
  --name openclaw-deploy \
  --resource-group rg-openclaw \
  --query properties.outputs
```

## 5.（Managed Identity 模式）部署后分配角色

如果您选择了 Managed Identity 认证模式，模板会**自动尝试**为 VM 的托管标识分配 `Cognitive Services OpenAI User` 角色。

- **权限充足时（Owner / User Access Administrator）：** 角色自动分配成功，无需额外操作。
- **权限不足时（如 Contributor）：** 角色分配会失败，Azure 门户可能显示部署为"部分失败"。但 **VM 和 OpenClaw 仍会正常完成部署**，不需要重新部署。您只需手动补上角色，下一次 chat 请求即可正常工作。

部署输出中的 `azureOpenAiRoleAssignmentHint` 包含可直接复制执行的完整 `az role assignment create` 命令。

**通过 Azure 门户分配：**
1. 打开 Azure OpenAI 资源 → **访问控制 (IAM)** → **添加角色分配**。
2. 角色选 **Cognitive Services OpenAI User**，成员选**托管标识**，搜索并选择您的虚拟机。
3. **审查 + 分配**。

**通过 Azure CLI 分配：**
```bash
vm_principal_id=$(az deployment group show \
  --name <deployment-name> \
  --resource-group <resource-group> \
  --query properties.outputs.vmPrincipalId.value -o tsv)

az role assignment create \
  --assignee "$vm_principal_id" \
  --role "Cognitive Services OpenAI User" \
  --scope "/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.CognitiveServices/accounts/<openai-resource-name>"
```

> 执行此命令的用户需要 Owner、User Access Administrator 或 Role Based Access Control Administrator 角色。角色分配生效后，下一次 chat 请求即可正常工作。

## 6. SSH 登录虚拟机

**Windows（PowerShell）：**
```powershell
ssh -i "$env:USERPROFILE\.ssh\id_ed25519" azureuser@<vmPublicFqdn>
```

**macOS / Linux：**
```bash
ssh -i ~/.ssh/id_ed25519 azureuser@<vmPublicFqdn>
```

将 `<vmPublicFqdn>` 替换为部署输出中的域名。

## 7. 获取 Web 控制台地址并打开浏览器

SSH 登录虚拟机后，执行：
```bash
openclaw-browser-url
```

输出示例：
```
Dashboard URL: https://your-hostname/#token=...
```

将完整 URL 复制到浏览器中打开。

## 8. 浏览器配对授权

如果浏览器页面提示 `pairing required`，**保持页面打开**，回到 SSH 终端执行：
```bash
openclaw-approve-browser
```

该 helper 会先尝试 OpenClaw CLI 的 pairing RPC 路径；如果当前上游版本在这台主机上拒绝 `device.pair.*`，则自动回退到 `openclaw devices list/approve` 并批准最新的 Control UI 请求。如果提示没有待处理的配对请求，请保持浏览器停留在配对页面，等待几秒后重试。命令执行完毕后，回到浏览器刷新页面即可。

> OpenClaw 上游 `2026.3.12` 到 `2026.3.13` 期间存在已知的 loopback WebSocket 握手回归。`openclaw-approve-browser` 不依赖内部 dist 结构，会优先尝试官方 `openclaw gateway call device.pair.*` CLI 路径，并在需要时自动回退到 `openclaw devices list/approve`。

## 9.（可选）Teams 部署后配置

如果部署时填写了 Teams 参数，模板已自动创建 Azure Bot Service。部署完成后，需要生成 Teams 应用包并上传到 Teams：

1. 在本地 PowerShell 中运行（需要先 clone 本仓库）：
   ```powershell
   ./teams-app-package/build-app-package.ps1 `
     -AppId "<Teams Bot App ID>" `
     -BotDomain "<vmPublicFqdn>"
   ```
   将 `<Teams Bot App ID>` 替换为第 3 步获取的应用 ID，`<vmPublicFqdn>` 替换为部署输出中的域名。脚本生成的 zip 文件位于 `teams-app-package/dist/` 目录。

2. 打开 Microsoft Teams → 左侧**应用** → **管理你的应用** → **上传自定义应用**，选择生成的 zip 文件上传。

3. 上传成功后，向 Bot 发送一条私聊消息。Bot 会返回一个配对码（pairing code）。

4. SSH 登录 VM，执行以下命令完成配对：
   ```bash
   openclaw-approve-teams-pairing
   ```
   该 helper 会自动获取最新的 Teams 配对请求并批准。也可以手动传入配对码：
   ```bash
   openclaw-approve-teams-pairing <pairing-code>
   ```

配对完成后即可在 Teams 中正常与 Bot 对话。

## 10. （可选）后续升级

本模板使用官方 `install-cli.sh` 安装器将 CLI 和专用 Node 运行时装到用户的 `~/.openclaw` 前缀下，再通过 `openclaw onboard --non-interactive --install-daemon` 完成 gateway 安装，最后通过 `openclaw config` 写入 Azure 传入的配置。

```bash
openclaw update
openclaw doctor
openclaw gateway restart
```

如果启用了 Teams，升级后可能需要补装扩展依赖：
```bash
export PATH="$HOME/.openclaw/tools/node/bin:$HOME/.openclaw/bin:$PATH"
npm install --omit=dev --prefix "$HOME/.openclaw/lib/node_modules/openclaw/extensions/msteams"
systemctl --user restart openclaw-gateway
```

如需完全重跑安装器：
```bash
curl -fsSL https://openclaw.ai/install-cli.sh | bash -s -- --prefix "$HOME/.openclaw" --node-version 24.14.0 --no-onboard
bash -c '. /etc/openclaw/openclaw.env && openclaw onboard --non-interactive --accept-risk --mode local --workspace /data/workspace --auth-choice skip --gateway-port "$OPENCLAW_GATEWAY_PORT" --gateway-bind loopback --gateway-auth token --gateway-token "$OPENCLAW_GATEWAY_TOKEN" --install-daemon --daemon-runtime node --skip-channels --skip-skills'
bash -c '. /etc/openclaw/openclaw.env && openclaw config validate'
openclaw doctor
openclaw gateway restart
```

## 11.（可选）切换 Gateway 模式

SSH 管理员默认走本机 loopback gateway。如需切到公网 `wss://` gateway 排查问题：
```bash
openclaw-use-public-gateway
```
该 helper 会按这台 VM 的 current local device identity 去匹配并自动批准对应的 pending request，然后用 `openclaw health --verbose` 验证公网路径可用后才持久化切换。

切回默认 loopback：
```bash
openclaw-use-loopback-gateway
```

切换后需 reconnect SSH，运行以下命令确认：
```bash
openclaw-gateway-mode current
```

## 常见问题

**SSH 报错 `Permission denied (publickey)`**
> 私钥与部署时使用的公钥不匹配。确保使用 `-i` 指定正确的私钥文件。

**SSH 报错 `UNPROTECTED PRIVATE KEY FILE`**
> 私钥文件权限过宽。Windows 执行 `icacls $Key /inheritance:r` 等命令修复；macOS/Linux 执行 `chmod 600 <私钥文件>`。

**SSH 报错 `REMOTE HOST IDENTIFICATION HAS CHANGED!`**
> VM 重建导致主机指纹变化。执行 `ssh-keygen -R <vmPublicFqdn>` 后重新连接。

**浏览器报错 `502 Bad Gateway`**
> 部署刚完成时，请等待 1-2 分钟。如持续报错，SSH 登录 VM 执行：
> ```bash
> sudo systemctl status openclaw-gateway caddy --no-pager
> sudo journalctl -u openclaw-gateway -n 100 --no-pager
> ```

**无法连接虚拟机（Connection Timed Out）**
> 在 Azure 门户确认 VM 处于 Running 状态、已分配公网 IP，且 NSG 允许 22 和 443 端口入站。

> **环境说明：** 模板会为管理员用户预装 Homebrew 到 `/home/linuxbrew/.linuxbrew` 并配置 passwordless sudo。VM 作为管理员专用主机使用。

---

<a id="en"></a>
# English Deployment Guide

## 1. Prepare SSH Keys

Skip this step if you already have an SSH key pair.

**Windows (PowerShell):**
```powershell
ssh-keygen -t ed25519 -C "openclaw-azure"
Get-Content $env:USERPROFILE\.ssh\id_ed25519.pub
```

**macOS / Linux:**
```bash
ssh-keygen -t ed25519 -C "openclaw-azure"
cat ~/.ssh/id_ed25519.pub
```

Copy the public key output — you will paste it into the deployment form later.

## 2. (Optional) Prepare Azure OpenAI Information

If you want Azure OpenAI ready immediately after deployment, prepare the following based on your chosen authentication mode:

| Parameter | API Key Mode | Managed Identity Mode (Recommended) |
|-----------|-------------|-------------------------------------|
| Azure OpenAI Endpoint | Required | Required |
| Deployment Name | Required | Required |
| API Key | Required | Not needed |
| Azure OpenAI Resource Group | Not needed | When cross-resource-group |

In Managed Identity mode, the template automatically attempts to assign the `Cognitive Services OpenAI User` role to the VM. If the deploying user lacks sufficient permissions, the role assignment fails but the VM and OpenClaw are fully deployed and functional (the Azure portal may show the deployment as "partially failed"). Just assign the role manually afterward — no redeployment needed (see Step 5).

> **Azure China users:** Azure OpenAI is not available in Azure China, so Managed Identity mode cannot be used. Please choose API Key mode or skip Azure OpenAI configuration.

Leave all Azure OpenAI fields empty to skip.

## 3. (Optional) Prepare Channel Integration Information

**Feishu (Azure China / Azure Global):** Create a self-built enterprise app on the Feishu Open Platform, enable bot capability, add the `im.message.receive_v1` event subscription with WebSocket long-connection mode, publish the app, then obtain:
- **Feishu App ID** and **Feishu App Secret** (provide both or leave both empty)

**Microsoft Teams (Azure China / Azure Global):**

1. In the Azure portal, go to **Microsoft Entra ID** → **App registrations** → **New registration**:
   - Name: any name (e.g. `openclaw-teams-bot`)
   - Supported account types: **Accounts in this organizational directory only (Single tenant)**
   - Redirect URI: leave blank
   - Click **Register**
2. After registration, note the **Application (client) ID** — this is the **Teams Bot App ID**.
3. Go to **Certificates & secrets** → **New client secret**, add a secret and note the secret value — this is the **Teams Bot App Password**.

Provide both parameters during deployment (or leave both empty). The template automatically creates the Azure Bot Service and connects the Teams Channel — no manual configuration needed. The template also uses the current Azure tenant as the Teams tenant ID.

## 4. Deploy to Azure

### Option A: One-Click Deployment (Recommended)

1. Click a **Deploy to Azure** button above and sign in.
2. Select or create a **Resource Group**.
3. Fill in the form parameters:
   - `vmName`: virtual machine name
   - `adminUsername`: SSH username (default `azureuser`)
   - `sshPublicKey`: paste the SSH public key from Step 1
   - `vmSize`: virtual machine size (default `Standard_B2as_v2`)
   - Azure OpenAI parameters (optional, see Step 2)
   - Feishu / Teams channel parameters (optional, see Step 3)
4. Click **Review + create** → **Create** and wait for deployment to finish.
5. After deployment, open **Outputs** on the left and note:
   - `vmPublicFqdn`: public domain name (for SSH login)
   - `vmPrincipalId`: VM managed identity ID (needed for Managed Identity mode)

### Option B: Azure CLI Deployment

```bash
# Azure China users first run: az cloud set --name AzureChinaCloud
az login

az group create --name rg-openclaw --location southeastasia

# API Key mode
az deployment group create \
  --name openclaw-deploy \
  --resource-group rg-openclaw \
  --template-uri https://raw.githubusercontent.com/hanhsia/openclaw-azure-deploy/main/azuredeploy.json \
  --parameters \
    vmName=my-openclaw \
    sshPublicKey="ssh-ed25519 AAAA..." \
    azureOpenAiAuthMode=key \
    azureOpenAiEndpoint="https://your-resource.cognitiveservices.azure.com/" \
    azureOpenAiDeployment="gpt-5.2" \
    azureOpenAiApiKey="your-api-key"

# Managed Identity mode (recommended): omit azureOpenAiApiKey, set azureOpenAiAuthMode=managedIdentity
# Skip Azure OpenAI: omit all azureOpenAi* parameters
```

View deployment outputs:
```bash
az deployment group show \
  --name openclaw-deploy \
  --resource-group rg-openclaw \
  --query properties.outputs
```

## 5. (Managed Identity Mode) Post-Deployment Role Assignment

If you chose Managed Identity authentication, the template **automatically attempts** to assign the `Cognitive Services OpenAI User` role to the VM's managed identity.

- **When permissions are sufficient (Owner / User Access Administrator):** The role is assigned automatically. No further action needed.
- **When permissions are insufficient (e.g. Contributor):** The role assignment fails, and the Azure portal may show the deployment as "partially failed". However, **the VM and OpenClaw are still fully deployed** — no redeployment is needed. Just assign the role manually, and the next chat request will work immediately.

The deployment output `azureOpenAiRoleAssignmentHint` contains the exact `az role assignment create` command you can copy and run.

**Via Azure Portal:**
1. Open your Azure OpenAI resource → **Access control (IAM)** → **Add role assignment**.
2. Select role **Cognitive Services OpenAI User**, choose **Managed identity**, search for your VM.
3. **Review + assign**.

**Via Azure CLI:**
```bash
vm_principal_id=$(az deployment group show \
  --name <deployment-name> \
  --resource-group <resource-group> \
  --query properties.outputs.vmPrincipalId.value -o tsv)

az role assignment create \
  --assignee "$vm_principal_id" \
  --role "Cognitive Services OpenAI User" \
  --scope "/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.CognitiveServices/accounts/<openai-resource-name>"
```

> The user running this command needs the Owner, User Access Administrator, or Role Based Access Control Administrator role. Once the role is assigned, the next chat request will work immediately.

## 6. SSH into the Virtual Machine

**Windows (PowerShell):**
```powershell
ssh -i "$env:USERPROFILE\.ssh\id_ed25519" azureuser@<vmPublicFqdn>
```

**macOS / Linux:**
```bash
ssh -i ~/.ssh/id_ed25519 azureuser@<vmPublicFqdn>
```

Replace `<vmPublicFqdn>` with the domain name from the deployment outputs.

## 7. Get the Web Dashboard URL

After SSH login, run:
```bash
openclaw-browser-url
```

Example output:
```
Dashboard URL: https://your-hostname/#token=...
```

Copy the full URL and open it in your browser.

## 8. Authorize Browser Pairing

If the browser shows `pairing required`, **keep the page open**, return to SSH and run:
```bash
openclaw-approve-browser
```

This helper tries the OpenClaw CLI pairing RPC first and falls back to the devices CLI when the current upstream build rejects `device.pair.*` on this host. It then approves the newest Control UI request. If it reports no pending request, keep the browser on the pairing page, wait a few seconds, and retry. After the command succeeds, refresh the browser page.

> Known upstream note: OpenClaw `2026.3.12` through `2026.3.13` has a reported loopback WebSocket handshake regression on some hosts. The `openclaw-approve-browser` helper does not depend on internal dist module structure; it prefers the official `openclaw gateway call device.pair.*` path and falls back to `openclaw devices list/approve` when needed.

## 9. (Optional) Post-Deployment Teams Setup

If you provided Teams parameters during deployment, the template has already created the Azure Bot Service. After deployment, you need to generate a Teams app package and upload it to Teams:

1. Run the following in PowerShell locally (clone this repository first):
   ```powershell
   ./teams-app-package/build-app-package.ps1 `
     -AppId "<Teams Bot App ID>" `
     -BotDomain "<vmPublicFqdn>"
   ```
   Replace `<Teams Bot App ID>` with the app ID from Step 3, and `<vmPublicFqdn>` with the domain from deployment outputs. The generated zip file is in `teams-app-package/dist/`.

2. Open Microsoft Teams → **Apps** on the left → **Manage your apps** → **Upload a custom app**, and upload the generated zip file.

3. After upload, send a direct message to the bot. The bot will return a pairing code.

4. SSH into the VM and run:
   ```bash
   openclaw-approve-teams-pairing
   ```
   This helper automatically finds the latest Teams pairing request and approves it. You can also pass the pairing code manually:
   ```bash
   openclaw-approve-teams-pairing <pairing-code>
   ```

After pairing, you can chat with the bot in Teams normally.

## 10. (Optional) Updating Later

This template uses the official `install-cli.sh` installer to place the CLI and its dedicated Node runtime under the user's `~/.openclaw` prefix, then runs `openclaw onboard --non-interactive --install-daemon` to install the gateway service, and finally applies Azure-provided settings through `openclaw config`.

```bash
openclaw update
openclaw doctor
openclaw gateway restart
```

If Teams is enabled, you may need to reinstall extension dependencies after updating:
```bash
export PATH="$HOME/.openclaw/tools/node/bin:$HOME/.openclaw/bin:$PATH"
npm install --omit=dev --prefix "$HOME/.openclaw/lib/node_modules/openclaw/extensions/msteams"
systemctl --user restart openclaw-gateway
```

To rerun the installer from scratch:
```bash
curl -fsSL https://openclaw.ai/install-cli.sh | bash -s -- --prefix "$HOME/.openclaw" --node-version 24.14.0 --no-onboard
bash -c '. /etc/openclaw/openclaw.env && openclaw onboard --non-interactive --accept-risk --mode local --workspace /data/workspace --auth-choice skip --gateway-port "$OPENCLAW_GATEWAY_PORT" --gateway-bind loopback --gateway-auth token --gateway-token "$OPENCLAW_GATEWAY_TOKEN" --install-daemon --daemon-runtime node --skip-channels --skip-skills'
bash -c '. /etc/openclaw/openclaw.env && openclaw config validate'
openclaw doctor
openclaw gateway restart
```

## 11. (Optional) Switch Gateway Mode

The SSH admin shell uses the local loopback gateway by default. To switch to the public `wss://` gateway for troubleshooting:
```bash
openclaw-use-public-gateway
```
This helper matches the pending request for this VM's current local device identity, automatically approves it, validates the public path with `openclaw health --verbose`, and only then persists the switch.

Switch back to the default loopback:
```bash
openclaw-use-loopback-gateway
```

Reconnect SSH after switching and confirm with:
```bash
openclaw-gateway-mode current
```

## FAQ

**SSH reports `Permission denied (publickey)`**
> The private key does not match the public key used during deployment. Use `-i` to specify the correct private key file.

**SSH reports `UNPROTECTED PRIVATE KEY FILE`**
> Private key file permissions are too broad. On Windows, run `icacls $Key /inheritance:r` and related commands; on macOS/Linux, run `chmod 600 <key-file>`.

**SSH reports `REMOTE HOST IDENTIFICATION HAS CHANGED!`**
> The VM was recreated and the host fingerprint changed. Run `ssh-keygen -R <vmPublicFqdn>` then reconnect.

**Browser shows `502 Bad Gateway`**
> Wait 1-2 minutes after deployment finishes. If it persists, SSH into the VM and check:
> ```bash
> sudo systemctl status openclaw-gateway caddy --no-pager
> sudo journalctl -u openclaw-gateway -n 100 --no-pager
> ```

**Cannot connect to the VM (`Connection Timed Out`)**
> In Azure portal, confirm the VM is Running with a public IP, and NSG allows inbound ports 22 and 443.
