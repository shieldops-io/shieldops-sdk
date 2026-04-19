## Summary

One-paragraph description of what this PR changes and why. Focus on the
"why" -- the diff already shows the "what".

## Linked issue

Closes #<issue-number>

(Use `Closes` / `Fixes` for bug fixes, `Refs` for partial work.)

## Tests added

- [ ] Unit tests for new code paths
- [ ] Integration tests updated if public behavior changed
- [ ] Coverage on changed lines is >= 80%
- [ ] `pytest tests/ -v` passes locally

Describe what the new tests cover and how they exercise the change.

## DCO signed

- [ ] Every commit on this branch is signed off with `git commit -s`
      (adds a `Signed-off-by:` trailer). The DCO bot blocks merge
      otherwise. See `CONTRIBUTING.md` for details.

## Breaking change?

- [ ] Yes -- describe the break and the migration path below.
- [ ] No.

If yes: document the before/after API, whether a deprecation period
was offered, and link the RFC issue that approved the break.

## Checklist

- [ ] `ruff check src/ tests/` passes with no new warnings
- [ ] `ruff format --check src/ tests/` passes
- [ ] `pytest tests/ -v --tb=short` passes
- [ ] Type hints on all new public functions and methods
- [ ] Docstrings on all new public classes, functions, and methods
- [ ] `CHANGELOG.md` updated under `[Unreleased]`
- [ ] Documentation updated in `docs/` if public behavior changed
- [ ] No secrets, API keys, or customer data in the diff or tests
