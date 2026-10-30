# Changelog

Release versions follow `MAJOR.MINOR.PATCH` and are tagged `vX.Y.Z` on `main`.
Builds between releases are **debug** builds: `X.(Y+1).0-dev.N+sha` (see `scripts/version.py`).

## [Unreleased]

## [0.2.0] — 2026-10-30
### Added — dashboards, reports, settings (design screens v-home, v-rep, v-c-home, v-c-rep, v-set, v-p-set)
- Branch home (today, queue, latest invoices), company home (every branch today and this month), reports with branch comparison, best sellers, staff, payment methods, peak hours and a profit summary (cost-permission only).
- Salon receipt settings (header, footer, commercial registration) and CSV export of customers and invoices (audited).
- Platform settings: sales WhatsApp, support e-mail, site headline and trial length (no longer only environment variables).
- Customer app: points and active packages on the account screen.
- Staging-only test accounts without MFA (`E2E_PASSWORD`), closed when the variable is removed.
### Added — MOCI report
- Cash flow statement (indirect method, reconciled to the change in cash) and statement of changes in equity.
### Added — Offline till (D-013)
- The till keeps selling when the internet drops: catalogue snapshot in the browser, the app shell opens offline, every receipt numbered per device and HMAC-signed.
- Automatic sync when the connection returns: posted once, at the real sale time and drawer; promotions no longer valid are kept as reviewed discounts; conflicts can be retried; missing receipt numbers are reported.
- Offline receipts page for managers (review, retry, devices, missing numbers).
### Fixed
- The till header date used the device's time zone instead of Kuwait's.
### Added — Platform console and public site (D-010)
- Platform home with real figures (active/trial/past-due salons, MRR, invoiced per month, plan mix, renewals, open tickets).
- Monthly subscription invoices issued nightly (one per period), manual payment with reference, void with reason; overdue → past_due (never auto-suspended).
- Support tickets between salons and the platform team; owner notified on WhatsApp from the platform number when available.
- Leads from the public site's contact form (honeypot, 5/hour per IP); public site per the approved design with pricing from the live plans.
- Read-only, one-hour, audited "view as support" access with a written reason.
### Added — Phase 5 (accounting, D-011)
- Expenses paid or accrued, with later payment; fixed assets with monthly straight-line depreciation (example 12); KNET / gateway settlements (example 11).
- Income statement, balance sheet, period close (blocked by open drawers), reopen with reason, year-end closing entry.
- Frozen report versions with a SHA-256 fingerprint, immutable in the database.
### Added — Phase 6 (D-012)
- Automatic WhatsApp service messages from the salon's number: booking confirmation/change, reminder (1–48 h), receipt — opt-in customers only.
### Fixed
- Prices set between 00:00 and 04:00 Kuwait time were not sellable until the next business day.
- 50+ server error codes showed "unknown error"; every code now has a message (enforced by a test).
- Public site scrolled sideways on phones.
### Added — Phase 4 (stock, purchasing, loyalty, commissions)
- Products and stock per branch at weighted-average cost, never negative; adjustments with reason; stock moves log.
- Purchasing: goods receipt → supplier bill (must equal the receipt) → bank payment, with proposed journal entries.
- Session packages (contract liability, revenue per session used), coupons, loyalty points; all priced by the server (`/pos/quote`).
- Tips to a staff member (tips payable); commission % per staff member, accrued on net service value, reversed on returns, paid out by bank.
- Staff working hours and time off, enforced in booking and free slots; reschedule a booking.
- Returns can put products back in stock; receipts show tip and points.
- Users: invite / edit / resend; set-password page; forgot-password link.
- MOCI XBRL draft statements (financial position, profit or loss) with account mapping and CSV export (D-009).
### Removed
- Front-desk one-time customer login link (owner decision; see D-003).
### Added — customer app (D-006)
- Login first: phone + WhatsApp code (hashed, expiring, attempt-limited, throttled), registration with children.
- Booking flow per the approved design: service → branch (nearest suggested) → day/staff/time → who → confirm; my bookings with cancel; account with children.
- Branch location, opening hours and online-booking switch; free slots from hours and staff skills.
### Fixed
- Wrong OTP attempts were rolled back with the error and not counted (found by tests before release).
- Booking times shown in the device time zone instead of the salon's.
### Added — Phase 3 (operations)
- Bookings and walk-in queue on one board (waiting / on the chair / done), multi-service visits, PostgreSQL exclusion constraint against double-booking a staff member.
- Checkout (POS) priced by the server's price list, line discounts within the role limit, cash / KNET / transfer / split, credit sales with permission, printable receipt and WhatsApp link.
- Invoices list, collections on credit invoices, returns as credit notes with optional refund.
- Cash drawer shifts: one open drawer per branch, expected vs counted, variance approved by a second person.
- Automatic journal entries (proposed matrix, pending the accountant's review): invoice, receipts, refunds, credit notes, cash over/short.
- Issued invoices, payments and credit notes are immutable in the database.
- Customer app restyled on the approved design (Alexandria font, tokens, per-type logo).
### Added — Phase 2 (setup)
- Services and categories per business type; prices as dated rows (no backdating, DB constraint against overlaps, branch overrides).
- Staff with branches and skills (services they deliver).
- Customers (guardians) with beneficiaries (self / children); Kuwait phone normalisation; search by name, phone or child.
- Plans from the approved design (Basic 15, Pro 29, Chains 69 KWD) with branch/staff limits enforced on the server; platform staff change plan/status with an audited reason.
- Per-company customer app host: automatic subdomain, custom domain on plans that allow it (D-005).
- Back-office rebuilt on the approved design system (same CSS, Alexandria font, icons, themes per business type); platform console.
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
