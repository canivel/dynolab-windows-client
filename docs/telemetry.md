# Worker telemetry v1

The worker app owns an HTTP listener at `127.0.0.1:50055`, independently of the RPC process. Only `GET /v1/telemetry` is accepted. The JSON response uses [this schema](POOL-TELEMETRY-V1.schema.json), `Cache-Control: no-store` and a 32 KiB maximum. Request headers are capped at 8 KiB, four clients run concurrently, and incomplete headers have a two-second deadline. Extra clients are closed. Windows may reset an oversized request after rejecting it.

NVIDIA collection happens about once per second in a background thread with a two-second subprocess timeout. HTTP requests read cached samples. Failed attempts increment sequence, report error/unavailable and clear metrics. Samples older than five seconds retain identity but null measurements. Instance UUID changes with each app launch; age is monotonic and requires no shared clock.

GPU identity is the `nvidia-smi` UUID. On GUI launch of RPC, the selected inventory entry is resolved again, its UUID is set as the child's `CUDA_VISIBLE_DEVICES`, and RPC selects `CUDA0` inside that one-device mapping. Thus inventory indices are not assumed to match CUDA's native ordering. Missing identity fails visibly instead of guessing. Older/manual Worker callers without an explicit UUID report unknown selection.

RPC running and PID come from the owned process's live poll, independent of the UI state. Metrics include other applications' GPU activity. No prompts, model responses, credentials, command lines or arbitrary files are exposed.

## Existing pairing upgrade

**Enable telemetry for paired coordinator** uses the existing same-account elevation flow. It upgrades exact Dyno-generated key entries for that Windows account, preserving key material, source address, forced command and unrelated entries. Custom restrictions fail closed. The resulting key permits only `127.0.0.1:50052` and `127.0.0.1:50055`. The SYSTEM/Administrators ACL remains protected. No firewall port, SSH configuration edit, service restart, host-key replacement or re-pairing is required.

## Mac integration

Add a second local forward to the existing verified SSH tunnel: a free coordinator loopback port to worker `127.0.0.1:50055`. Keep the original identity, strict host checks, route restrictions and RPC forward. Existing saved records need no migration. The Mac implementation lives in Dyno Lab and is not replaced by this repository.

Poll only the owned loopback forward: no redirects, two-second timeout, 32 KiB cap, schema/type/range validation. A repeated sequence or age above five seconds is stale. Reset chart history on instance change, retain gaps rather than zero values and do not mix workers. Back off after rejected forwarding (for example 30 seconds) and offer Retry telemetry. Missing telemetry must never fail inference. Close polling and the owned tunnel with the pool session.
