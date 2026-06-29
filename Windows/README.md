# Windows 部署脚本

本目录提供在 Windows 系统上一键部署 Claude Code 环境的 PowerShell 脚本。

## 快速开始（Quick Start）

```
# 如需代理请在 github 的 http 前面追加 https://gh-proxy.org/https://raw.git...
irm https://raw.githubusercontent.com/AuditAIH/audit-tool-skills/main/Windows/install_Claude_code.ps1 | iex
```

> 脚本检测到非管理员运行时会自动提权（UAC 弹窗需点击「是」）；若 UAC 被拒绝则无法继续。

## 脚本说明

### install_Claude_code.ps1

一键部署脚本，依次完成以下工作：

1. **设置执行策略** — 配置当前用户和进程的 PowerShell 执行策略（容错处理，已设置或无权限均不报错）。
2. **自动提权** — 检测到非管理员运行时，自动以管理员身份重新启动脚本（支持在线 `irm | iex` 和离线文件两种方式）。
3. **配置 NPM 环境变量** — 将 `%APPDATA%\npm` 永久添加到用户 PATH。
4. **安装 Node.js** — 通过 `winget` 安装 Node.js LTS（已安装则跳过）。
5. **安装 Git** — 通过 `winget` 安装 Git（已安装则跳过）。
6. **安装 Claude Code** — 配置 npmmirror 镜像源后，通过 `npm install -g @anthropic-ai/claude-code` 全局安装。
7. **生成配置文件** — 在 `%USERPROFILE%\.claude\settings.json` 写入 API Token 与模型配置（已存在则跳过）。

## 使用方法

### 方式一：在线执行（推荐）

以管理员身份打开 PowerShell，执行（见上方「快速开始」）：

```powershell
irm https://raw.githubusercontent.com/AuditAIH/audit-tool-skills/main/Windows/install_Claude_code.ps1 | iex
```

### 方式二：离线执行

1. 下载 `install_Claude_code.ps1` 到本地：

```powershell
irm https://raw.githubusercontent.com/AuditAIH/audit-tool-skills/main/Windows/install_Claude_code.ps1 -OutFile install_Claude_code.ps1
```

2. 右键 PowerShell →「以管理员身份运行」。
3. 执行脚本：

```powershell
.\install_Claude_code.ps1
```

> 说明：脚本检测到非管理员运行时会自动提权，无需手动以管理员启动；但若 UAC 弹窗被拒绝则无法继续。

## 前置要求

- Windows 10 / 11
- PowerShell 5.1 或更高版本
- 可用的网络连接（用于 `winget` 和 `npm` 安装）

## 配置说明

脚本会在首次运行时生成 `%USERPROFILE%\.claude\settings.json`，需要输入 `ANTHROPIC_AUTH_TOKEN`。默认配置使用：

- `ANTHROPIC_BASE_URL`: `https://ark.cn-beijing.volces.com/api/coding`
- `ANTHROPIC_MODEL`: `deepseek-v4-pro`

如需更换模型或服务地址，可在脚本生成配置后手动编辑该文件。

## 注意事项

- 脚本会修改用户级 PATH 环境变量（永久生效）。
- `winget` 安装可能需要较长时间，请耐心等待。
- 若 Node.js 或 Git 安装后仍提示未找到，请关闭并重新打开 PowerShell 以刷新环境变量。
