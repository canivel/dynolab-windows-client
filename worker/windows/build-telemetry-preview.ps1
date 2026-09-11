param(
    [Parameter(Mandatory=$true)][string]$Python,
    [Parameter(Mandatory=$true)][string]$RuntimeDirectory,
    [string]$OutputDirectory = 'dist\windows-telemetry'
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$runtime = (Resolve-Path -LiteralPath $RuntimeDirectory).Path
$manifest = Get-Content -LiteralPath (Join-Path $runtime 'manifest.json') -Raw | ConvertFrom-Json
if ($manifest.revision -ne '5bda51bfbc62e64193221e639f6ad4e08767d760') { throw 'Wrong runtime revision' }
foreach ($entry in $manifest.files.PSObject.Properties) {
    if ([IO.Path]::GetFileName($entry.Name) -ne $entry.Name) { throw 'Invalid manifest path' }
    if ((Get-FileHash -LiteralPath (Join-Path $runtime $entry.Name) -Algorithm SHA256).Hash -ne $entry.Value) { throw "Runtime integrity failure: $($entry.Name)" }
}
$output = [IO.Path]::GetFullPath((Join-Path $repo $OutputDirectory))
$build = Join-Path $repo 'work\telemetry-pyinstaller'
& $Python -m PyInstaller --noconfirm --clean --windowed --onedir --name DynoWorker --paths "$repo\src" --distpath $output --workpath "$build\build" --specpath $build "$PSScriptRoot\entry.py"
if ($LASTEXITCODE) { throw 'PyInstaller failed' }
$app = Join-Path $output 'DynoWorker'
Copy-Item -LiteralPath $runtime -Destination $app -Recurse -Force
foreach ($name in @('setup-lan.ps1', 'setup-discovery.ps1', 'setup-telemetry.ps1', 'README.md', 'PAIRING.md')) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination $app -Force
}
# Carry the existing runtime's redistribution notices into this local preview.
$previousApp = Split-Path -Parent $runtime
Get-ChildItem -LiteralPath $previousApp -File | Where-Object Name -Match 'LICENSE|NOTICE' | Copy-Item -Destination $app -Force
& $Python "$PSScriptRoot\package-notices.py" $app
if ($LASTEXITCODE) { throw 'Notice packaging failed' }
Write-Output "Built local telemetry preview: $app\DynoWorker.exe"
