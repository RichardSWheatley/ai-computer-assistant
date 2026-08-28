# One-command Windows build: bundle + installer.
#   powershell -ExecutionPolicy Bypass -File packaging\build.ps1
# Needs: Python 3.11+, Inno Setup 6 (ISCC on PATH or default install dir).

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

if (-not (Test-Path ".venv-build")) { py -m venv .venv-build }
& .venv-build\Scripts\Activate.ps1

pip install --upgrade pip | Out-Null
pip install -e ".[gui,mcp,firmware,voice]" pyinstaller

pyinstaller packaging\rita.spec --noconfirm --distpath dist

$version = (python -c "import rita; print(rita.__version__)").Trim()

$iscc = Get-Command ISCC -ErrorAction SilentlyContinue
if (-not $iscc) {
    $candidate = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
    if (Test-Path $candidate) { $iscc = $candidate }
    else { throw "Inno Setup 6 not found (install it or put ISCC on PATH)" }
}
& $iscc "/DAppVersion=$version" packaging\installer.iss

Write-Host "Installer: dist\installer\RITA-Setup-$version.exe"
