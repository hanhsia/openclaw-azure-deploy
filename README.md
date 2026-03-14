# OpenClaw Azure One-Click Deployment

[中文](#zh-cn) | [English](#en)

Use the button below to easily deploy OpenClaw to your Azure environment.

Azure 全球用户 / Azure Global users:

[![Deploy to Azure](https://aka.ms/deploytoazurebutton)](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2Fhanhsia%2Fopenclaw-azure-deploy%2Fglobalupdate%2Fazuredeploy.json/createUIDefinitionUri/https%3A%2F%2Fraw.githubusercontent.com%2Fhanhsia%2Fopenclaw-azure-deploy%2Fglobalupdate%2FcreateUiDefinition.json)

Azure 中国区用户 / Azure China users:

[![Deploy to Azure China](https://aka.ms/deploytoazurebutton)](https://portal.azure.cn/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2Fhanhsia%2Fopenclaw-azure-deploy%2Fglobalupdate%2Fazuredeploy.json/createUIDefinitionUri/https%3A%2F%2Fraw.githubusercontent.com%2Fhanhsia%2Fopenclaw-azure-deploy%2Fglobalupdate%2FcreateUiDefinition.json)

<a id="zh-cn"></a>
# 中文部署指南

本指南将引导您完成 OpenClaw 在 Azure 上的完整部署流程。部署完成后，您将自动获得一台配置好的 Ubuntu 虚拟机、持久化数据盘、自动分配的公网域名以及安全的 HTTPS 访问。

## 1. 准备部署信息

在开始部署之前，您需要准备以下信息：

- **SSH 公钥** (SSH Public Key)：用于稍后安全登录虚拟机

如果您希望部署完成后立即接入 Azure OpenAI，还需要额外准备以下信息：

- **Azure OpenAI 终结点** (Endpoint)：例如 `https://your-resource.cognitiveservices.azure.com/`
- **模型部署名称** (Deployment Name)：您在 Azure OpenAI 中部署的模型名称，例如 `gpt-4o`
- **API 密钥** (API Key)：您的 Azure OpenAI 访问密钥

这三个 Azure OpenAI 参数要么全部填写，要么全部留空。

如果您希望部署完成后立即接入飞书（WebSocket 长连接模式），请先在飞书开放平台完成应用配置并获取以下信息：

- **Feishu App ID**：飞书开放平台中应用的 App ID，例如 `cli_xxx`
- **Feishu App Secret**：飞书开放平台中应用的 App Secret

这两个飞书参数要么全部填写，要么全部留空。

如果您希望部署完成后立即接入 Microsoft Teams（标准模式），请先准备以下信息：

- **Teams Bot App ID**：您在 Microsoft Entra / Azure Bot 中使用的应用 ID
- **Teams Bot App Password**：对应应用的客户端密钥值

Teams 标准模式当前仅支持 **Azure Global**，不支持 **Azure China**。模板会自动使用当前 Azure tenant 作为 Teams 所需的 tenant ID，因此您无需手动填写 tenant ID。

这两个 Teams 参数要么全部填写，要么全部留空。

如果你还没有 SSH 密钥对，可以参考下方操作系统的具体说明进行生成。

## 2. 一键部署流程

1. 点击上方的 **Deploy to Azure** 按钮。
2. 登录您的 Azure 账号。
3. 在部署页面中，选择或创建一个 **资源组 (Resource Group)**。
4. 填写表单中的参数：
  - `vmName`：自定义您的虚拟机名称，例如 `openclaw-prod-001`
  - `adminUsername`：SSH 登录用户名，默认值为 `azureuser`
  - `sshPublicKey`：粘贴您的 SSH **公钥** `.pub` 文件内容（非私钥）
  - `vmSize`：虚拟机规格，例如 `Standard_B2as_v2`
  - `azureOpenAiEndpoint`：可选，您的 Azure OpenAI 终结点
  - `azureOpenAiDeployment`：可选，您的模型部署名称
  - `azureOpenAiApiKey`：可选，您的 Azure OpenAI API 密钥
  - `feishuAppId`：可选，飞书应用的 App ID
  - `feishuAppSecret`：可选，飞书应用的 App Secret
  - `msteamsAppId`：可选，Microsoft Teams Bot App ID，仅支持 Azure Global
  - `msteamsAppPassword`：可选，Microsoft Teams Bot App Password，仅支持 Azure Global
  - 上述三个 Azure OpenAI 参数要么全部填写，要么全部留空
  - 上述两个飞书参数要么全部填写，要么全部留空
  - 上述两个 Teams 参数要么全部填写，要么全部留空；tenant ID 由模板自动取当前 Azure tenant
5. 点击**查看 + 创建**，然后点击**创建**提交部署。
6. 等待部署完成。请耐心等待，直到所有资源（特别是扩展 `openclaw-bootstrap`）显示部署成功。
7. 部署完成后，点击左侧的**输出 (Outputs)**，记录以下重要信息：
   - `vmPublicFqdn` (虚拟机公网域名，用于稍后 SSH 登录,你也可以查看虚拟机的的DNS 名称获得)

## 3. 连接与初始化配置

根据您的操作系统，按照以下步骤登录虚拟机并获取访问令牌。登录成功后，您可以直接在虚拟机上使用 `openclaw` 命令，例如 `openclaw status`。

### Windows 用户操作步骤

#### 准备 SSH 密钥
如果您还没有 SSH 密钥，可以先在 PowerShell 中执行以下命令生成一对新的 SSH 密钥：
```powershell
ssh-keygen -t ed25519 -C "openclaw-azure"
```

生成完成后，再运行以下命令获取公钥内容，并将其粘贴到 Azure 部署表单中：
```powershell
Get-Content $env:USERPROFILE\.ssh\id_ed25519.pub
```

#### SSH 登录虚拟机
使用您的 SSH 私钥（例如 `id_ed25519`）连接虚拟机：
```powershell
ssh -i "$env:USERPROFILE\.ssh\id_ed25519" azureuser@<vmPublicFqdn>
```
*(请将 `<vmPublicFqdn>` 替换为您在部署输出中记录的域名，如有其他私钥名称或位置请相应调整)*

#### 获取 Web 控制台地址
登录成功后，在已经 SSH 进入 Azure 虚拟机的远程终端中执行：
```bash
openclaw-browser-url
```
输出示例：
```text
Dashboard URL: https://your-hostname/#token=...
```
将完整的 URL 复制并在浏览器中打开。

#### 设备配对授权
如果浏览器页面提示 `pairing required` 或需要配对，请保持页面打开，回到 SSH 终端执行以下许可命令：
```bash
openclaw-approve-browser
```
命令执行完毕后，回到浏览器刷新页面即可完成登录。

---

### macOS / Linux 用户操作步骤

#### 准备 SSH 密钥
如果您还没有 SSH 密钥，请先运行以下命令生成一对新的 SSH 密钥：
```bash
ssh-keygen -t ed25519 -C "openclaw-azure"
```

生成完成后，再运行以下命令查看公钥并复制整行内容到 Azure 表单：
```bash
cat ~/.ssh/id_ed25519.pub
```

#### SSH 登录虚拟机
```bash
ssh -i ~/.ssh/id_ed25519 azureuser@<vmPublicFqdn>
```
*(请将 `<vmPublicFqdn>` 替换为您在部署输出中记录的域名)*

#### 获取 Web 控制台地址
登录成功后，在已经 SSH 进入 Azure 虚拟机的远程终端中执行：
```bash
openclaw-browser-url
```
将终端输出的完整 Dashboard URL 复制并在浏览器中打开。

#### 设备配对授权
如果浏览器页面提示需要配对授权，请回到 SSH 终端执行：
```bash
openclaw-approve-browser
```
然后返回浏览器刷新页面，即可正常使用 OpenClaw。

## 4. 后续升级

这个模板会在虚拟机中使用**系统 Node.js + npm 全局安装** OpenClaw，而不是使用 `/opt/openclaw` 前缀下的内置运行时安装。这样做的目的，是让后续升级路径更接近 OpenClaw 官方文档中的 global install 方式。

部署完成后，如果你需要升级 OpenClaw，建议在虚拟机中执行：

```bash
sudo npm i -g openclaw@latest
openclaw doctor
openclaw gateway restart
```

这样至少可以明确通过 npm 完成核心程序升级；相比旧的 `/opt/openclaw` 前缀安装方式，`openclaw update` 也更容易识别当前安装属于包管理器安装。

## 进阶：使用 Azure CLI 部署（替代方案）

如果您熟悉命令行操作，也可以跳过网页一键部署，直接使用 Azure CLI 完成部署。此方式适合自动化脚本或不方便使用浏览器的场景。

### 1. 登录 Azure 账号
```bash
az login
```

> **Azure 中国区用户：** 请先切换到 Azure China 环境再登录：
> ```bash
> az cloud set --name AzureChinaCloud
> az login
> ```

### 2. 创建资源组
在开始部署前，先指定一个位置（例如 `southeastasia`）来创建您的资源组：
```bash
az group create --name rg-openclaw-sea --location southeastasia
```

### 3. 执行部署命令
在此命令中直接填入您的自定义参数。部署过程可能需要几分钟。

如果您希望部署时同时配置 Azure OpenAI，请将 `azureOpenAiEndpoint`、`azureOpenAiDeployment`、`azureOpenAiApiKey` 三个参数一起填写；如果暂时不接入 Azure OpenAI，请将这三个参数一起省略。
```bash
az deployment group create \
  --name openclaw-sea-20260307 \
  --resource-group rg-openclaw-sea \
  --template-uri https://raw.githubusercontent.com/hanhsia/openclaw-azure-deploy/globalupdate/azuredeploy.json \
  --parameters \
    vmName=openclaw-sea-20260307 \
    location=southeastasia \
    adminUsername=azureuser \
    sshPublicKey="ssh-ed25519 AAAA..." \
    vmSize=Standard_B2as_v2 \
    azureOpenAiEndpoint="https://your-resource.cognitiveservices.azure.com/" \
    azureOpenAiDeployment="gpt-5.2" \
    azureOpenAiApiKey="replace-with-api-key"
```

  如果您暂时不需要 Azure OpenAI，可以直接省略这三个参数；如果需要填写，则必须三个一起填写。

### 4. 查看部署输出
部署成功后，控制台会输出大量的 JSON 信息，您可以在输出结果底部找到 `outputs` 节点，里面包含虚拟机的公网域名（`vmPublicFqdn`）。
如果您不小心清空了终端，可以随时通过以下命令再次查看部署输出：
```bash
az deployment group show \
  --name openclaw-sea-20260307 \
  --resource-group rg-openclaw-sea \
  --query properties.outputs
```
拿到公网域名后，后续的步骤与上述的【3. 连接与初始化配置】完全相同。

## 飞书配置（Azure China）

在部署表单填写 `feishuAppId` 和 `feishuAppSecret` 之前，请先在飞书开放平台完成以下设置并获取 App ID / App Secret。完成后，再把这两个值填入部署表单；模板会自动把飞书通道写入 OpenClaw 配置，并启用 WebSocket 长连接模式，无需暴露公网 webhook。

1. 创建企业自建应用，并获取 App ID / App Secret。
2. 开启机器人能力。
3. 为应用添加至少以下事件订阅：`im.message.receive_v1`。
4. 在“事件订阅”中选择“使用长连接接收事件（WebSocket）”。
5. 确保应用已经发布到可用版本。

部署完成后，可在虚拟机中检查：

```bash
openclaw gateway status
sudo cat /data/openclaw.json
```

## Microsoft Teams 配置（Azure Global）

在部署表单填写 `msteamsAppId` 和 `msteamsAppPassword` 之前，请先在 Azure Global 中完成 Azure Bot / App Registration 准备。标准模式下，模板会自动使用当前 Azure tenant 作为 Teams 所需 tenant ID，因此无需单独填写 tenant ID。

1. 在 Azure Global 中创建 Azure Bot，并准备 Bot 使用的 App ID / App Password。
2. 在部署表单中填写 `msteamsAppId` 和 `msteamsAppPassword`。
3. 模板会自动：
  - 创建 Azure Bot 资源并启用 Teams channel
  - 将 Teams 通道配置写入 OpenClaw
  - 通过 Caddy 暴露 `https://<你的域名>/api/messages`
4. 部署完成后，您仍需在 Teams 侧单独完成 Teams app manifest/package 的上传与安装。

部署完成后，可在虚拟机中检查：

```bash
openclaw plugins list
openclaw gateway status
sudo cat /data/openclaw.json
```

如果你要继续做 Teams 手工联调和验收，参考 [tests/TEAMS_TESTING.md](/c:/Users/hanxia/repos/openclaw-azure-deploy/tests/TEAMS_TESTING.md)。文档里已经包含当前已验证的最小手测闭环，以及 `openclaw-approve-teams-pairing` 无参批准的操作方式。

## 常见问题

### 1. SSH 报错 `Permission denied (publickey)`
**原因：** 您使用的私钥与提供给 Azure 的公钥不匹配，或者您没有使用 `-i` 参数指定正确的私钥路径。  
**解决办法：** 
- 确保部署时粘贴的公钥内容（`.pub`）与您当前使用的私钥是一对。
- 如果您在 Azure 门户下载了 `.pem` 文件，登录时请通过 `-i` 参数明确指定：
  ```bash
  ssh -i <你的私钥文件路径.pem> azureuser@<vmPublicFqdn>
  ```

### 2. SSH 报错 `UNPROTECTED PRIVATE KEY FILE` 或者 `Permissions 0644 for ... are too open`
**原因：** 您的私钥文件权限过于宽松，SSH 客户端出于安全考虑拒绝使用它。  
**解决办法：**  
- **Windows 用户：** 在 PowerShell 中执行以下命令（假设您的私钥名为 `openclaw-key.pem`）：
  ```powershell
  $Key = "$env:USERPROFILE\.ssh\openclaw-key.pem"
  icacls $Key /inheritance:r
  icacls $Key /remove:g "Users" "Authenticated Users" "Everyone" "BUILTIN\Administrators"
  icacls $Key /grant:r "${env:USERNAME}:R"
  ```
- **Mac / Linux 用户：** 在终端中执行以下命令限制权限：
  ```bash
  chmod 600 ~/.ssh/openclaw-key.pem
  ```

### 3. SSH 报错 `REMOTE HOST IDENTIFICATION HAS CHANGED!`
**原因：** 您当前连接的域名在本机 `known_hosts` 中已经保存过旧的主机指纹，但这台虚拟机可能已经被删除重建、重新部署过系统，或者同一个域名现在指向了另一台机器，因此 SSH 发现远端主机密钥发生了变化。  
**解决办法：**  
- 如果这台虚拟机确实是您刚刚重新部署或重建的，可以先删除本机保存的旧记录，再重新连接：
  ```powershell
  ssh-keygen -R <vmPublicFqdn>
  ssh -i "$env:USERPROFILE\.ssh\id_ed25519" azureuser@<vmPublicFqdn>
  ```
- 第一次重新连接时，SSH 会提示您确认新的主机指纹，确认无误后输入 `yes` 即可。
- 如果这台机器并不是您刚刚重建的，请不要直接忽略该警告，而应先确认域名和公网 IP 是否仍然对应您自己的虚拟机。

### 4. 如何找到 `gateway token`（网关令牌）缺少的提示？
**原因：** OpenClaw 面板采用了基于 Token 的安全验证，不允许直接通过裸域名访问，直接输入 URL 时会被拒绝。  
**解决办法：**  
切勿手动猜测或输入 Token。请 SSH 登录进虚拟机，在远程终端中直接运行：
```bash
openclaw-browser-url
```
它会直接输出完整的 `https://.../#token=...` 链接，复制整段带有 token 的 URL 在浏览器中打开即可。

### 5. 浏览器显示 `pairing required`（需要设备配对）
**原因：** 为了安全限制，您的浏览器设备作为一个新的客户端首次连接网关时，需要进行管理员授权。  
**解决办法：**  
保持该浏览器页面不要关闭，此时切回虚拟机的 SSH 终端，执行以下命令进行授权：
```bash
openclaw-approve-browser
```
命令执行完毕后，回到浏览器刷新页面即可直接进入面板。

### 6. 浏览器访问报错 `502 Bad Gateway`
**原因：** 部署尚未完全结束，或者宿主机上的 OpenClaw Gateway / Caddy 服务未成功启动，或正在重启中。  
**解决办法：**  
1. 刚刚部署完毕时，请等待 1-2 分钟让组件完全启动。
2. 如果持续报错，请登录至虚拟机排查服务状态：
  ```bash
  # 查看 OpenClaw 和 Caddy 服务状态
  sudo systemctl status openclaw-gateway caddy --no-pager

  # 查看 OpenClaw Gateway 的最近日志
  sudo journalctl -u openclaw-gateway -n 100 --no-pager

  # 查看 Caddy 的最近日志
  sudo journalctl -u caddy -n 100 --no-pager
  ```

### 7. 无法连接虚拟机（Connection Timed Out）
**原因：** 虚拟机实例没有成功获取公网 IP，或者其 22 / 443 端口被安全组（NSG）阻挡。  
**解决办法：**  
- 在 Azure 门户中前往您刚刚部署的**虚拟机**页面。
- 检查处于 `Running(正在运行)` 状态，并且确认分配到了 Public IP。
- 点击左侧的**网络 (Networking)**，确保入站端口规则 (Inbound port rules) 允许了 `22` (SSH) 和 `443` (HTTPS) 端口。

---

<a id="en"></a>
# English Deployment Guide

This guide walks you through the full OpenClaw deployment process on Azure. After deployment finishes, you will have a configured Ubuntu virtual machine, a persistent data disk, an automatically assigned public domain name, and HTTPS access.

## 1. Prepare Deployment Information

Before you begin, prepare the following:

- **SSH Public Key**: used to log in to the virtual machine later

If you want Azure OpenAI configured during deployment, also prepare the following:

- **Azure OpenAI Endpoint**: for example `https://your-resource.cognitiveservices.azure.com/`
- **Deployment Name**: the model deployment name in Azure OpenAI, for example `gpt-4o`
- **API Key**: your Azure OpenAI access key

These three Azure OpenAI parameters must either all be provided or all be left empty.

If you want Feishu connected during deployment with the WebSocket long-connection mode, first finish the Feishu Open Platform app setup and obtain the following:

- **Feishu App ID**: the Feishu app App ID, for example `cli_xxx`
- **Feishu App Secret**: the Feishu app App Secret

These two Feishu parameters must either both be provided or both be left empty.

If you want Microsoft Teams connected during deployment in standard mode, prepare the following:

- **Teams Bot App ID**: the application ID used by your Microsoft Entra / Azure Bot registration
- **Teams Bot App Password**: the client secret value for that application

Teams standard mode currently supports **Azure Global only** and does not support **Azure China**. The template automatically uses the current Azure tenant as the tenant ID required by Teams, so you do not need to enter a tenant ID manually.

These two Teams parameters must either both be provided or both be left empty.

If you do not have an SSH key pair yet, you can generate one by following the operating-system-specific instructions below.

## 2. One-Click Deployment Workflow

1. Click the **Deploy to Azure** button above.
2. Sign in to your Azure account.
3. On the deployment page, select or create a **Resource Group**.
4. Fill in the deployment parameters:
   - `vmName`: your custom virtual machine name, for example `openclaw-prod-001`
   - `adminUsername`: SSH login username, default is `azureuser`
   - `sshPublicKey`: paste the content of your SSH **public key** `.pub` file, not the private key
   - `vmSize`: virtual machine size, for example `Standard_B2as_v2`
   - `azureOpenAiEndpoint`: optional, your Azure OpenAI endpoint
   - `azureOpenAiDeployment`: optional, your Azure OpenAI deployment name
   - `azureOpenAiApiKey`: optional, your Azure OpenAI API key
   - `feishuAppId`: optional, your Feishu app App ID
   - `feishuAppSecret`: optional, your Feishu app App Secret
   - `msteamsAppId`: optional, your Microsoft Teams Bot App ID, Azure Global only
   - `msteamsAppPassword`: optional, your Microsoft Teams Bot App Password, Azure Global only
   - The three Azure OpenAI parameters above must either all be provided or all be left empty
   - The two Feishu parameters above must either both be provided or both be left empty
   - The two Teams parameters above must either both be provided or both be left empty; the tenant ID is automatically taken from the current Azure tenant
5. Click **Review + create**, then click **Create** to submit the deployment.
6. Wait for deployment to finish. In particular, wait until all resources, especially the `openclaw-bootstrap` extension, show as successfully deployed.
7. After deployment finishes, open **Outputs** on the left and record the following:
   - `vmPublicFqdn` (the public VM domain name used later for SSH login)

## 3. Connect and Complete Initial Setup

Depending on your operating system, follow the steps below to log in to the virtual machine and obtain the access token. After you sign in, you can use the `openclaw` command directly on the VM, for example `openclaw status`.

### Windows

#### Prepare SSH keys
If you do not have SSH keys yet, run the following command in PowerShell to generate a new key pair:
```powershell
ssh-keygen -t ed25519 -C "openclaw-azure"
```

After the key pair is created, run the following command to print the public key, then paste it into the Azure deployment form:
```powershell
Get-Content $env:USERPROFILE\.ssh\id_ed25519.pub
```

#### SSH into the virtual machine
Use your SSH private key, for example `id_ed25519`, to connect to the VM:
```powershell
ssh -i "$env:USERPROFILE\.ssh\id_ed25519" azureuser@<vmPublicFqdn>
```
*(Replace `<vmPublicFqdn>` with the domain name shown in the deployment outputs. Adjust the key path or file name if needed.)*

#### Get the web dashboard URL
After you log in successfully, run this in the remote shell on the Azure virtual machine, not in your local repo terminal:
```bash
openclaw-browser-url
```
Example output:
```text
Dashboard URL: https://your-hostname/#token=...
```
Copy the full URL and open it in your browser.

#### Authorize browser pairing
If the browser page shows `pairing required`, keep the page open, return to your SSH terminal, and run:
```bash
openclaw-approve-browser
```
After the command finishes, refresh the browser page to complete sign-in.

---

### macOS / Linux

#### Prepare SSH keys
If you do not have SSH keys yet, first run the following command to generate a new key pair:
```bash
ssh-keygen -t ed25519 -C "openclaw-azure"
```

After that, run the following command to print the public key, then paste the full line into the Azure form:
```bash
cat ~/.ssh/id_ed25519.pub
```

#### SSH into the virtual machine
```bash
ssh -i ~/.ssh/id_ed25519 azureuser@<vmPublicFqdn>
```
*(Replace `<vmPublicFqdn>` with the domain name shown in the deployment outputs.)*

#### Get the web dashboard URL
After you log in successfully, run this in the remote shell on the Azure virtual machine, not in your local repo terminal:
```bash
openclaw-browser-url
```
Copy the full Dashboard URL from the terminal output and open it in your browser.

#### Authorize browser pairing
If the browser page asks for pairing approval, run:
```bash
openclaw-approve-browser
```
Then return to the browser and refresh the page to start using OpenClaw.

## 4. Updating Later

This template installs OpenClaw with **system Node.js + global npm install** on the VM instead of using the older `/opt/openclaw` prefixed runtime layout. That keeps the deployment closer to OpenClaw's documented global-install upgrade path.

After deployment, when you want to upgrade OpenClaw on the VM, run:

```bash
sudo npm i -g openclaw@latest
openclaw doctor
openclaw gateway restart
```

This gives you an explicit npm-based core upgrade path, and it also makes `openclaw update` more likely to recognize the install as a package-manager install.

## Advanced: Deploy with Azure CLI (Alternative)

If you prefer the command line, you can skip the web-based one-click deployment and deploy directly with Azure CLI. This is useful for automation or when using a browser is inconvenient.

### 1. Sign in to Azure
```bash
az login
```

> **Azure China users:** Switch to the Azure China environment before signing in:
> ```bash
> az cloud set --name AzureChinaCloud
> az login
> ```

### 2. Create a resource group
Before deployment, choose a location such as `southeastasia` and create a resource group:
```bash
az group create --name rg-openclaw-sea --location southeastasia
```

### 3. Run the deployment command
Fill in your custom parameters directly in the command below. Deployment may take a few minutes.

If you want Azure OpenAI configured during deployment, provide `azureOpenAiEndpoint`, `azureOpenAiDeployment`, and `azureOpenAiApiKey` together. If you do not want Azure OpenAI configured yet, omit all three together.
```bash
az deployment group create \
  --name openclaw-sea-20260307 \
  --resource-group rg-openclaw-sea \
  --template-uri https://raw.githubusercontent.com/hanhsia/openclaw-azure-deploy/globalupdate/azuredeploy.json \
  --parameters \
    vmName=openclaw-sea-20260307 \
    location=southeastasia \
    adminUsername=azureuser \
    sshPublicKey="ssh-ed25519 AAAA..." \
    vmSize=Standard_B2as_v2 \
    azureOpenAiEndpoint="https://your-resource.cognitiveservices.azure.com/" \
    azureOpenAiDeployment="gpt-5.2" \
    azureOpenAiApiKey="replace-with-api-key"
```

### 4. View deployment outputs
After the deployment succeeds, the console prints a large JSON object. In the `outputs` section near the bottom, you can find the VM public domain name `vmPublicFqdn`.
If you cleared the terminal, you can retrieve the deployment outputs again with:
```bash
az deployment group show \
  --name openclaw-sea-20260307 \
  --resource-group rg-openclaw-sea \
  --query properties.outputs
```
After you obtain the public domain name, the remaining steps are the same as in **3. Connect and Complete Initial Setup** above.

## Feishu Setup (Azure China)

Before you enter `feishuAppId` and `feishuAppSecret` in the deployment form, complete the following Feishu Open Platform setup and obtain the App ID and App Secret. After that, enter those two values in the form; the template writes the Feishu channel configuration into OpenClaw automatically and uses the WebSocket long-connection mode, so no public webhook is required.

1. Create a self-built enterprise app and copy the App ID and App Secret.
2. Enable the bot capability.
3. Add at least the `im.message.receive_v1` event subscription.
4. In Event Subscription, choose the WebSocket long-connection mode.
5. Publish the app version.

After deployment, you can verify the channel on the VM:

```bash
openclaw gateway status
sudo cat /data/openclaw.json
```

## Microsoft Teams Setup (Azure Global)

Before you enter `msteamsAppId` and `msteamsAppPassword` in the deployment form, prepare your Azure Bot / App Registration in Azure Global first. In standard mode, the template automatically uses the current Azure tenant as the tenant ID required by Teams, so you do not need to enter a tenant ID separately.

1. Create an Azure Bot in Azure Global and prepare the Bot App ID / App Password.
2. Enter `msteamsAppId` and `msteamsAppPassword` in the deployment form.
3. The template automatically:
  - creates the Azure Bot resource and enables the Teams channel
  - writes the Teams channel configuration into OpenClaw
  - exposes `https://<your-hostname>/api/messages` through Caddy
4. After deployment, you still need to upload and install the Teams app manifest/package on the Teams side.

After deployment, you can verify the setup on the VM:

```bash
openclaw plugins list
openclaw gateway status
sudo cat /data/openclaw.json
```

If you want to continue with manual Teams validation after deployment, see [tests/TEAMS_TESTING.md](/c:/Users/hanxia/repos/openclaw-azure-deploy/tests/TEAMS_TESTING.md). It includes the currently verified minimal manual flow and the no-argument approval path for `openclaw-approve-teams-pairing`.

## FAQ

### 1. SSH reports `Permission denied (publickey)`
**Cause:** The private key you are using does not match the public key you provided to Azure, or you did not use `-i` to point to the correct private key file.  
**Resolution:**
- Make sure the public key content you pasted during deployment matches the private key you are using now.
- If you downloaded a `.pem` file from Azure portal, specify it explicitly when connecting:
  ```bash
  ssh -i <path-to-your-private-key.pem> azureuser@<vmPublicFqdn>
  ```

### 2. SSH reports `UNPROTECTED PRIVATE KEY FILE` or `Permissions 0644 for ... are too open`
**Cause:** Your private key file permissions are too broad, so the SSH client refuses to use it for security reasons.  
**Resolution:**
- **Windows:** Run the following commands in PowerShell, assuming the private key file is named `openclaw-key.pem`:
  ```powershell
  $Key = "$env:USERPROFILE\.ssh\openclaw-key.pem"
  icacls $Key /inheritance:r
  icacls $Key /remove:g "Users" "Authenticated Users" "Everyone" "BUILTIN\Administrators"
  icacls $Key /grant:r "${env:USERNAME}:R"
  ```
- **Mac / Linux:** Restrict permissions in the terminal:
  ```bash
  chmod 600 ~/.ssh/openclaw-key.pem
  ```

### 3. SSH reports `REMOTE HOST IDENTIFICATION HAS CHANGED!`
**Cause:** Your local `known_hosts` file already contains an older host fingerprint for this domain name, but the virtual machine may have been deleted and recreated, reprovisioned, or the same domain name may now point to a different machine. SSH therefore detects that the remote host key has changed.  
**Resolution:**
- If this is a virtual machine you just redeployed or recreated, remove the old local record and connect again:
  ```powershell
  ssh-keygen -R <vmPublicFqdn>
  ssh -i "$env:USERPROFILE\.ssh\id_ed25519" azureuser@<vmPublicFqdn>
  ```
- On the next connection, SSH will ask you to confirm the new host fingerprint. If you have verified that this is your newly deployed VM, enter `yes`.
- If the virtual machine was not just rebuilt by you, do not ignore the warning immediately. First verify that the domain name and public IP still belong to your own VM.

### 4. How do I handle a missing `gateway token` prompt?
**Cause:** OpenClaw uses token-based authentication for the dashboard. Accessing only the bare domain name is rejected.  
**Resolution:**
Do not guess or type the token manually. SSH into the virtual machine and run this in the remote shell:
```bash
openclaw-browser-url
```
The command prints the complete `https://.../#token=...` URL. Copy the full URL, including the token, into your browser.

### 5. The browser shows `pairing required`
**Cause:** For security reasons, a browser connecting as a new client to the gateway must be approved by an administrator.  
**Resolution:**
Keep the browser page open, switch back to the SSH terminal on the virtual machine, and run:
```bash
openclaw-approve-browser
```
After the command finishes, refresh the browser page to enter the dashboard.

### 6. The browser shows `502 Bad Gateway`
**Cause:** Deployment may not be fully finished yet, or the host-level OpenClaw Gateway or Caddy service may have failed to start or may still be restarting.  
**Resolution:**
1. If deployment just finished, wait 1 to 2 minutes and let all components start completely.
2. If the issue persists, SSH into the virtual machine and inspect the service status:
  ```bash
  # Check the OpenClaw and Caddy service status
  sudo systemctl status openclaw-gateway caddy --no-pager

  # Inspect recent OpenClaw Gateway logs
  sudo journalctl -u openclaw-gateway -n 100 --no-pager

  # Inspect recent Caddy logs
  sudo journalctl -u caddy -n 100 --no-pager
  ```

### 7. I cannot connect to the virtual machine (`Connection Timed Out`)
**Cause:** The virtual machine may not have received a public IP successfully, or ports 22 and 443 may be blocked by the Network Security Group (NSG).  
**Resolution:**
- In Azure portal, open the **Virtual Machine** page for the deployment you just created.
- Confirm it is in the `Running` state and that it has a Public IP assigned.
- Open **Networking** on the left and make sure the inbound port rules allow `22` (SSH) and `443` (HTTPS).
