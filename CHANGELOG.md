# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

### Changed

### Fixed

### Removed

### Deprecated

### Security

## [0.1.0] - 2026-05-10

First public release. Local-first by default — `ShieldOpsConfig()` with no
arguments makes zero network attempts and requires no credentials. Opt in to
remote telemetry explicitly via `telemetry=SDKTelemetry.REMOTE`.

### Added

- `shieldops_sdk.experimental` namespace for unstable framework integrations.
  Importing anything from it emits a one-time `UserWarning`. Currently houses
  `experimental.autogen` (Microsoft AutoGen) and `experimental.openai_agents`
  (OpenAI Agents SDK).
- `ShieldOpsConfig.extra_blocked_patterns` and
  `ShieldOpsConfig.extra_high_risk_patterns` — opt-in extension of the
  built-in policy catalogue without subclassing or monkey-patching. Merged
  with the SDK defaults at interceptor construction.
- `SDKTelemetry` enum (`LOCAL` | `REMOTE` | `OTLP`) and
  `ShieldOpsConfig.telemetry` field — telemetry destination is now an axis
  distinct from `mode` (block vs. audit).

### Changed

- **BREAKING**: default `telemetry` is `SDKTelemetry.LOCAL`. Previously,
  setting `api_key` alone caused `async_check()` to POST to the ShieldOps
  backend implicitly. Network calls now require BOTH `api_key` set AND
  `telemetry=SDKTelemetry.REMOTE`. Setting only `api_key` falls back to
  local evaluation — a deliberately safer default (no implicit network on
  credentials alone).
- `ShieldOpsTelemetry.flush()` routes by `(telemetry, api_key)`:
  - `REMOTE` + `api_key` set → POST batched spans to
    `{endpoint}/api/v1/firewall/spans`
  - `LOCAL` or empty `api_key` → clean no-op, drains batch counter only
  - `OTLP` → relies on `record_span()`-time OTLP push; `flush()` drains the
    batch counter
- Block decision in `interceptor.check()` is now strictly a function of
  `(mode, policy)` — independent of `telemetry` and `api_key`. Locked by a
  parametrized 12-cell matrix in `tests/test_telemetry_modes.py`.

### Internal

- Policy default catalogues moved from `interceptor.py` module-level sets
  into a private `shieldops_sdk._policy/` package. Defaults are now
  `frozenset` (immune to accidental global mutation). The
  `effective_blocked_patterns(config)` and
  `effective_high_risk_patterns(config)` helpers centralise the
  defaults-∪-extras merge so future callbacks/feature additions reuse one
  implementation instead of duplicating merge logic.

### Removed

- Module-level `_DEFAULT_BLOCKED_PATTERNS` and `_HIGH_RISK_PATTERNS` symbols
  from `shieldops_sdk.interceptor` (they were underscore-private, never
  part of the public API). Import from `shieldops_sdk._policy._defaults`
  instead if your code reached into the old names.

## [0.9.0-pre] - 2026-04-17

Pre-release carve-out of `sdk/` from ShieldOps monorepo. Apache-2.0 license.
