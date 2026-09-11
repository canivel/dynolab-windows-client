# Contributing to Dyno Lab Windows Worker

The project is maintained by @canivel. Anyone can propose a focused PR; only authorized maintainers can merge or release.

Open an issue before substantial features, protocol changes, dependencies or changes to network exposure. Fork the repository, branch from `main`, and describe the user-visible problem, resulting behavior, tests and compatibility risks in your PR. UI changes need actual app screenshots with private information removed.

Follow the commands in [README.md](README.md) to run the Python suite and Windows ACL tests. Test lifecycle and protocol changes on real Windows hardware. CI does not prove CUDA inference, LAN discovery or end-to-end pairing works. Record the GPU architecture and pinned backend revision when sharing redacted results.

Preserve verified SSH host keys, dedicated identities, unrelated authorized-key entries, loopback RPC and bounded telemetry. Never make a failed test pass by disabling host verification or broadening a firewall rule. Unsupported metrics must remain unavailable rather than zero.

Do not commit keys, tokens, credentials, environment files, pairing stores, home-directory paths, local network identifiers, prompts, responses, model weights, runtime logs or diagnostics. Use synthetic fixtures. Review the entire staged diff and run `python scripts/check-public-tree.py` before pushing.

PR workflows run with read-only tokens on disposable GitHub-hosted runners. No release credentials, `pull_request_target` execution of contributor code or self-hosted PR runners. Inspect workflow, dependency and build-script changes before approving a fork run.

Passing CI is necessary, not acceptance. Code-owner approval, current checks and resolved conversations govern community merges. The solo maintainer can use the review ruleset's PR-only exception, but cannot bypass the separate integrity checks. See [maintenance](docs/maintaining.md).
