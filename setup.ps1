# Optional bootstrap. The application itself is Python/Textual.
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host 'Install Python 3.11+ from https://www.python.org/downloads/windows/ and run setup.ps1 again.'
    exit 1
}
$setupPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $setupPython)) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
& $setupPython -m pip install -e .
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $setupPython -m jobagent setup
exit $LASTEXITCODE
