# Qassa POS — قصّة POS

Multi-tenant POS, booking and accounting system for kids', men's and women's salons in Kuwait.

| Part | Stack | Folder |
|---|---|---|
| Backend API | Python 3.13, Django 5.2 LTS, DRF 3.18, PostgreSQL 16, Redis, Celery | `backend/` |
| Web (back-office, POS, finance) | React 19 + TypeScript + Vite (Node 22) | `frontend/` |
| Customer app | Flutter (phase 6) | `mobile/` (not started) |
| Design & decisions | | `docs/ARCHITECTURE.md` |
| API spec (OpenAPI 3) | generated | `docs/openapi.yaml` |
| UI reference (old static demo — **not** production code) | HTML/JS | `reference/salon-pos-demo/` |

## Run locally

**With Docker:** `docker compose up` → web on http://localhost:5173, API on http://localhost:8000/api/docs/

**Without Docker** (PostgreSQL 16 and Redis 7 running locally):

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r backend/requirements-dev.txt
cd backend
python manage.py migrate
python manage.py seed_dev          # synthetic data, development only — refuses to run in production
python manage.py runserver 8000
# another terminal
cd frontend && npm install && npm run dev
```

Dev users after `seed_dev` (password printed by the command, default `Dev-Only-Pass-2026`):
`owner@mykids.dev` (requires MFA setup), `accountant@mykids.dev`, `financemanager@mykids.dev`,
`cashier@mykids.dev`, `branchmanager@mykids.dev` — same pattern for `gentle.dev` (men) and `lamsa.dev` (women).

## Tests

```bash
cd backend && pytest            # needs PostgreSQL (creates test_qassa)
cd frontend && npm test && npx tsc -b
```

## Ground rules

- Tenant-scoped data is read through `Model.objects` (always filtered by the server-side tenant context). `Model.unscoped` is an explicit, reviewed escape hatch.
- Money is `Decimal` / `numeric(18,3)`; floats are rejected. The frontend does money math in integer fils (`src/money.ts`).
- The general ledger is written only by `apps.accounting.services.posting.post_entry`. Posted entries are immutable (DB triggers); corrections are reversals.
- Every financial POST needs an `Idempotency-Key` header.
- UI text uses translation keys (`src/i18n/ar.json`, `en.json`); a test fails if the two files diverge.
- Secrets come from the environment (`.env.example`). Never commit real values.
