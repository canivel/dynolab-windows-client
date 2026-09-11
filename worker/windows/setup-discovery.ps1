param([Parameter(Mandatory=$true)][string]$RequestPath, [Parameter(Mandatory=$true)][string]$ResultPath, [string]$StatusPath)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
function Report-Stage([string]$Message) {
    if ($StatusPath) { $Message | Set-Content -LiteralPath $StatusPath -Encoding utf8 }
}
try {
    Report-Stage 'Checking your selected network and Windows permissions…'
    $request = Get-Content -LiteralPath $RequestPath -Raw | ConvertFrom-Json
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    if ($identity.User.Value -ne $request.user_sid) { throw 'Approve using the same Windows account as Dyno Worker.' }
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Administrator approval is required.' }
    $program = (Resolve-Path -LiteralPath $request.program).Path
    if ([IO.Path]::GetExtension($program) -ne '.exe') { throw 'Expected the Dyno executable path.' }
    if (-not $request.interface -or -not $request.address) { throw 'Select the local network in Dyno Worker first.' }
    $addresses = @(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.InterfaceAlias -eq $request.interface -and $_.IPAddress -eq $request.address -and $_.AddressState -eq 'Preferred' })
    if ($addresses.Count -ne 1) { throw 'Selected network changed. Refresh networks and select it again.' }
    $profile = Get-NetConnectionProfile -InterfaceIndex $addresses[0].InterfaceIndex
    if ($profile.NetworkCategory -eq 'Public' -and $request.make_private -eq $true) {
        Report-Stage 'Setting your approved network to Private…'
        Set-NetConnectionProfile -InterfaceIndex $addresses[0].InterfaceIndex -NetworkCategory Private
        $profile = Get-NetConnectionProfile -InterfaceIndex $addresses[0].InterfaceIndex
    }
    if ($profile.NetworkCategory -ne 'Private') { throw 'Selected network must be Private to enable discovery.' }
    Report-Stage 'Configuring discovery on the selected network…'
    foreach ($entry in @(@{name='Dyno-Worker-Discovery'; protocol='UDP'; port=5353},
                          @{name='Dyno-Worker-Pairing'; protocol='TCP'; port=50053})) {
        # mDNS queries target the multicast group, not only our unicast IP.
        $localAddresses = @($request.address)
        if ($entry.protocol -eq 'UDP') { $localAddresses += '224.0.0.251' }
        Get-NetFirewallRule -Name $entry.name -ErrorAction SilentlyContinue | Remove-NetFirewallRule
        New-NetFirewallRule -Name $entry.name -DisplayName $entry.name -Direction Inbound -Action Allow `
            -Protocol $entry.protocol -LocalPort $entry.port -Profile Private -RemoteAddress LocalSubnet `
            -Program $program -LocalAddress $localAddresses -InterfaceAlias $request.interface | Out-Null
    }
    Report-Stage 'Discovery configured. Opening the pairing window…'
    'Discovery enabled for this app on Private local networks. GPU RPC remains loopback-only.' |
        Set-Content -LiteralPath $ResultPath -Encoding utf8
    exit 0
} catch {
    Report-Stage ('Discovery needs attention: ' + $_.Exception.Message)
    ('Discovery setup failed: ' + $_.Exception.Message) | Set-Content -LiteralPath $ResultPath -Encoding utf8
    exit 1
}
