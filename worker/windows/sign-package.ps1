# Sign a separate copy of an existing package. Never modifies the input bundle.
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$AppDirectory,
    [string]$OutputDirectory,
    [string]$MetadataPath,
    [string]$DlibPath,
    [string]$SignToolPath = 'C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\signtool.exe',
    [switch]$InventoryOnly
)
$ErrorActionPreference = 'Stop'
$app = (Resolve-Path -LiteralPath $AppDirectory).Path
if (-not (Test-Path -LiteralPath (Join-Path $app 'DynoWorker.exe'))) { throw 'AppDirectory must contain DynoWorker.exe.' }
$manifestPath = Join-Path $app 'runtime\manifest.json'
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
if ($manifest.revision -ne '5bda51bfbc62e64193221e639f6ad4e08767d760') { throw 'Unexpected backend revision.' }
if (-not $manifest.files.'ggml-rpc-server.exe') { throw 'Manifest is missing the backend.' }
foreach ($property in $manifest.files.PSObject.Properties) {
    if ($property.Name -match '[/\\:]' -or $property.Name -in '.', '..') { throw 'Invalid manifest entry.' }
    $actual = (Get-FileHash -LiteralPath (Join-Path $app ('runtime\' + $property.Name)) -Algorithm SHA256).Hash
    if ($actual -ne $property.Value) { throw "Input integrity failure: $($property.Name)" }
}
$files = @(Get-ChildItem -LiteralPath $app -Recurse -File | Where-Object { $_.Extension -in '.exe', '.dll', '.pyd', '.ps1' })
if ($InventoryOnly) {
    foreach ($file in $files) {
        $signature = Get-AuthenticodeSignature -LiteralPath $file.FullName
        [PSCustomObject]@{ File=$file.FullName.Substring($app.Length + 1); Signature=$signature.Status; Action=$(if ($signature.Status -eq 'Valid') { 'Preserve' } elseif ($signature.Status -eq 'NotSigned') { 'Sign' } else { 'Blocked' }) }
    }
    return
}
if (-not $OutputDirectory -or -not $MetadataPath -or -not $DlibPath) { throw 'Provide OutputDirectory, MetadataPath and DlibPath, or use InventoryOnly.' }
foreach ($path in @($SignToolPath, $DlibPath, $MetadataPath)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing signing prerequisite: $path" }
}
$MetadataPath = (Resolve-Path -LiteralPath $MetadataPath).Path
$DlibPath = (Resolve-Path -LiteralPath $DlibPath).Path
$metadata = Get-Content -LiteralPath $MetadataPath -Raw | ConvertFrom-Json
if ($metadata.Endpoint -notmatch '^https://[a-z0-9]+\.codesigning\.azure\.net/?$' -or
    -not $metadata.CodeSigningAccountName -or -not $metadata.CertificateProfileName) { throw 'Provide valid Artifact Signing metadata.' }
$output = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputDirectory).TrimEnd('\')
if ($output -eq $app -or $output.StartsWith($app + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Output must be outside the input app.' }
if (Test-Path -LiteralPath $output) { throw 'Use a new output directory; existing output is never overwritten.' }
New-Item -ItemType Directory -Path $output | Out-Null
$signedApp = Join-Path $output 'DynoWorker'
Copy-Item -LiteralPath $app -Destination $signedApp -Recurse
$report = @()
foreach ($file in (Get-ChildItem -LiteralPath $signedApp -Recurse -File | Where-Object { $_.Extension -in '.exe', '.dll', '.pyd', '.ps1' })) {
    $signature = Get-AuthenticodeSignature -LiteralPath $file.FullName
    $action = 'Preserved'
    if ($signature.Status -ne 'Valid') {
        # Refuse to conceal tampering or an invalid pre-existing signature.
        if ($signature.Status -ne 'NotSigned') { throw "Invalid existing signature ($($signature.Status)): $($file.FullName)" }
        & $SignToolPath sign /fd SHA256 /tr 'http://timestamp.acs.microsoft.com' /td SHA256 /dlib $DlibPath /dmdf $MetadataPath $file.FullName
        if ($LASTEXITCODE -ne 0) { throw "Signing failed: $($file.Name). Incomplete staging folder retained; no ZIP produced." }
        $action = 'Signed'
    }
    & $SignToolPath verify /pa /all $file.FullName
    if ($LASTEXITCODE -ne 0) { throw "Signature verification failed: $($file.Name)" }
    $signature = Get-AuthenticodeSignature -LiteralPath $file.FullName
    if ($signature.Status -ne 'Valid') { throw "Untrusted signature: $($file.Name)" }
    if ($action -eq 'Signed' -and -not $signature.TimeStamperCertificate) { throw "Missing timestamp: $($file.Name)" }
    $report += [PSCustomObject]@{File=$file.FullName.Substring($signedApp.Length + 1); Action=$action; Publisher=$signature.SignerCertificate.Subject; SHA256=(Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLower()}
}
# Authenticode changes file bytes; regenerate hashes only after signing succeeds.
$hashes = @{}
Get-ChildItem -LiteralPath (Join-Path $signedApp 'runtime') -File | Where-Object { $_.Name -ne 'manifest.json' } | ForEach-Object {
    $hashes[$_.Name] = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLower()
}
@{revision=$manifest.revision; files=$hashes} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $signedApp 'runtime\manifest.json') -Encoding ascii
$report | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $signedApp 'signing-report.json') -Encoding utf8
$zip = Join-Path $output 'DynoWorker-windows-x64-signed-preview.zip'
Compress-Archive -LiteralPath $signedApp -DestinationPath $zip
(Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLower() | Set-Content -LiteralPath ($zip + '.sha256') -Encoding ascii
Write-Output "Signed preview: $zip. Test on the protected host before distributing."
