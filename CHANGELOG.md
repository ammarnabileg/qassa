# Changelog

Release versions follow `MAJOR.MINOR.PATCH` and are tagged `vX.Y.Z` on `main`.
Builds between releases are **debug** builds: `X.(Y+1).0-dev.N+sha` (see `scripts/version.py`).

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
