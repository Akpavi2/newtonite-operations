# Newtonite Operations — Operations Under Pressure

A small internal operations tracker built for the Newtonite Software Engineering Challenge. It supports team-scoped work items, role-based access, a status workflow, activity history, comments, pagination, and safeguards for conflicting or repeated requests.

## Features

- FastAPI backend and SQLite database with SQLAlchemy.
- Secure password hashing (Argon2) and signed, expiring bearer tokens.
- Viewer, Member, Lead and Admin team roles; authorization is checked by API endpoints.
- Work item creation, editing, claiming, comments and activity timeline.
- Server-side search, filters and pagination.
- Atomic claim, optimistic version checks, idempotency keys and transactional activity events.
- Responsive HTML/CSS/vanilla JavaScript dashboard.
- Automated API tests with pytest and a separate temporary test database.

## Requirements

- Python 3.11 or newer.
- Windows PowerShell, macOS Terminal, or Linux shell.

## Run on Windows PowerShell

```powershell
cd newtonite-ops
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000>. API docs are at <http://127.0.0.1:8000/docs> and health check at <http://127.0.0.1:8000/health>.

If PowerShell blocks activation, use `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` in that terminal and activate again, or run `.venv\Scripts\python.exe -m pip install -r requirements.txt` and `.venv\Scripts\python.exe -m uvicorn app.main:app --reload`.

## Demo accounts

These are local demo-only credentials. Change/remove them before deploying publicly.

| Role | Email | Password | Team access |
|---|---|---|---|
| Admin | `admin@newtonite.local` | `AdminDemo!2026` | All seeded teams |
| Lead | `lead@newtonite.local` | `LeadDemo!2026` | Operations |
| Member | `member@newtonite.local` | `MemberDemo!2026` | Operations |
| Viewer | `viewer@newtonite.local` | `ViewerDemo!2026` | Operations (read-only) |
| Member | `finance@newtonite.local` | `FinanceDemo!2026` | Finance |

Seed data is created automatically on the first startup. The local database file is `newtonite.db` in the current working directory. To reset the demo data, stop the server, delete that file, and start the server again.

## Tests

From the project root, with the virtual environment active:

```powershell
python -m pytest -q
```

Tests cover task creation/retrieval, claim conflict handling, stale updates, idempotency, cross-team authorization, invalid workflow transitions, activity history, and Viewer restrictions. Tests create a temporary test database.

## API overview

- `POST /api/auth/login` — authenticate and receive a bearer token.
- `GET /api/me` — current user and memberships.
- `GET /api/dashboard` — dashboard counters.
- `GET /api/items` — paginated search/filter list (`q`, `status`, `priority`, `team_id`, `page`, `page_size`, `assigned_to_me`, `unassigned_urgent`, `awaiting_approval`).
- `POST /api/items` — create; accepts optional `Idempotency-Key` header.
- `GET /api/items/{id}` and `PATCH /api/items/{id}` — view and version-checked update.
- `POST /api/items/{id}/claim` — atomic claim of an unassigned item.
- `POST /api/items/{id}/transition` — validated status transition with version.
- `GET /api/items/{id}/activity` — chronological activity timeline.
- `GET/POST /api/items/{id}/comments` — list/add comments.

All `/api` routes except login require `Authorization: Bearer <token>`.

## GitHub submission

Create a public repository (for example `newtonite-ops-yourrollno`) and run:

```powershell
git init
git add .
git commit -m "Build Newtonite operations tracker"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/newtonite-ops-YOURROLLNO.git
git push -u origin main
```

Replace the remote URL with your real repository URL. Verify the repository page opens before submitting its link through the university's Google Form.

## Known limitations

- SQLite is appropriate for a compact assessment demo; PostgreSQL should replace it for multi-instance production use and higher write concurrency.
- Seeded accounts are for local demonstration, not real identity management. There is no password reset, SSO, MFA, or account provisioning workflow.
- Tokens expire after eight hours; a revocation/refresh-token service is not implemented.
- There is no real-time websocket updates, email notifications, or background outbox worker.
- The frontend uses a small vanilla JavaScript implementation rather than a component framework; user/assignee names are basic demo labels in some list views.
- Due dates are stored as ISO date strings and do not yet have reminder scheduling.
- The demo secret has a development fallback. Set a long random `SECRET_KEY` environment variable before any deployment. Do not expose demo credentials or use this build as-is for sensitive production data.