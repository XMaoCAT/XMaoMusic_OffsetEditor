$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0

# Bootstrap contract: Windows x64, project-local dependencies, visible download
# progress, China mirrors first, and official sources only as fallbacks.
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$AppPath = Join-Path $ProjectRoot "app.py"
$RequirementsPath = Join-Path $ProjectRoot "requirements.txt"
$VenvDir = Join-Path $ProjectRoot ".venv"
$RuntimeDir = Join-Path $ProjectRoot ".runtime"
$PortablePythonDir = Join-Path $RuntimeDir "python"
$PythonVersion = "3.12.10"
$PythonInstallerName = "python-$PythonVersion-amd64.exe"
$PythonInstallerSha256 = "67b5635e80ea51072b87941312d00ec8927c4db9ba18938f7ad2d27b328b95fb"

[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Add-Type -AssemblyName System.Net.Http

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Format-ByteSize {
    param([long]$Bytes)
    if ($Bytes -ge 1GB) { return "{0:N2} GB" -f ($Bytes / 1GB) }
    if ($Bytes -ge 1MB) { return "{0:N2} MB" -f ($Bytes / 1MB) }
    if ($Bytes -ge 1KB) { return "{0:N2} KB" -f ($Bytes / 1KB) }
    return "$Bytes B"
}

function Get-Sha256 {
    param([string]$Path)

    $stream = [System.IO.File]::OpenRead($Path)
    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = $sha256.ComputeHash($stream)
        return ([System.BitConverter]::ToString($bytes)).Replace("-", "").ToLowerInvariant()
    }
    finally {
        $sha256.Dispose()
        $stream.Dispose()
    }
}

