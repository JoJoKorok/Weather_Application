$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (!(Test-Path -LiteralPath $Python)) {
  & (Join-Path $Root "setup.ps1")
}

Push-Location $Root
try {
  & $Python -m src.main
}
finally {
  Pop-Location
}
