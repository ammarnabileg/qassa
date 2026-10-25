# Changelog

Release versions follow `MAJOR.MINOR.PATCH` and are tagged `vX.Y.Z` on `main`.
Builds between releases are **debug** builds: `X.(Y+1).0-dev.N+sha` (see `scripts/version.py`).

## [Unreleased]
### Added
- Flutter customer app (`mobile/`), one app for all salons (D-001 picker): salon code / `?salon=` link → salon name, theme by business type (kids/men/women), active branches with call and WhatsApp; Arabic RTL / English LTR; same build serves as the per-salon PWA.
- `GET /api/v1/public/salons/<slug>`: public read-only salon profile (suspended salons hidden, throttled 60/min).
- `mobile/tool/build.sh`: debug/release builds stamped from `VERSION`; release refuses to build from an untagged commit.

## [0.1.0] — 2026-10-25 — Phase 1: foundation
### Added
- Django 5.2 LTS backend: identity (Argon2, sessions, CSRF, login rate limit), TOTP MFA for sensitive roles.
- Multi-tenancy: tenant / legal entity / branch / membership; server-side tenant context; composite same-tenant foreign keys in PostgreSQL; per-branch business type (kids / men / women).
- Roles and permissions (25 permissions, 9 role templates) enforced on the server; branch scope.
- Append-only audit log with SHA-256 hash chain.
- Idempotency keys for financial POSTs; transactional outbox with retries; gap-free numbering.
- Accounting core: salon chart of accounts (47), fiscal years/periods, balanced posting, duplicate-event protection, immutable posted entries (DB triggers), reversals, period close/reopen, trial balance by branch.
- OpenAPI 3 spec; React 19 web shell (login + MFA, company & branches, manual journal entry, trial balance) with Arabic RTL / English LTR translation keys.
- `seed_dev` synthetic data (refuses to run in production).
### Decisions
- See `docs/DECISIONS.md` (D-001 store publishing, D-002 unofficial WhatsApp, D-003 WhatsApp OTP).
- D-004: work on `main`; release/debug version scheme; `/api/v1/version`; version shown in web console.
- Payment provider deferred to the end of the project (cash / card terminal / transfer recorded manually until then).
