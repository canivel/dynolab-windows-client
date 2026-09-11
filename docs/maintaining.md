# Maintaining the Windows worker

This repository follows Dyno Lab's separation between review and integrity rules. Public PRs are proposals, not permission to merge or release.

## Repository controls

- **Main review:** default branch, one approval, code-owner review, stale approval dismissal, resolved conversations, linear history, no deletion or force push. The repository-admin exception applies **through PRs only**, for the solo maintainer; community changes still require review.
- **Main integrity:** separate ruleset with no bypass, current passing **Worker protocol tests** and **Native Windows build**, linear history, no deletion or force push. Keep required job names stable and avoid path filters.
- **Immutable version tags:** prevent updates, deletion and force pushes of `v*` tags without a bypass.
- **Release publishers:** only repository administrators may create `v*` tags. No automated Windows release publication is configured in this preview.
- Actions tokens stay read-only; workflows cannot create or approve PRs. Fork workflows require maintainer approval. Never execute unreviewed fork code on a self-hosted runner or with signing credentials.
- Enable private vulnerability reporting, dependency alerts, secret scanning and push protection where supported. Review collaborators, apps, deploy keys and runner access deliberately.

CODEOWNERS and workflow files alone do not activate GitHub settings. Verify the rulesets and settings in GitHub after bootstrap. Preserve the separate integrity layer when changing the solo-maintainer review exception.

## Dependencies and CI

Action references are pinned to commit SHAs; Python development dependencies are version-pinned. Transitive Python hashes are not yet locked, so these builds are not claimed reproducible. Dependabot proposes reviewed weekly updates. Hosted CI runs portable protocol tests and native Windows tests/packaging without downloading models, using CUDA hardware, signing or publishing.

The `src/dyno/pool` namespace is shared with the coordinator for protocol compatibility. Do not install this distribution into the same environment as the Mac `mlx-dyno` distribution. Integrate narrow source changes through reviewed PRs instead of overwriting the Mac checkout.

## Release gates

Build from a reviewed main commit, retain the pinned llama.cpp revision, include third-party notices, verify runtime hashes and validate each advertised CUDA architecture on clean Windows hardware. Check Windows cancellation, occupied ports, existing pairing upgrades, preserved ACLs, disconnects and app shutdown. Record actual pool generation and tunneled telemetry results separately from idle startup.

Windows publisher signing and an independently reviewed release pipeline remain required work before advertising a general installer. Do not copy Apple signing credentials into this repository. Keep signing material in a protected release environment, never PR jobs or source. Publish a reviewed draft only after hardware and installation acceptance; never silently replace a published binary or move its version tag.
