# Creates a local virtual environment and installs dependencies.

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$Venv = Join-Path $Root ".venv"
$Python = Join-Path $Venv "Scripts\python.exe"
$Pip = Join-Path $Venv "Scripts\pip.exe"

# Create venv if missing
if (!(Test-Path -LiteralPath $Python)) {
  python -m venv $Venv
}

# Upgrade pip
& $Python -m pip install --upgrade pip

# Install client deps
& $Pip install -r (Join-Path $Root "requirements.txt")

# Install proxy deps (so proxy can run locally too)
& $Pip install -r (Join-Path $Root "proxy\requirements.txt")

Write-Host "Setup complete."
Write-Host "Run client: '.\.venv\Scripts\python src\main.py' or 'python -m src.main'"
Write-Host "Run proxy:  .\.venv\Scripts\uvicorn proxy.server:app --host 127.0.0.1 --port 8000"
