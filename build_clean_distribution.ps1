[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$DistributionName = "Releases"
$DistributionRoot = Join-Path $ProjectRoot $DistributionName
$WindowsRoot = Join-Path $DistributionRoot "Windows"
$MacRoot = Join-Path $DistributionRoot "Mac"

function Copy-RequiredFile {
    param(
        [Parameter(Mandatory)] [string] $Source,
        [Parameter(Mandatory)] [string] $Destination
    )
    if (-not (Test-Path -LiteralPath $Source -PathType Leaf)) {
        throw "Required file is missing: $Source"
    }
    $parent = Split-Path -Parent $Destination
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    Copy-Item -LiteralPath $Source -Destination $Destination -Force
}

function Copy-CommonProject {
    param([Parameter(Mandatory)] [string] $TargetRoot)

    $commonFiles = @(
        "app.py",
        "audio_core.py",
        "desktop_app.py",
        "ncm_core.py",
        "requirements.txt",
        "README.md",
        "PLATFORMS.md",
        "PRODUCT.md",
        "DESIGN.md",
        "THIRD_PARTY_NOTICES.md"
    )
    foreach ($name in $commonFiles) {
        Copy-RequiredFile (Join-Path $ProjectRoot $name) (Join-Path $TargetRoot $name)
    }

    $uiTarget = Join-Path $TargetRoot "ui"
    New-Item -ItemType Directory -Force -Path $uiTarget | Out-Null
    foreach ($name in @("index.html", "styles.css", "app.js", "fluid.js")) {
        Copy-RequiredFile (Join-Path $ProjectRoot "ui\$name") (Join-Path $uiTarget $name)
    }
}

if (Test-Path -LiteralPath $DistributionRoot) {
    $resolvedRoot = [System.IO.Path]::GetFullPath($DistributionRoot)
    $expectedRoot = [System.IO.Path]::GetFullPath((Join-Path $ProjectRoot $DistributionName))
    if ($resolvedRoot -ne $expectedRoot -or (Split-Path -Leaf $resolvedRoot) -ne $DistributionName) {
        throw "Refusing to replace an unexpected distribution path: $resolvedRoot"
    }
    Remove-Item -LiteralPath $resolvedRoot -Recurse -Force
}

New-Item -ItemType Directory -Force -Path $WindowsRoot, $MacRoot | Out-Null
Copy-CommonProject $WindowsRoot
Copy-CommonProject $MacRoot

foreach ($name in @("Start.bat", "bootstrap.ps1", "install_deps.ps1")) {
    Copy-RequiredFile (Join-Path $ProjectRoot $name) (Join-Path $WindowsRoot $name)
}
foreach ($name in @("ncm_cli.py", "ncm-core.exe", "build_windows.ps1", "README.md")) {
    Copy-RequiredFile (Join-Path $ProjectRoot "Core0\$name") (Join-Path $WindowsRoot "Core0\$name")
}

foreach ($name in @("Start.command", "bootstrap_macos.sh", "build_dmg.sh", "XMaoMusic-macos.spec")) {
    Copy-RequiredFile (Join-Path $ProjectRoot "Mac\$name") (Join-Path $MacRoot $name)
}
Copy-RequiredFile (Join-Path $ProjectRoot "Mac\README.md") (Join-Path $MacRoot "README-macOS.md")
foreach ($name in @("ncm_cli.py", "README.md")) {
    Copy-RequiredFile (Join-Path $ProjectRoot "Core0\$name") (Join-Path $MacRoot "Core0\$name")
}

$forbiddenNames = @(".venv", ".runtime", "Output", "output", "__pycache__", "build", "dist", "qa")
$forbidden = Get-ChildItem -LiteralPath $DistributionRoot -Force -Recurse | Where-Object {
    $_.Name -in $forbiddenNames -or $_.Extension -in @(".pyc", ".log")
}
if ($forbidden) {
    throw "Clean distribution contains forbidden runtime artifacts: $($forbidden.FullName -join ', ')"
}

$windowsCount = (Get-ChildItem -LiteralPath $WindowsRoot -File -Recurse).Count
$macCount = (Get-ChildItem -LiteralPath $MacRoot -File -Recurse).Count
Write-Host "Clean distributions are ready." -ForegroundColor Green
Write-Host "Windows: $WindowsRoot ($windowsCount files)"
Write-Host "Mac:     $MacRoot ($macCount files)"
