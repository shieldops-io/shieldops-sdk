# Roadmap

This roadmap describes where `shieldops-sdk` is going at a milestone level.
It is intentionally short on dates and long on intent — the public version
ladder, not the sprint board. Concrete release notes live in
[CHANGELOG.md](CHANGELOG.md); planned issues live in the GitHub tracker.

The SDK follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Until we reach `1.0.0`, the public API may evolve between minor releases;
breaking changes are always called out in the changelog under a
`### Changed` heading with the **BREAKING** marker.

## Current — `0.1.x` (Beta)

The first public release line. The SDK is local-first by default: zero
network calls, zero credentials required, policy evaluation runs in
process. Remote telemetry is strictly opt-in.

Goals during `0.1.x`:

- Bug-fix and documentation polish; no public API breakage.
- Hold the line on the local-first invariant — every new code path must be
  safe to run without an `api_key` set.
- Promote framework integrations out of `experimental` as they stabilize
  (LangChain, CrewAI, LlamaIndex are already stable; AutoGen and
  OpenAI Agents remain experimental).

## Near term — `0.2.x` through `0.5.x`

The "shape it for production" window. Expect minor releases roughly
quarterly; breaking changes are allowed but each one ships with a
migration note.

Focus areas:

- **Telemetry ergonomics.** First-class OTLP path with sensible defaults
  so existing OpenTelemetry collectors work without bespoke wiring.
- **Policy catalogue.** Harden and document the default blocked/high-risk
  pattern sets; expose composition helpers so downstream users can layer
  organisational policy on top without subclassing the interceptor.
- **Coverage.** CI runs on Linux, macOS, and Windows for every supported
  Python version (currently 3.12+; we follow upstream Python deprecation).
- **Performance budget.** Pin a per-call overhead target for the
  interceptor and add benchmarks that fail CI on regression.

## Pre-GA — `0.9.x` (release candidates)

Stabilisation window before `1.0.0`. The intent is *no new features* — the
public API is frozen, the change surface is small, and each `0.9.z` exists
to retire risk:

- Public API freeze: any change requires a deprecation cycle.
- Independent security review of the SDK surface.
- PyPI Trusted Publishing rotation rehearsed end-to-end.
- Documentation review pass with at least one external contributor.

## GA — `1.0.0`

Semantic versioning guarantees on every public symbol. Breaking changes
after `1.0.0` require a `2.0` major and a deprecation window of at least
one minor release. The [SECURITY.md](SECURITY.md) supported-versions
matrix becomes load-bearing — `1.0.x` is supported, prior `0.x` lines
move to end-of-life on a published schedule.

## Beyond `1.0`

Direction, not commitments:

- Streaming/incremental telemetry export for long-running agent sessions.
- Authoring tools for policy-as-code (lint, simulate, diff against
  production traffic).
- Exploration of language bindings beyond Python. This is a research
  question, not a roadmap item — and would only happen if the Python API
  has settled and there is clear demand.

## How priorities change

Roadmap items are not promises. Security work always preempts feature
work, and we will reshuffle in response to community feedback, regulatory
shifts, or upstream framework changes. If a milestone in this document
matters to you, open a discussion or issue so we can weigh it in.
