param(
    [switch] $Clean
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Dist = Join-Path $Root "dist"

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

$Work = Join-Path ([System.IO.Path]::GetTempPath()) (
    "weather-application-pyinstaller-" + [guid]::NewGuid().ToString("N")
)
New-Item -ItemType Directory -Path $Work -Force | Out-Null

try {
    & $Python -m PyInstaller `
        --name WeatherApplication `
        --onefile `
        --console `
        --clean `
        --distpath $Dist `
        --workpath (Join-Path $Work "build") `
        --specpath $Work `
        (Join-Path $Root "src\main.py")

    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE."
    }
}
finally {
    if (Test-Path -LiteralPath $Work) {
        Remove-Item -LiteralPath $Work -Recurse -Force -ErrorAction SilentlyContinue
    }
}

$Executable = Join-Path $Dist "WeatherApplication.exe"
if (-not (Test-Path -LiteralPath $Executable)) {
    throw "Expected executable was not created: $Executable"
}

Write-Host "Executable created at: $Executable"
