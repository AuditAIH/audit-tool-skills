<#
.SYNOPSIS
    一键部署：Node → Git → Claude Code
    支持 irm | iex 在线提权（模仿 get.activated.win）
#>

& {
    # ========== 执行策略设置（容错不报错） ==========
    # 作用：确保当前用户和进程可以运行 PowerShell 脚本
    # 原因：npm 等工具需要执行 ps1 脚本，Windows 默认可能禁止
    # 容错：使用 -ErrorAction SilentlyContinue 和 try-catch，即使已设置或无权限也不会报错
    try {
        # 设置当前用户的执行策略为 RemoteSigned（允许运行本地脚本，远程脚本需要签名）
        # 永久生效，只影响当前用户
        Set-ExecutionPolicy RemoteSigned -Scope CurrentUser -Force -ErrorAction SilentlyContinue
        
        # 设置当前进程的执行策略为 Unrestricted（允许运行所有脚本）
        # 仅当前进程有效，关闭 PowerShell 后失效
        Set-ExecutionPolicy Unrestricted -Scope Process -Force -ErrorAction SilentlyContinue
    }
    catch {
        # 静默处理异常，不中断脚本执行
        # 即使已经设置过或无权限，也不会报错
    }
    
    # ============ 1. 检查是否管理员 ============
    $isAdmin = [bool]([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    
    if (-not $isAdmin) {
        Write-Host ""
        Write-Host "[INFO] Not running as admin, requesting elevation..." -ForegroundColor Yellow
        
        # 获取当前脚本内容（支持在线和离线）
        $scriptContent = $null
        
        # 方法1：从文件执行时获取（离线执行）
        $scriptPath = $MyInvocation.MyCommand.Path
        if (-not $scriptPath) { $scriptPath = $PSCommandPath }
        if ($scriptPath -and (Test-Path $scriptPath)) {
            $scriptContent = Get-Content -Path $scriptPath -Raw -Encoding UTF8
        }
        
        # 方法2：在线执行时，从调用行中解析 URL（不依赖历史命令）
        # 原理：irm URL | iex 时，$MyInvocation.Line 包含完整的调用命令
        if (-not $scriptContent) {
            $line = $MyInvocation.Line
            if ($line -match '(?:irm|Invoke-RestMethod)\s+(\S+)') {
                $url = $matches[1]
                Write-Host "[INFO] Detected online execution, downloading from: $url" -ForegroundColor Gray
                try {
                    $scriptContent = Invoke-RestMethod -Uri $url
                } catch {
                    Write-Host "[ERROR] Failed to download script: $_" -ForegroundColor Red
                    return
                }
            }
        }
        
        # 方法3：如果还是获取不到，提示用户
        if (-not $scriptContent) {
            Write-Host "[ERROR] Cannot get script content for elevation." -ForegroundColor Red
            Write-Host "Please use one of these methods:" -ForegroundColor Yellow
            Write-Host "  1. Download and run: irm URL -OutFile temp.ps1; .\temp.ps1" -ForegroundColor Gray
            Write-Host "  2. Or run as admin: Right-click PowerShell -> Run as administrator" -ForegroundColor Gray
            return
        }
        
        # 写到临时文件
        $rand = [Guid]::NewGuid().Guid
        $tempFile = Join-Path $env:TEMP "install_claude_$rand.ps1"
        [System.IO.File]::WriteAllText($tempFile, $scriptContent, [System.Text.Encoding]::UTF8)
        
        Write-Host "[INFO] Temp file: $tempFile" -ForegroundColor Gray
        Write-Host "[INFO] Launching elevated PowerShell..." -ForegroundColor Yellow
        
        # 以管理员身份运行
        try {
            $process = Start-Process powershell.exe `
                -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$tempFile`"" `
                -Verb RunAs `
                -PassThru
            
            # 等待完成
            $process.WaitForExit()
            
            # 清理临时文件
            if (Test-Path $tempFile) {
                Remove-Item -Path $tempFile -Force
            }
            
            Write-Host "[DONE] Elevated process completed." -ForegroundColor Green
        } catch {
            Write-Host "[ERROR] Failed to elevate: $_" -ForegroundColor Red
        }
        
        return
    }
    
    # ============ 2. 已经是管理员，开始执行 ============
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  Running as Administrator" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    
    # 永久添加 NPM 到用户环境变量
    Write-Host ""
    Write-Host "===== Setting NPM Environment Variable =====" -ForegroundColor Cyan
    $npmPath = Join-Path $env:APPDATA "npm"
    Write-Host "  NPM path: $npmPath" -ForegroundColor Gray
    
    $userPath = [Environment]::GetEnvironmentVariable("PATH", "User")
    if ($userPath -notlike "*$npmPath*") {
        $newPath = "$userPath;$npmPath"
        [Environment]::SetEnvironmentVariable("PATH", $newPath, "User")
        Write-Host "  [OK] Added NPM to User PATH permanently" -ForegroundColor Green
    } else {
        Write-Host "  [OK] NPM already in User PATH" -ForegroundColor Green
    }
    
    # 刷新当前进程环境变量
    function Refresh-Path {
        $machinePath = [Environment]::GetEnvironmentVariable("PATH", "Machine")
        $userPathNew = [Environment]::GetEnvironmentVariable("PATH", "User")
        $env:PATH = "$machinePath;$userPathNew"
    }
    Refresh-Path
    
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  Deploy: Node -> Git -> Claude Code" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    
    # ============ 3. 安装 Node.js ============
    Write-Host ""
    Write-Host "[1/3] Checking Node.js ..." -ForegroundColor Yellow
    $nodeCmd = Get-Command node -ErrorAction SilentlyContinue
    if ($nodeCmd) {
        $nodeVer = & node --version 2>$null
        Write-Host "  [OK] Node.js installed: $nodeVer" -ForegroundColor Green
    } else {
        Write-Host "  [..] Installing Node.js LTS ..." -ForegroundColor Yellow
        try {
            winget install --id OpenJS.NodeJS.LTS -e --accept-source-agreements --accept-package-agreements --silent
            Refresh-Path
            $nodeCmd2 = Get-Command node -ErrorAction SilentlyContinue
            if ($nodeCmd2) {
                Write-Host "  [OK] Node.js installed: $(& node --version)" -ForegroundColor Green
            } else {
                Write-Host "  [FAIL] Node.js not found after install" -ForegroundColor Red
            }
        } catch {
            Write-Host "  [FAIL] Install error: $_" -ForegroundColor Red
        }
    }
    
    # ============ 4. 安装 Git ============
    Write-Host ""
    Write-Host "[2/3] Checking Git ..." -ForegroundColor Yellow
    $gitCmd = Get-Command git -ErrorAction SilentlyContinue
    if ($gitCmd) {
        $gitVer = & git --version 2>$null
        Write-Host "  [OK] Git installed: $gitVer" -ForegroundColor Green
    } else {
        Write-Host "  [..] Installing Git ..." -ForegroundColor Yellow
        try {
            winget install --id Git.Git -e --accept-source-agreements --accept-package-agreements --silent
            Refresh-Path
            Write-Host "  [OK] Git installed" -ForegroundColor Green
        } catch {
            Write-Host "  [FAIL] Install error: $_" -ForegroundColor Red
        }
    }
    
    # ============ 5. 安装 Claude Code ============
    Write-Host ""
    Write-Host "[3/3] Checking Claude Code ..." -ForegroundColor Yellow
    $claudeCmd = Get-Command claude -ErrorAction SilentlyContinue
    if ($claudeCmd) {
        Write-Host "  [OK] Claude Code installed" -ForegroundColor Green
    } else {
        $npmCmd = Get-Command npm -ErrorAction SilentlyContinue
        if (-not $npmCmd) {
            Write-Host "  [FAIL] npm not found" -ForegroundColor Red
        } else {
            Write-Host "  [..] Setting npm mirror and installing Claude Code ..." -ForegroundColor Yellow
            try {
                & npm config set registry https://registry.npmmirror.com
                & npm install -g @anthropic-ai/claude-code
                Refresh-Path
                $claudeCmd2 = Get-Command claude -ErrorAction SilentlyContinue
                if ($claudeCmd2) {
                    Write-Host "  [OK] Claude Code installed" -ForegroundColor Green
                } else {
                    Write-Host "  [WARN] Install done but claude not found" -ForegroundColor Yellow
                }
            } catch {
                Write-Host "  [FAIL] Install error: $_" -ForegroundColor Red
            }
        }
    }
    
    # ============ 6. 生成配置文件 ============
    Write-Host ""
    Write-Host "===== Config file check =====" -ForegroundColor Cyan
    $configDir = Join-Path $env:USERPROFILE ".claude"
    $configFile = Join-Path $configDir "settings.json"
    
    if (Test-Path $configFile) {
        Write-Host "  [OK] Config file exists: $configFile" -ForegroundColor Green
    } else {
        Write-Host "  [WARN] Config file not found, creating..." -ForegroundColor Yellow
        $apiKey = Read-Host "  Please paste your ANTHROPIC_AUTH_TOKEN"
        
        $jsonLines = @(
            '{'
            '    "env": {'
            "        `"ANTHROPIC_AUTH_TOKEN`": `"$apiKey`","
            '        "ANTHROPIC_BASE_URL": "https://ark.cn-beijing.volces.com/api/coding",'
            '        "ANTHROPIC_MODEL": "deepseek-v4-pro",'
            '        "ANTHROPIC_DEFAULT_HAIKU_MODEL": "deepseek-v4-pro",'
            '        "ANTHROPIC_DEFAULT_SONNET_MODEL": "deepseek-v4-pro",'
            '        "ANTHROPIC_DEFAULT_OPUS_MODEL": "deepseek-v4-pro",'
            '        "CLAUDE_CODE_SUBAGENT_MODEL": "deepseek-v4-pro"'
            '    },'
            '    "permissions": {'
            '        "defaultMode": "auto"'
            '    }'
            '}'
        )
        $jsonContent = $jsonLines -join "`r`n"
        
        if (-not (Test-Path $configDir)) {
            New-Item -ItemType Directory -Path $configDir -Force | Out-Null
        }
        [System.IO.File]::WriteAllText($configFile, $jsonContent, [System.Text.Encoding]::UTF8)
        Write-Host "  [OK] Config file created: $configFile" -ForegroundColor Green
    }
    
    # ============ 7. 完成 ============
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "  [DONE] Deploy completed!" -ForegroundColor Green
    Write-Host "  NPM PATH: $npmPath" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    Write-Host ""
    Read-Host "Press Enter to exit"
    
} @args
