# Maintainers

This document lists the people who maintain `shieldops-sdk` and describes
what maintainer responsibility means in practice. It is the source of
truth that [.github/CODEOWNERS](.github/CODEOWNERS) and the GitHub team
configuration are kept in sync with.

## Current maintainers

| Name | GitHub | Areas |
|------|--------|-------|
| Kiran Reddy Ghanta | [@ghantakiran](https://github.com/ghantakiran) | All — initial maintainer, primary contact for the public carve and the `0.1.x` line |

The SDK is young and the maintainer roster is small on purpose. One of
the explicit goals on the road to `1.0.0` (see [ROADMAP.md](ROADMAP.md))
is to grow this list to at least three active maintainers, so that bus
factor is not one.

## What maintainers do

Maintainers are the people accountable for the health of the project.
Concretely, that means:

- **Review and merge.** Approve pull requests, request changes, and merge
  once CI is green and CODEOWNERS are satisfied.
- **Release.** Cut tagged releases, write the changelog entry, and shepherd
  the PyPI publish workflow (Trusted Publishing via OIDC — see
  [.github/workflows/publish.yml](.github/workflows/publish.yml)).
- **Triage.** Label and route issues, close stale or out-of-scope reports,
  and escalate security reports per [SECURITY.md](SECURITY.md).
- **Steward direction.** Keep [ROADMAP.md](ROADMAP.md) honest; say no to
  scope creep; protect the local-first default.
- **Enforce conduct.** Apply the [Code of Conduct](CODE_OF_CONDUCT.md) when
  needed, reviewing reports sent to `conduct@shieldops.io`.

Maintainers are expected to be responsive on a best-effort basis (we are
not a 24×7 on-call rotation) and to disclose conflicts of interest when
they arise — for example, reviewing a PR that touches code their employer
depends on.

## Becoming a maintainer

We do not have a formal "contributor → committer → maintainer" ladder
yet. The current pathway is informal but transparent:

1. Show up. Land non-trivial pull requests, help with reviews, answer
   issues, improve docs.
2. Take ownership of an area. Demonstrate working knowledge of one part
   of the codebase (a framework integration, the telemetry layer, the
   policy catalogue, CI, etc.).
3. Nomination. An existing maintainer proposes the addition in a public
   GitHub issue. Other maintainers acknowledge within two weeks. If
   nobody objects, the nomination passes by lazy consensus. Objections
   are discussed openly and resolved before any addition.
4. Onboarding. The new maintainer is added to CODEOWNERS, the GitHub
   maintainers team, and this document in the same pull request.

We will formalise this process once the maintainer count is larger than
two and the current ad-hoc approach starts to creak.

## Stepping down

Maintainers may step down at any time by opening a pull request that
moves their entry to the "Emeritus" section below. There is no stigma
attached — projects outlive any individual contributor, and an honest
hand-off is more valuable than a quiet drift away.

If a maintainer becomes unresponsive for an extended period (no public
activity for roughly six months, and no reply to direct outreach), the
remaining maintainers may move them to Emeritus by lazy consensus so
that CODEOWNERS reviews are not blocked.

## Emeritus

_None yet._
