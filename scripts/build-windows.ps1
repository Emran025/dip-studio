[CmdletBinding()]
param(
    [switch]$SkipTests,
    [switch]$SkipInstall,
    [string]$Python = "python"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Invoke-Step {
    param([string]$Name, [scriptblock]$Command)
    Write-Host "`n==> $Name" -ForegroundColor Cyan
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Step failed ($LASTEXITCODE): $Name"
    }
}

if (-not $SkipInstall) {
    Invoke-Step "Upgrade pip" { & $Python -m pip install --upgrade pip }
    Invoke-Step "Install packaged application dependencies" {
        & $Python -m pip install ".[gui,vision]" pyinstaller
    }
}

if (-not $SkipTests) {
    $env:QT_QPA_PLATFORM = "offscreen"
    Invoke-Step "Run full test suite" { & $Python -m pytest --no-cov }
}

Remove-Item -Recurse -Force -ErrorAction SilentlyContinue build, dist
Invoke-Step "Build DIP-Studio.exe" {
    & $Python -m PyInstaller --noconfirm --clean dip_studio.spec
}

$executable = Join-Path $Root "dist\DIP-Studio.exe"
if (-not (Test-Path $executable)) {
    throw "PyInstaller did not produce $executable"
}

Write-Host "`n==> Smoke-test executable (15 seconds)" -ForegroundColor Cyan
$env:QT_QPA_PLATFORM = "offscreen"
$process = Start-Process -FilePath $executable -PassThru
try {
    if (-not $process.WaitForExit(15000)) {
        Stop-Process -Id $process.Id -Force
        Write-Host "Smoke test passed: application stayed alive for 15 seconds." -ForegroundColor Green
    } elseif ($process.ExitCode -ne 0) {
        throw "Packaged application exited with code $($process.ExitCode)"
    } else {
        Write-Host "Smoke test passed: application exited cleanly." -ForegroundColor Green
    }
} finally {
    if (-not $process.HasExited) {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    }
}

$archive = Join-Path $Root "DIP-Studio-windows.zip"
Remove-Item -Force -ErrorAction SilentlyContinue $archive
Invoke-Step "Package artifact" {
    Compress-Archive -Path $executable -DestinationPath $archive
}
Write-Host "`nBuild complete: $archive" -ForegroundColor Green
