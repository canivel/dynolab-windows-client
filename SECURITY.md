# Security policy

Report vulnerabilities through [private vulnerability reporting](https://github.com/canivel/dynolab-windows-client/security/advisories/new). Include the affected revision, impact and a minimal redacted reproduction. Do not post exploit details, secrets or personal diagnostics in public issues.

Security work targets `main` and the latest supported preview. This is an experimental project without a guaranteed response time or paid bounty.

RPC and telemetry are loopback-only and carried through constrained, verified SSH forwarding. The telemetry endpoint is accessible to local processes and explicitly authorized coordinators; it reports device-wide metrics, including other GPU applications. Use a trusted LAN and dedicated pool identities. Existing Windows SSH configuration may grant additional access outside Dyno's rules.

Preview binaries are not a generally signed Windows release. A runtime hash manifest detects mismatches but does not authenticate a publisher. See [signing](worker/windows/SIGNING.md). Never bypass host-key verification to repair a connection or disable Windows security as an installation instruction.
