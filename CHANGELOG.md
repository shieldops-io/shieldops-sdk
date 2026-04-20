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

## [1.1.0] - 2026-04-20

### Removed

- **BREAKING**: Deleted framework adapter deprecation shims introduced in
  RFC #434 PR-2/3/4 — the deprecation window has elapsed. The following
  top-level modules are gone; importing them now raises
  `ModuleNotFoundError`:
  - `shieldops.sdk.langchain` → use `shieldops.sdk.adapters.langchain`
  - `shieldops.sdk.crewai` → use `shieldops.sdk.adapters.crewai`
  - `shieldops.sdk.llamaindex` → use `shieldops.sdk.adapters.llamaindex`

  Closes RFC #434 PR-6.

## [1.0.0] - 2026-07-14

v1.0 GA. Framework integrations for LangChain, CrewAI, LlamaIndex. Bundle
runtime loader. Audit + enforce modes.

## [0.9.0-pre] - 2026-04-17

Pre-release carve-out of `sdk/` from ShieldOps monorepo. Apache-2.0 license.
