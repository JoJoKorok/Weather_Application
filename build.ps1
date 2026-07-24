param(
    [switch] $Clean
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    & (Join-Path $Root "setup.ps1")
}

if ($Clean) {
    $resolvedRoot = [System.IO.Path]::GetFullPath($Root)
    foreach ($target in @("build", "dist")) {
        $resolvedTarget = [System.IO.Path]::GetFullPath((Join-Path $Root $target))
        if (-not $resolvedTarget.StartsWith($resolvedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to clean a path outside the repository: $resolvedTarget"
        }
        if (Test-Path -LiteralPath $resolvedTarget) {
            Remove-Item -LiteralPath $resolvedTarget -Recurse -Force
        }
    }
}

& $Python -m PyInstaller `
    --name WeatherApplication `
    --onefile `
    --console `
    --clean `
    (Join-Path $Root "src\main.py")

Write-Host "Executable created at: $(Join-Path $Root 'dist\WeatherApplication.exe')"
