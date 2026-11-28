# ============================================================
#  化工原理课设助手 · 一键安装脚本
#
#  用法（在 PowerShell 里跑）：
#    irm https://raw.githubusercontent.com/cly0301/TUSTER-help-hgyl/main/install.ps1 | iex
#
#  它会做三件事：
#    1. 下载仓库
#    2. 把 skill 装到 ~/.dsh/skills/chemeng-distillation-design
#    3. 把预设包放到 ~/.dsh/chemeng-preset
#
#  最后一步「启用预设」必须由 DSH 自己执行（见脚本末尾提示）
# ============================================================

$ErrorActionPreference = 'Stop'
$Repo = 'cly0301/TUSTER-help-hgyl'
$Branch = 'main'

Write-Host ''
Write-Host '=== 化工原理课设助手 · 安装 ===' -ForegroundColor Cyan

# ---------- 1. 下载仓库 ----------
$tmp = Join-Path $env:TEMP ('chemeng-install-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
New-Item -ItemType Directory -Force $tmp | Out-Null
$zip = Join-Path $tmp 'repo.zip'
$url = "https://github.com/$Repo/archive/refs/heads/$Branch.zip"

Write-Host "[1/3] 下载 $url" -ForegroundColor Yellow
try {
    Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
} catch {
    Write-Host "下载失败：$($_.Exception.Message)" -ForegroundColor Red
    Write-Host '请检查网络（GitHub 可能需要代理）' -ForegroundColor Red
    exit 1
}

Expand-Archive -Path $zip -DestinationPath $tmp -Force
$repoDir = Get-ChildItem $tmp -Directory | Where-Object { $_.Name -like 'TUSTER-help-hgyl-*' } | Select-Object -First 1
if (-not $repoDir) {
    # 兼容分支名不是 main 的情况
    $repoDir = Get-ChildItem $tmp -Directory | Select-Object -First 1
}
Write-Host "    解压到 $($repoDir.FullName)"

# ---------- 2. 装 skill ----------
$dshHome = Join-Path $env:USERPROFILE '.dsh'
$skillsDir = Join-Path $dshHome 'skills'
New-Item -ItemType Directory -Force $skillsDir | Out-Null
$skillDst = Join-Path $skillsDir 'chemeng-distillation-design'
if (Test-Path $skillDst) { Remove-Item -Recurse -Force $skillDst }

Write-Host "[2/3] 安装 skill 到 $skillDst" -ForegroundColor Yellow
Copy-Item -Recurse -Force (Join-Path $repoDir.FullName 'chemeng-distillation-design') $skillDst
Remove-Item -Recurse -Force (Join-Path $skillDst 'tmp_out'), (Join-Path $skillDst 'resources\__pycache__') -ErrorAction SilentlyContinue

# ---------- 3. 放预设包 ----------
$presetSrc = Join-Path $repoDir.FullName 'chemeng-preset'
$presetDst = Join-Path $dshHome 'chemeng-preset'
if (Test-Path $presetSrc) {
    if (Test-Path $presetDst) { Remove-Item -Recurse -Force $presetDst }
    Write-Host "[3/3] 放置预设包到 $presetDst" -ForegroundColor Yellow
    Copy-Item -Recurse -Force $presetSrc $presetDst
} else {
    Write-Host '[3/3] 仓库里没有 chemeng-preset，跳过（旧版 DSH 不需要）' -ForegroundColor DarkYellow
}

Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue

# ---------- 自检 ----------
$ok = Test-Path (Join-Path $skillDst 'SKILL.md')
Write-Host ''
if ($ok) {
    Write-Host 'skill 安装完成 ✔' -ForegroundColor Green
} else {
    Write-Host 'skill 安装似乎失败，请检查目录' -ForegroundColor Red
    exit 1
}

Write-Host ''
Write-Host '============================================' -ForegroundColor Cyan
Write-Host ' 最后一步：启用「化工原理课设助手」预设' -ForegroundColor Cyan
Write-Host '============================================' -ForegroundColor Cyan
Write-Host ''
Write-Host '预设不能靠脚本启用，需要 DSH 自己执行。'
Write-Host '请在 DSH 对话框里直接说这句：'
Write-Host ''
Write-Host ('  请执行 plugin_manager(action="install_bundle", target="' + $presetDst + '")') -ForegroundColor White
Write-Host ''
Write-Host '然后按 F5 刷新页面，预设选择器里就会出现「化工原理课设助手」。'
Write-Host ''
Write-Host '（0.1.x 版本的 DSH 不用最后一步，skill 已自动可用）' -ForegroundColor DarkGray
Write-Host ''
