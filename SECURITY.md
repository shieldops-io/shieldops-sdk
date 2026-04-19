# Security Policy

The ShieldOps team takes the security of `shieldops-sdk` seriously. This
document describes how to report vulnerabilities, what is in scope, and what
you can expect from us in return.

## Reporting a vulnerability

Please report suspected vulnerabilities by email to
**security@shieldops.io**. Do not open a public GitHub issue, pull request,
or discussion for security matters.

For sensitive reports, encrypt your message with our PGP key:

- Fingerprint: `TBD-REPLACE-AT-ORG-SETUP`
- Public key: published at `https://shieldops.io/.well-known/pgp-key.asc`
  once the organization account is provisioned.

Include as much of the following as you can:

- A description of the vulnerability and its impact
- Steps to reproduce (minimal proof-of-concept preferred)
- The affected version of `shieldops-sdk`
- Your name and contact details (if you would like credit)

## Coordinated disclosure

We follow a **90-day coordinated disclosure window**. You agree to give us
up to 90 days from the date of report to investigate, develop a fix, and
coordinate a release before any public disclosure. We will work with you
on the disclosure timeline and credit.

## Response SLAs

| Severity | Acknowledgement | Target patch |
|----------|-----------------|--------------|
| Critical | 24 hours        | 7 days       |
| High     | 72 hours        | 30 days      |
| Medium   | 1 week          | 90 days      |
| Low      | 1 week          | Best effort  |

Acknowledgement means a human has triaged the report and confirmed receipt.
Target patch is the time from triage to a fixed release on PyPI. Timelines
are best-effort targets and may shift for reports that require upstream
fixes, cross-project coordination, or extensive validation.

## Scope

**In scope:**

- Code in this repository (`shieldops-sdk` Python package, including
  framework integrations, SDK runtime, audit/enforce logic, bundle loader).
- Vulnerabilities in the SDK's default dependencies declared in
  `pyproject.toml`.
- Documented examples in `examples/`.

**Out of scope for this repository:**

- Server-side ShieldOps API issues (control plane, dashboard, agent fleet).
  Report those to `security@shieldops.io` separately and mention the
  control plane in your subject line.
- Vulnerabilities in third-party frameworks (LangChain, CrewAI,
  LlamaIndex) that are not triggered by SDK code.
- Issues that require an attacker who has already compromised the host,
  the Python environment, or a privileged credential.

## Safe harbor

We welcome good-faith security research. If you make a good-faith effort
to comply with this policy, we will:

- Consider your research lawful and authorized under this policy.
- Not pursue or support legal action against you for your research.
- Work with you to understand and resolve the issue quickly.

A bug bounty program is not yet live; monetary rewards are **TBD**. We
will publicly credit researchers (with permission) in the `CHANGELOG.md`
release notes for the patched version.

### Safe harbor exclusions

Safe harbor does **not** apply to:

- Denial-of-service testing against production services without prior
  written arrangement.
- Social engineering of ShieldOps employees, contractors, or users.
- Physical attacks against ShieldOps offices or personnel.
- Accessing data, accounts, or systems that do not belong to you.
- Any activity that violates applicable law.

## Supported versions

Security fixes land on the latest minor release line and, for critical
issues, are backported to the previous minor for up to 6 months after a
new minor ships.

| Version | Supported |
|---------|-----------|
| 1.0.x   | Yes       |
| 0.9.x   | Pre-release, best effort |
| < 0.9   | No        |

## Contact

- Security reports: `security@shieldops.io`
- General questions: GitHub Discussions (non-security only)
