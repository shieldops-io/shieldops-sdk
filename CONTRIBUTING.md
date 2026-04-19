# Contributing to shieldops-sdk

Thanks for your interest in contributing. This project is Apache-2.0
licensed and accepts contributions via GitHub pull requests under the
[Developer Certificate of Origin](#developer-certificate-of-origin)
(DCO). **We do not require a Contributor License Agreement (CLA).**

## Code of Conduct

This project adopts the [Contributor Covenant 2.1](https://www.contributor-covenant.org/version/2/1/code_of_conduct/).
By participating you agree to uphold it. Report unacceptable behavior to
`conduct@shieldops.io`.

## Developer Certificate of Origin

Every commit must be signed off, certifying that you wrote the patch or
otherwise have the right to contribute it under the project license. We
use the Developer Certificate of Origin 1.1 verbatim:

```
Developer Certificate of Origin
Version 1.1

Copyright (C) 2004, 2006 The Linux Foundation and its contributors.
1 Letterman Drive
Suite D4700
San Francisco, CA, 94129

Everyone is permitted to copy and distribute verbatim copies of this
license document, but changing it is not allowed.


Developer's Certificate of Origin 1.1

By making a contribution to this project, I certify that:

(a) The contribution was created in whole or in part by me and I
    have the right to submit it under the open source license
    indicated in the file; or

(b) The contribution is based upon previous work that, to the best
    of my knowledge, is covered under an appropriate open source
    license and I have the right under that license to submit that
    work with modifications, whether created in whole or in part
    by me, under the same open source license (unless I am
    permitted to submit under a different license), as indicated
    in the file; or

(c) The contribution was provided directly to me by some other
    person who certified (a), (b) or (c) and I have not modified
    it.

(d) I understand and agree that this project and the contribution
    are public and that a record of the contribution (including all
    personal information I submit with it, including my sign-off) is
    maintained indefinitely and may be redistributed consistent with
    this project or the open source license(s) involved.
```

### Signing commits

Append the sign-off automatically with `-s`:

```bash
git commit -s -m "feat: add foo integration"
```

This adds a `Signed-off-by: Your Name <you@example.com>` trailer to the
commit message, which the DCO bot checks on every pull request. Make
sure your `git config user.name` and `user.email` match the identity you
intend to sign with.

If you forget, amend:

```bash
git commit --amend -s --no-edit
git push --force-with-lease
```

## Development setup

Requires Python 3.10 or newer.

```bash
git clone https://github.com/shieldops/shieldops-sdk.git
cd shieldops-sdk
pip install -e ".[dev]"
```

Common tasks:

```bash
ruff check src/ tests/          # lint
ruff format src/ tests/         # format
pytest tests/ -v --tb=short     # run tests
pytest tests/ --cov=src         # with coverage
```

All CI checks must pass before merge: `ruff check`, `ruff format --check`,
`pytest`, and DCO verification.

## Branches and commits

- Branch names use the prefixes `feat/`, `fix/`, `chore/`, or `docs/`.
- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/):
  `feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:`, `perf:`.
- Keep commits focused; prefer multiple small commits over one mega-commit.
- Every commit must be DCO-signed (`git commit -s`).

## Pull requests

See the pull request template for the required sections. In short:

- Link the issue the PR closes.
- Describe what changed and why (the "why" matters more than the "what").
- Add or update tests. New code must have **>= 80% line coverage**.
- Update `CHANGELOG.md` under `[Unreleased]`.
- Confirm DCO sign-off on every commit.

A maintainer will review within 5 business days. Expect at least one
round of feedback on non-trivial changes.

## Proposing a new framework integration

Framework integrations live under `src/shieldops_sdk/integrations/<name>/`.
Before sending a PR, open an issue with:

1. **The framework and its public hook surface.** Which callback, middleware,
   or wrapper entry point will you use to intercept tool calls?
2. **Interface contract.** How does the integration map the framework's
   tool-call event to the SDK's `check(tool_name, parameters)` call? What
   does it do with the `ShieldOpsDecision` result in each mode?
3. **Test plan.** At minimum: unit tests for audit-mode passthrough,
   enforce-mode denial, configuration loading, and error paths. Coverage
   must be **>= 80%** on all new code.
4. **Optional dependency wiring.** Add a `pyproject.toml` extra
   (e.g. `[project.optional-dependencies] foo = ["foo-framework>=X.Y"]`)
   and import the framework lazily so the core SDK remains lightweight.

We will respond on the issue before you invest PR time.

## Release cadence

- **Minor** releases every 6 weeks (new features, no breaking changes).
- **Patch** releases as needed (bug fixes, security patches).
- **Major** releases only after a public RFC issue with at least 2 weeks
  of community comment and a committed migration guide.

Security patches for critical issues may ship outside the normal cadence.

## Questions

- Usage questions: GitHub Discussions.
- Bug reports / feature requests: GitHub Issues (see templates).
- Security reports: see `SECURITY.md` (do not use public issues).
