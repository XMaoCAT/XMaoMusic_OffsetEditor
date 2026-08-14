[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Python = if (Test-Path -LiteralPath $VenvPython) { $VenvPython } else { "python" }
$WorkRoot = Join-Path $PSScriptRoot "build"
$DistRoot = Join-Path $WorkRoot "dist"

Write-Host "[Core0] Checking PyInstaller from Tsinghua mirror (progress is shown when needed)..." -ForegroundColor Cyan
$ErrorActionPreference = "Continue"
& $Python -m pip install --progress-bar on -i https://pypi.tuna.tsinghua.edu.cn/simple pyinstaller==6.16.0
$InstallExitCode = $LASTEXITCODE
if ($InstallExitCode -ne 0) {
    Write-Host "[Core0] China mirror unavailable; trying official PyPI..." -ForegroundColor Yellow
    & $Python -m pip install --progress-bar on pyinstaller==6.16.0
    $InstallExitCode = $LASTEXITCODE
}
$ErrorActionPreference = "Stop"
if ($InstallExitCode -ne 0) { throw "PyInstaller installation failed." }

New-Item -ItemType Directory -Force -Path $WorkRoot, $DistRoot | Out-Null
Write-Host "[Core0] Building headless ncm-core.exe..." -ForegroundColor Cyan
& $Python -m PyInstaller --noconfirm --clean --onefile --console `
    --name ncm-core `
    --paths $ProjectRoot `
    --distpath $DistRoot `
    --workpath (Join-Path $WorkRoot "work") `
    --specpath $WorkRoot `
    (Join-Path $PSScriptRoot "ncm_cli.py")
if ($LASTEXITCODE -ne 0) { throw "Core0 build failed." }

Copy-Item -Force -LiteralPath (Join-Path $DistRoot "ncm-core.exe") -Destination (Join-Path $PSScriptRoot "ncm-core.exe")
Write-Host "[Core0] Ready: $PSScriptRoot\ncm-core.exe" -ForegroundColor Green
