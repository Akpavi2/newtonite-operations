# Engineering Decisions

## 1. FastAPI + server-rendered static frontend

**Context:** The assessment allows one working day and values correctness over decorative complexity. **Options:** a React SPA, a full-stack framework, or a small API with static HTML/CSS/JavaScript. **Choice:** FastAPI serves the frontend assets and JSON API, with no frontend build step. **Trade-off:** the app is quick to run and review, but frontend state and components are less structured than a larger React application.

## 2. SQLite for the assessment, with SQLAlchemy models

**Context:** A reviewer should be able to start the application locally without configuring a separate database service. **Options:** PostgreSQL, SQLite, or an in-memory store. **Choice:** SQLite plus SQLAlchemy, with indexes on team, status, priority, assignee and activity lookups. **Trade-off:** minimal setup and persistent local data, but SQLite is not the right database for high-volume multi-instance production workloads. PostgreSQL is the planned scale-up path.

## 3. Team-scoped authorization on the server

**Context:** Hiding a button does not prevent someone from calling an API directly. **Options:** UI-only checks, global roles, or server-side team membership checks. **Choice:** every resource route checks the current user's membership in the item's team and role for the action. A non-member receives 404 for item reads to avoid confirming that another team's item exists. **Trade-off:** checks are repeated in service helpers, but the trust boundary is explicit and testable.

## 4. Atomic claims and optimistic locking

**Context:** two people may claim the same item or edit a stale copy. **Options:** client-side checks, pessimistic locking, or conditional updates with a version counter. **Choice:** claims use one conditional database update where `assignee_id IS NULL`; edits/transitions include a version and update only when that version matches. Conflicts return HTTP 409. **Trade-off:** clients must refresh after a conflict, but the database—not the UI—decides which write wins. SQLite's write-concurrency profile remains a limitation at larger scale.

## 5. Idempotency and atomic activity history

**Context:** clients can retry after a timeout, and audit history must not disagree with the work item. **Options:** assume requests are sent once, record history after commit, or store request keys and history inside the same transaction. **Choice:** create requests can include an `Idempotency-Key`; a unique record points to the created item. Item mutations and activity events are committed together. **Trade-off:** keys need a retention policy in a larger deployment, and the current implementation handles task-creation idempotency rather than every mutation endpoint.

## Workflow assumptions

- Items begin in `Open`.
- Allowed transitions are explicit in `app/main.py`.
- `Awaiting Approval` to `Resolved` requires a Lead or Admin of the item's team.
- Viewers are read-only; Members can work on items in their team; Leads and Admins have additional assignment/approval permissions.
- Items and activity are only visible to team members.

## Next improvements

Move to PostgreSQL with migrations, add refresh/revocation for sessions, improve user/assignee labels, add a transactional outbox worker and notification retries, add due-date reminders, and expand concurrency tests against PostgreSQL.
