$ErrorActionPreference = 'Stop'
$tokens = $null; $parseErrors = $null
$path = Join-Path $PSScriptRoot '..\worker\windows\setup-telemetry.ps1'
$ast = [Management.Automation.Language.Parser]::ParseFile($path, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count) { throw $parseErrors }
$fn = $ast.Find({param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Upgrade-TelemetryKeys'}, $true)
. ([scriptblock]::Create($fn.Extent.Text))
$sid = 'S-1-5-21-1-2-3-1001'
$key = 'A' * 68
$line = 'from="192.168.50.20",restrict,port-forwarding,permitopen="127.0.0.1:50052",command="echo Dyno forwarding only" ssh-ed25519 ' + $key + ' dyno-worker-' + $sid + '-192.168.50.20'
$other = '# unrelated entry unchanged'
$result = Upgrade-TelemetryKeys @($other, $line) $sid
if ($result.Count -ne 2 -or $result[0] -ne $other) { throw 'Unrelated entries changed' }
$expected = $line.Replace('permitopen="127.0.0.1:50052",', 'permitopen="127.0.0.1:50052",permitopen="127.0.0.1:50055",')
if ($result[1] -cne $expected) { throw 'Key or restrictions changed' }
$again = Upgrade-TelemetryKeys $result $sid
if (($again -join "`n") -cne ($result -join "`n")) { throw 'Upgrade not idempotent' }
foreach ($bad in @($line.Replace('restrict,', ''), $line.Replace('50052', '12345'), $line.Replace('from="192.168.50.20"', 'from="10.0.0.2"'))) {
    $failed = $false
    try { Upgrade-TelemetryKeys @($bad) $sid | Out-Null } catch { $failed = $true }
    if (-not $failed) { throw 'Custom/mismatched restrictions accepted' }
}
$text = Get-Content -LiteralPath $path -Raw
if ($text -match '(?i)New-NetFirewallRule|Restart-Service|ssh-keygen') { throw 'Upgrade changes firewall/service/identity' }
Write-Output 'PASS: telemetry upgrade preserves key and unrelated entries; exactly two targets; idempotent; rejects custom restrictions; no firewall/service/key generation.'
