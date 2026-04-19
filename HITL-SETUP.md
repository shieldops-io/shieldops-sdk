# HITL setup checklist for the public `shieldops-sdk` repo

This file lists every action the founder must do **by hand** before or
during the carve-out of `sdk/` into its own public repository. The
automation in this directory cannot do any of these -- each step
requires human credentials, legal judgement, or external account
creation.

Work top to bottom. Items are grouped so you can schedule them across
a few sessions.

## 1. GitHub organization

- [ ] **Register the `shieldops` GitHub organization.** ~15 min.
      Fallbacks if the handle is taken: `shieldops-ai`, `shieldops-sec`.
      Document the chosen handle in `README.md`, `CONTRIBUTING.md`,
      `SECURITY.md`, `CODEOWNERS`, `ISSUE_TEMPLATE/config.yml`, and
      `ci.yml` (anywhere `shieldops/shieldops-sdk` appears).
      <https://github.com/organizations/plan>

- [ ] **Upgrade the org to GitHub Team plan** (paid). ~5 min.
      Required for protected branches on private repos and for team
      mentions in `CODEOWNERS`. Free tier is not sufficient once the
      main ShieldOps monorepo joins the org.
      <https://docs.github.com/en/billing/managing-billing-for-your-github-account/about-billing-for-github-accounts>

- [ ] **Create the `maintainers` and `security` teams.** ~5 min.
      Invite the initial team members. Update `CODEOWNERS` to replace
      `@ghantakiran` with `@shieldops/maintainers` and
      `@shieldops/security` where appropriate.

- [ ] **Invite core team members.** ~10 min per person.
      Set 2FA-required at the org level before inviting.

## 2. Repository and branch protection

- [ ] **Create the public `shieldops/shieldops-sdk` repo.** ~5 min.
      Push the carved-out `sdk/` contents to `main`. Enable the MIT
      badge-free default social preview.

- [ ] **Configure branch protection on `main`.** ~10 min. Require:
      - Pull request before merge, with **1 review approval**.
      - Status checks: `test (py3.12 / ubuntu-latest)` and
        `DCO sign-off check` (from `ci.yml`).
      - Linear history (no merge commits on `main`).
      - Signed commits optional now, required after Sigstore work.
      - Dismiss stale reviews when new commits are pushed.
      <https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/defining-the-mergeability-of-pull-requests/managing-a-branch-protection-rule>

- [ ] **Enable Discussions.** ~2 min. Route usage questions there so
      GitHub Issues stays focused on bugs and features. Update the URL
      in `.github/ISSUE_TEMPLATE/config.yml` once the discussions tab
      is live.

- [ ] **Enable Dependabot alerts + security updates.** ~2 min.
      Repo Settings -> Code security and analysis.

## 3. Security disclosure plumbing

- [ ] **Generate a PGP key for `security@shieldops.io`.** ~20 min.
      Use a hardware-backed key (YubiKey or equivalent) if available.
      Replace the `TBD-REPLACE-AT-ORG-SETUP` placeholder in
      `SECURITY.md` with the actual 40-char fingerprint.
      Publish the public key at
      `https://shieldops.io/.well-known/pgp-key.asc` and keep a copy
      on keys.openpgp.org.

- [ ] **Stand up the `security@shieldops.io` inbox.** ~15 min.
      Route it to a small triage group, not an individual. Configure
      auto-reply referencing the 90-day disclosure window and the
      acknowledgement SLA table.

- [ ] **Stand up the `conduct@shieldops.io` inbox.** ~5 min.
      Referenced in `CONTRIBUTING.md`. Route to HR + a maintainer.

- [ ] **Decide on bug-bounty stance.** ~30 min.
      `SECURITY.md` currently says bounty is TBD. Pick one of:
      HackerOne private program, Bugcrowd private program, or
      self-hosted with a fixed payout table. Update `SECURITY.md`
      when decided.

## 4. Release + supply chain

- [ ] **Register the `shieldops-sdk` project on PyPI.** ~10 min.
      Reserve the name before v0.9.0-pre ships.

- [ ] **Enable Sigstore trusted publishing on PyPI.** ~20 min.
      Configure the publisher to accept uploads from the
      `shieldops/shieldops-sdk` repo's GitHub Actions, not a long-lived
      PyPI API token.
      <https://docs.pypi.org/trusted-publishers/>

- [ ] **Add a `release.yml` workflow** that builds, signs with Sigstore,
      and uploads on tag push. (Out of scope for this scaffold PR;
      track in a follow-up issue.)

## 5. Bundle distribution (R2 + DNS)

- [ ] **Provision a Cloudflare R2 bucket for bundle distribution.** ~20 min.
      Name suggestion: `shieldops-bundles-prod`. Enable versioning and
      lifecycle rules per PRD-027.

- [ ] **Create a scoped R2 access token.** ~5 min. Save as GitHub
      Actions secrets in the public repo:
      - `R2_ACCESS_KEY_ID`
      - `R2_SECRET_ACCESS_KEY`
      - `R2_BUCKET_NAME`
      - `R2_ENDPOINT`
      Scope the token to the bundle bucket only; do not reuse across
      environments.

- [ ] **Configure DNS for `bundles.shieldops.io`.** ~15 min.
      Point the CNAME at the R2 custom domain. Set up a Cloudflare
      WAF rule that only serves signed URLs on the bundle paths.

- [ ] **Verify end-to-end**: push a test bundle, fetch via SDK loader,
      confirm Sigstore signature verification passes. ~30 min.

## 6. Community and optional accounts

- [ ] **Set up GitHub Sponsors (optional).** ~20 min.
      Lets community contributors back individual maintainers. Not
      required for launch.

- [ ] **Create a `@shieldops` handle on Twitter/X, Bluesky, Mastodon.** ~15 min total.
      Link from the org page. Use consistent branding.

- [ ] **Stand up a `shieldops/community` repo for RFCs.** ~15 min.
      Major breaking changes require an RFC per `CONTRIBUTING.md`.

## 7. Legal

- [ ] **Confirm Apache-2.0 is the right license for every file in `sdk/`.**
      ~30 min. Walk every source file, check for borrowed code, update
      headers where required. We use DCO not CLA, so external patches
      are in under Apache-2.0 by sign-off.

- [ ] **Run a trademark sweep on "ShieldOps".** ~varies.
      Confirm there is no conflicting mark in the security-software
      class before public launch.

- [ ] **Decide on attribution of any third-party code snippets.** ~1 hour.
      Audit `docs/` and `examples/` for copy-pasted content from
      framework vendors. Add `NOTICE` file if anything is retained.

## 8. Pre-launch smoke checks

- [ ] Fresh `pip install shieldops-sdk==0.9.0-pre` on all supported
      Python versions (3.10, 3.11, 3.12) on Linux + macOS.
- [ ] Clone the public repo into a clean environment, run
      `pip install -e ".[dev]"` and `pytest tests/ -v`. Everything
      green.
- [ ] Open a test issue with each template, confirm labels and
      assignees fire correctly.
- [ ] Open a test PR without DCO sign-off, confirm the check blocks
      merge.
- [ ] Run a test security email to `security@shieldops.io` from an
      outside account, confirm the triage group receives it.

## Estimated total effort

About **8-12 hours of focused work**, spread across a week. The PGP
key setup, bug-bounty decision, and trademark sweep are the most
open-ended items -- start them first.
