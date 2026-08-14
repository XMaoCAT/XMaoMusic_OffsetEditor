$ErrorActionPreference = "Stop"
$depsDir = Join-Path $PSScriptRoot "_deps"
if (!(Test-Path $depsDir)) {
    New-Item -ItemType Directory -Path $depsDir | Out-Null
}
python -m pip install -r (Join-Path $PSScriptRoot "requirements.txt") --target $depsDir
Write-Host "依赖已安装到: $depsDir"