function Download-FileWithProgress {
    param(
        [string[]]$Urls,
        [string]$Destination,
        [string]$DisplayName,
        [string]$ExpectedSha256 = ""
    )

    $parent = Split-Path -Parent $Destination
    if (-not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }

    $partial = "$Destination.part"
    $failures = New-Object System.Collections.Generic.List[string]
    $attempts = New-Object System.Collections.Generic.List[object]
    foreach ($useProxy in @($true, $false)) {
        foreach ($url in $Urls) {
            $attempts.Add([PSCustomObject]@{ Url = $url; UseProxy = $useProxy })
        }
    }

    foreach ($attempt in $attempts) {
        $url = $attempt.Url
        $route = if ($attempt.UseProxy) { "system network settings" } else { "direct connection" }
        if (Test-Path -LiteralPath $partial) {
            Remove-Item -LiteralPath $partial -Force
        }

        Write-Host "Trying ($route): $url"
        $client = $null
        $response = $null
        $sourceStream = $null
        $targetStream = $null

        try {
            $handler = New-Object System.Net.Http.HttpClientHandler
            $handler.AllowAutoRedirect = $true
            $handler.UseProxy = $attempt.UseProxy
            $client = New-Object System.Net.Http.HttpClient($handler)
            $client.Timeout = [TimeSpan]::FromMinutes(30)
            $client.DefaultRequestHeaders.UserAgent.ParseAdd("XMaoMusic-OffsetEditor-Bootstrap/1.0")

            $completion = [System.Net.Http.HttpCompletionOption]::ResponseHeadersRead
            $response = $client.GetAsync($url, $completion).GetAwaiter().GetResult()
            $response.EnsureSuccessStatusCode()

            $total = $response.Content.Headers.ContentLength
            $sourceStream = $response.Content.ReadAsStreamAsync().GetAwaiter().GetResult()
            $targetStream = New-Object System.IO.FileStream(
                $partial,
                [System.IO.FileMode]::Create,
                [System.IO.FileAccess]::Write,
                [System.IO.FileShare]::None,
                1048576,
                [System.IO.FileOptions]::SequentialScan
            )

            $buffer = New-Object byte[] 1048576
            [long]$received = 0
            $timer = [System.Diagnostics.Stopwatch]::StartNew()
            $lastUpdate = [TimeSpan]::Zero

            while (($read = $sourceStream.Read($buffer, 0, $buffer.Length)) -gt 0) {
                $targetStream.Write($buffer, 0, $read)
                $received += $read

                if (($timer.Elapsed - $lastUpdate).TotalMilliseconds -ge 150) {
                    $seconds = [Math]::Max(0.1, $timer.Elapsed.TotalSeconds)
                    $speed = Format-ByteSize ([long]($received / $seconds))
                    if ($total -and $total -gt 0) {
                        $percent = [Math]::Min(100, [int](($received * 100) / $total))
                        $status = "{0} / {1}  {2}%  {3}/s" -f `
                            (Format-ByteSize $received), (Format-ByteSize $total), $percent, $speed
                        Write-Progress -Activity "Downloading $DisplayName" -Status $status -PercentComplete $percent
                    }
                    else {
                        $status = "{0}  {1}/s" -f (Format-ByteSize $received), $speed
                        Write-Progress -Activity "Downloading $DisplayName" -Status $status
                    }
                    $lastUpdate = $timer.Elapsed
                }
            }

            $targetStream.Flush()
            $targetStream.Dispose()
            $targetStream = $null
            $sourceStream.Dispose()
            $sourceStream = $null
            Write-Progress -Activity "Downloading $DisplayName" -Completed

            if ($ExpectedSha256) {
                $actualHash = Get-Sha256 $partial
                if ($actualHash -ne $ExpectedSha256.ToLowerInvariant()) {
                    throw "SHA-256 mismatch for the downloaded file."
                }
            }

            Move-Item -LiteralPath $partial -Destination $Destination -Force
            Write-Host "Downloaded $DisplayName ($(Format-ByteSize $received))." -ForegroundColor Green
            return
        }
        catch {
            Write-Progress -Activity "Downloading $DisplayName" -Completed
            $failures.Add("$url ($route) -> $($_.Exception.Message)")
            Write-Warning "Download source failed; trying the next source."
        }
        finally {
            if ($targetStream) { $targetStream.Dispose() }
            if ($sourceStream) { $sourceStream.Dispose() }
            if ($response) { $response.Dispose() }
            if ($client) { $client.Dispose() }
        }
    }

    if (Test-Path -LiteralPath $partial) {
        Remove-Item -LiteralPath $partial -Force
    }
    throw "Unable to download $DisplayName from all configured sources:`n$($failures -join "`n")"
}

function Test-Python {
    param([string]$PythonExe)
    if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) { return $false }
    & $PythonExe -c "import struct,sys; ok=(3,9)<=sys.version_info[:2]<(3,14) and struct.calcsize('P')==8; raise SystemExit(0 if ok else 1)" 2>$null
    return ($LASTEXITCODE -eq 0)
}

function Find-SystemPython {
    $candidates = @(
        [PSCustomObject]@{ Command = "python"; Arguments = @() },
        [PSCustomObject]@{ Command = "py"; Arguments = @("-3.13") },
        [PSCustomObject]@{ Command = "py"; Arguments = @("-3.12") },
        [PSCustomObject]@{ Command = "py"; Arguments = @("-3.11") },
        [PSCustomObject]@{ Command = "py"; Arguments = @("-3.10") },
        [PSCustomObject]@{ Command = "py"; Arguments = @("-3.9") }
    )

    foreach ($candidate in $candidates) {
        if (-not (Get-Command $candidate.Command -ErrorAction SilentlyContinue)) { continue }
        $probe = "import struct,sys; ok=(3,9)<=sys.version_info[:2]<(3,14) and struct.calcsize('P')==8; print(sys.executable) if ok else None; raise SystemExit(0 if ok else 1)"
        $output = & $candidate.Command @($candidate.Arguments) -c $probe 2>$null
        if ($LASTEXITCODE -eq 0 -and $output) {
            $resolved = [string]($output | Select-Object -Last 1)
            if (Test-Path -LiteralPath $resolved -PathType Leaf) {
                return (Resolve-Path -LiteralPath $resolved).Path
            }
        }
    }
    return $null
}

function Install-PortablePython {
    if (-not [Environment]::Is64BitOperatingSystem) {
        throw "This automatic installer currently supports only 64-bit Windows."
    }

    $portableExe = Join-Path $PortablePythonDir "python.exe"
    if (Test-Python $portableExe) { return $portableExe }

    Write-Step "Python is missing. Downloading portable Python $PythonVersion"
    if (-not (Test-Path -LiteralPath $RuntimeDir)) {
        New-Item -ItemType Directory -Path $RuntimeDir -Force | Out-Null
    }

    $installerPath = Join-Path $RuntimeDir $PythonInstallerName
    $pythonUrls = @(
        "https://mirrors.aliyun.com/python-release/windows/$PythonInstallerName",
        "https://mirrors.huaweicloud.com/python/$PythonVersion/$PythonInstallerName",
        "https://registry.npmmirror.com/-/binary/python/$PythonVersion/$PythonInstallerName",
        "https://www.python.org/ftp/python/$PythonVersion/$PythonInstallerName"
    )

    $installerIsValid = $false
    if (Test-Path -LiteralPath $installerPath) {
        $existingHash = Get-Sha256 $installerPath
        $installerIsValid = ($existingHash -eq $PythonInstallerSha256)
    }
    if (-not $installerIsValid) {
        Download-FileWithProgress `
            -Urls $pythonUrls `
            -Destination $installerPath `
            -DisplayName $PythonInstallerName `
            -ExpectedSha256 $PythonInstallerSha256
    }

    $downloadedHash = Get-Sha256 $installerPath
    if ($downloadedHash -ne $PythonInstallerSha256) {
        Remove-Item -LiteralPath $installerPath -Force
        throw "Local Python checksum verification failed. Please run Start.bat again."
    }

    if (Test-Path -LiteralPath $PortablePythonDir) {
        Remove-Item -LiteralPath $PortablePythonDir -Recurse -Force
    }

    Write-Step "Installing Python into the project directory"
    $installerArguments = @(
        "/quiet",
        "InstallAllUsers=0",
        "TargetDir=$PortablePythonDir",
        "AssociateFiles=0",
        "CompileAll=0",
        "PrependPath=0",
        "Shortcuts=0",
        "Include_doc=0",
        "Include_debug=0",
        "Include_dev=0",
        "Include_launcher=0",
        "InstallLauncherAllUsers=0",
        "Include_pip=1",
        "Include_test=0",
        "Include_tools=1",
        "Include_tcltk=0"
    )
    $previousErrorPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $installerPath @installerArguments 2>&1 | ForEach-Object { Write-Host $_ }
    $installerExitCode = $LASTEXITCODE
    $ErrorActionPreference = $previousErrorPreference
    if ($installerExitCode -notin @(0, 3010)) {
        throw "Local Python installation failed with exit code $installerExitCode."
    }

    if (-not (Test-Python $portableExe)) {
        throw "Local Python could not start after installation."
    }

    return $portableExe
}

function Test-AppDependencies {
    param([string]$PythonExe)
    $healthCheck = "import os; from pathlib import Path; import imageio_ffmpeg; ffmpeg=Path(imageio_ffmpeg.get_ffmpeg_exe()); assert ffmpeg.is_file(); os.environ['PATH']=str(ffmpeg.parent)+os.pathsep+os.environ.get('PATH',''); import PySide6,pydub,librosa; from Crypto.Cipher import AES"
    $previousErrorPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $PythonExe -c $healthCheck 2>&1 | Out-Null
    $healthExitCode = $LASTEXITCODE
    $ErrorActionPreference = $previousErrorPreference
    return ($healthExitCode -eq 0)
}

function Test-Ffmpeg {
    param([string]$FfmpegExe)
    if (-not $FfmpegExe -or -not (Test-Path -LiteralPath $FfmpegExe -PathType Leaf)) { return $false }

    $previousErrorPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $FfmpegExe -hide_banner -version 2>&1 | Out-Null
    $ffmpegExitCode = $LASTEXITCODE
    $ErrorActionPreference = $previousErrorPreference
    return ($ffmpegExitCode -eq 0)
}

function Resolve-Ffmpeg {
    param([string]$PythonExe)

    $systemCommand = Get-Command "ffmpeg.exe" -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($systemCommand -and (Test-Ffmpeg $systemCommand.Source)) {
        return [PSCustomObject]@{ Path = [string]$systemCommand.Source; Source = "system FFmpeg" }
    }

    $previousErrorPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $bundledOutput = & $PythonExe -c "import base64,imageio_ffmpeg; path=imageio_ffmpeg.get_ffmpeg_exe(); print(base64.b64encode(path.encode('utf-8')).decode('ascii'))" 2>$null
    $bundledExitCode = $LASTEXITCODE
    $ErrorActionPreference = $previousErrorPreference
    if ($bundledExitCode -eq 0 -and $bundledOutput) {
        $encodedPath = [string]($bundledOutput | Select-Object -Last 1)
        $bundledPath = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($encodedPath))
        if (Test-Ffmpeg $bundledPath) {
            return [PSCustomObject]@{ Path = $bundledPath; Source = "project-local FFmpeg" }
        }
    }

    throw "FFmpeg is unavailable or failed its health check. Run Start.bat again to repair the project dependencies."
}

function Set-NetworkCompatibility {
    param([string]$PythonExe)

    $probeArguments = @(
        "-m", "pip", "index", "versions", "pip",
        "--disable-pip-version-check",
        "--retries", "0",
        "--timeout", "8",
        "--index-url", "https://pypi.tuna.tsinghua.edu.cn/simple"
    )
    $previousErrorPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $PythonExe @probeArguments 2>&1 | Out-Null
    $proxyProbeExitCode = $LASTEXITCODE
    $ErrorActionPreference = $previousErrorPreference
    if ($proxyProbeExitCode -eq 0) { return }

    $env:NO_PROXY = "*"
    $env:no_proxy = "*"
    $ErrorActionPreference = "Continue"
    & $PythonExe @probeArguments 2>&1 | Out-Null
    $directProbeExitCode = $LASTEXITCODE
    $ErrorActionPreference = $previousErrorPreference
    if ($directProbeExitCode -eq 0) {
        Write-Warning "The configured proxy cannot reach PyPI; bypassing it for this startup."
    }
    else {
        Write-Warning "The package index probe failed; the installer will still try each configured source."
    }
}

function Install-AppDependencies {
    param([string]$PythonExe)

    $indexes = @(
        [PSCustomObject]@{ Name = "Tsinghua PyPI mirror"; Url = "https://pypi.tuna.tsinghua.edu.cn/simple" },
        [PSCustomObject]@{ Name = "Aliyun PyPI mirror"; Url = "https://mirrors.aliyun.com/pypi/simple/" },
        [PSCustomObject]@{ Name = "official PyPI"; Url = "https://pypi.org/simple" }
    )

    Set-NetworkCompatibility $PythonExe
    foreach ($index in $indexes) {
        Write-Step "Installing dependencies from $($index.Name)"
        & $PythonExe -m pip install `
            --disable-pip-version-check `
            --no-input `
            --no-warn-script-location `
            --prefer-binary `
            --progress-bar on `
            --retries 2 `
            --timeout 45 `
            --index-url $index.Url `
            -r $RequirementsPath

        if ($LASTEXITCODE -eq 0 -and (Test-AppDependencies $PythonExe)) {
            return
        }
        Write-Warning "$($index.Name) failed; trying the next package source."
    }

    throw "Dependency installation failed from every configured package source."
}

try {
    Set-Location -LiteralPath $ProjectRoot
    if (-not (Test-Path -LiteralPath $AppPath -PathType Leaf)) { throw "app.py is missing." }
    if (-not (Test-Path -LiteralPath $RequirementsPath -PathType Leaf)) { throw "requirements.txt is missing." }

    Write-Host "XMaoMusic OffsetEditor startup" -ForegroundColor White
    Write-Host "Project: $ProjectRoot"

    $PythonExe = Join-Path $VenvDir "Scripts\python.exe"
    $StampPath = Join-Path $VenvDir ".requirements.sha256"

    if (-not (Test-Python $PythonExe)) {
        $systemPython = Find-SystemPython
        if ($systemPython) {
            Write-Step "Creating a project-local Python environment"
            Write-Host "Using: $systemPython"
            if (Test-Path -LiteralPath $VenvDir) {
                Remove-Item -LiteralPath $VenvDir -Recurse -Force
            }
            & $systemPython -m venv $VenvDir
            if ($LASTEXITCODE -ne 0 -or -not (Test-Python $PythonExe)) {
                Write-Warning "The detected Python cannot create a local environment; using project-local Python instead."
                if (Test-Path -LiteralPath $VenvDir) {
                    Remove-Item -LiteralPath $VenvDir -Recurse -Force
                }
                $PythonExe = Install-PortablePython
                $StampPath = Join-Path $PortablePythonDir ".requirements.sha256"
            }
        }
        else {
            $PythonExe = Install-PortablePython
            $StampPath = Join-Path $PortablePythonDir ".requirements.sha256"
        }
    }

    $requirementsHash = Get-Sha256 $RequirementsPath
    $installedHash = if (Test-Path -LiteralPath $StampPath) {
        (Get-Content -LiteralPath $StampPath -Raw).Trim().ToLowerInvariant()
    } else { "" }

    if ($installedHash -ne $requirementsHash -or -not (Test-AppDependencies $PythonExe)) {
        Install-AppDependencies $PythonExe
        Set-Content -LiteralPath $StampPath -Value $requirementsHash -Encoding ASCII
    }
    else {
        Write-Step "Environment check passed"
        Write-Host "All required dependencies are ready." -ForegroundColor Green
    }

    Write-Step "Checking FFmpeg"
    $Ffmpeg = Resolve-Ffmpeg $PythonExe
    $env:FFMPEG_BINARY = $Ffmpeg.Path
    $ffmpegDirectory = Split-Path -Parent $Ffmpeg.Path
    if (($env:PATH -split ";") -notcontains $ffmpegDirectory) {
        $env:PATH = "$ffmpegDirectory;$env:PATH"
    }
    Write-Host "Using $($Ffmpeg.Source): $($Ffmpeg.Path)" -ForegroundColor Green

    $PythonwExe = Join-Path (Split-Path -Parent $PythonExe) "pythonw.exe"
    if (-not (Test-Path -LiteralPath $PythonwExe -PathType Leaf)) {
        $PythonwExe = $PythonExe
    }

    Write-Step "Starting XMaoMusic OffsetEditor"
    Start-Process -FilePath $PythonwExe -ArgumentList @("`"$AppPath`"") -WorkingDirectory $ProjectRoot
    Write-Host "Application started." -ForegroundColor Green
    exit 0
}
catch {
    Write-Progress -Activity "Startup" -Completed
    Write-Host ""
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Resolve the issue shown above, then run Start.bat again." -ForegroundColor Yellow
    exit 1
}
