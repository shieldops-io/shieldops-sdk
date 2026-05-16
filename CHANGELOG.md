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

## [0.1.4] - 2026-05-15

Cross-framework parity release. Closes dogfood wart #6 once the CrewAI
spike at `sdk/examples/crewai_app.py` confirmed the same denial-payload
pattern reproduces in a third framework (FastAPI + Flask + CrewAI). No
breaking changes; the legacy `ShieldOpsDeniedError(tool_name=..., reasons=...,
risk_score=...)` constructor still emits a 4-field `to_dict()` shape when
`request_id` is omitted.

### Added

- **`ShieldOpsDeniedError.to_dict()`** — canonical denial payload helper.
  Returns a JSON-serialisable dict with `tool_name`, `action="deny"`,
  `risk_score`, `reasons`, and (when set) `request_id`. Lets HTTP adapters
  emit the same 4-or-5-field shape across FastAPI, Flask, and CrewAI
  instead of each hand-rolling the conversion.
- **`ShieldOpsDeniedError.request_id`** field. The interceptor now plumbs
  the Decision's `request_id` through to the exception (both `check` and
  `async_check` paths) for end-to-end trace correlation. Direct
  `ShieldOpsDeniedError(...)` construction without `request_id` keeps the
  legacy behaviour — the field stays empty and is omitted from
  `to_dict()` output.
- **`sdk/examples/crewai_app.py`** — CrewAI `BaseTool` subclass that
  re-raises `ShieldOpsDeniedError` as a `RuntimeError(json.dumps(exc.to_dict()))`.
  Doubles as the cross-framework parity proof — was the third-framework
  signal needed to promote wart #6 from hold to fixed.

### Changed

- `sdk/examples/flask_app.py` and `sdk/examples/fastapi_app.py` now call
  `exc.to_dict()` instead of hand-rolling the denial body. The Flask demo
  also stops using `abort()` (which renders the dict as a stringified
  HTML body) in favour of `return jsonify(exc.to_dict()), 403`.

### Internal

- 11 new tests in `tests/test_exceptions.py` (`TestDeniedErrorToDict` +
  `TestDeniedErrorRequestId`); 201 → 212 passing total.

## [0.1.3] - 2026-05-14

Ergonomics-only follow-on to `0.1.2`. No breaking changes. Three paper-cuts
identified in `docs/sdk/dogfood_0_1_2.md` (FastAPI + Flask cross-framework
reproduction) are fixed:

### Added

- **`ScopeStats.duration_ms`** — computed property exposing the scope
  duration in milliseconds (`duration_s * 1000.0`). `duration_s` is
  retained for backwards compatibility. Telemetry exporters and
  human-readable JSON responses should prefer `duration_ms`, which avoids
  the scientific-notation rendering (`7.09e-05`) that `duration_s` produces
  for sub-millisecond scopes. (Dogfood wart #4.)
- **`ShieldOpsInterceptor.from_env()` one-shot startup banner** —
  `logger.info("shieldops.interceptor.from_env mode=… telemetry=… api_key=set|unset")`
  is emitted once per `from_env()` call so silent misconfigs are visible at
  app boot without forcing `strict=True`. Direct `ShieldOpsInterceptor(config)`
  construction stays silent. The `api_key` value is never logged. (Dogfood
  wart #3.)
- **`@interceptor.guard()` unguardable-tool_name `UserWarning`** —
  emitted at decoration time when the resolved `tool_name` is not in
  `effective_blocked_patterns | effective_high_risk_patterns` AND no
  `extra_*_patterns` are configured on the `ShieldOpsConfig`. Surfaces the
  silent-no-op footgun documented in dogfood entry #1 (default
  `tool_name = fn.__qualname__` is exact-match, almost never lines up with
  the bare-name patterns like `"drop_table"`). Suppressed when the user
  has signalled custom policy via `extra_*_patterns`. (Dogfood wart #1.)

### Internal

- New `TestScopeStatsDurationMs`, `TestGuardUnknownToolNameWarning`,
  `TestFromEnvBanner` test classes; 8 new tests (191 → 199 passing).
- Existing decorator-mechanics test classes now use
  `pytest.mark.filterwarnings("ignore:.*guard\\(\\) resolved tool_name.*:UserWarning")`
  at the class level so they don't trip the new warning while exercising
  decorator wiring.

## [0.1.2] - 2026-05-14

First user-visible feature release. Three small additions that make
integration cleaner. No breaking changes to the public API.

### Added

- **`ShieldOpsConfig.from_env(*, strict=False, **overrides)`** — explicit
  factory exposing the env-loading that already happens inside
  `model_post_init`. Kwargs override env values.
- **`ShieldOpsInterceptor.from_env(*, strict=False, **overrides)`** — thin
  one-liner wrapper. `interceptor = ShieldOpsInterceptor.from_env()`.
- **`SHIELDOPS_TELEMETRY`** env var (LOCAL | REMOTE | OTLP), mirroring
  the existing `SHIELDOPS_MODE` handling.
- **`strict=True`** raises `ShieldOpsConfigError` (new exception type) on:
  unparseable `SHIELDOPS_MODE`, unparseable `SHIELDOPS_TELEMETRY`,
  `telemetry=REMOTE` with no `api_key`, any unrecognized `SHIELDOPS_*` env
  var.
- **`@interceptor.guard(*, tool_name=None)`** decorator — wraps any sync
  or async function with firewall interception. Args are extracted via
  `inspect.signature.bind` so policy patterns that key on parameter names
  see the right value regardless of call style.
- **Per-scope stats on ctx mgr** — `with interceptor as scope: ...`
  yields a `ScopeStats { calls, denials, duration_s, mode }` populated
  on exit. Same shape for `async with`. The old no-op stub is gone.
- **`ScopeStats`** dataclass exported via `from shieldops_sdk import ScopeStats`.

### Fixed

- Latent `model_post_init` bug where `SHIELDOPS_MODE=audit` would
  override an explicit `ShieldOpsConfig(mode=ENFORCE)`. Now uses
  `__pydantic_fields_set__` so explicit kwargs always win.

### Internal

- 26 new tests across the from_env + ctx mgr + guard surfaces (165 → 191
  passing total). 2 sigstore-staging tests still CI-only.

## [0.1.1] - 2026-05-13

Pipeline-fix release. No SDK behaviour changes — same public API, same
default semantics. `0.1.0` proved publish + install + import end-to-end
against production PyPI; this release validates the verify-published
smoke-test fix on a fresh version.

### Fixed

- **release pipeline** — `verify-published` job's import smoke test now
  passes a `ShieldOpsConfig` to `ShieldOpsInterceptor`. The 0.1.0 release
  hit `TypeError: missing 1 required positional argument: 'config'`
  because the smoke-test one-liner instantiated `ShieldOpsInterceptor()`
  with no args. PyPI publish itself was unaffected (#668).
- **release pipeline** — `verify-published` install pin now strips the
  `-rcN` suffix from the resolved tag so RC rehearsals install the
  actual wheel version that PyPI accepted (#667).
- **release pipeline** — `publish` job decoupled from the buggy
  `slsa-github-generator` `final` reporter, which hard-fails with
  `SUCCESS=false` on v2.0.0 and v2.1.0 even when provenance + upload
  succeed (#666). Provenance still runs in parallel.

### Internal

- New `test_packaging.py` fences: pre-1.0 version invariant,
  CHANGELOG-coherence (mirrors release.yml prepare-job validation), and
  the verify-published smoke-test invariant codified as a unit test.

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
