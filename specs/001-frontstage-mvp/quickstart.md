# Quickstart: Validate Frontstage New Product MVP

## Prerequisites

- Python virtual environment exists at `.venv/`
- Backend dependencies are installed
- Frontend dependencies are installed
- For production-like deployment, `.env` points `DATABASE_URL` to PostgreSQL
- For local tests, pytest may use SQLite test database
- First development target is local. Later production migration target is SSH `root@101.132.26.138:2323`; credentials must not be committed or written into project docs.

## Deployment direction

Develop and verify the MVP locally first. After backend tests, frontend build, and Docker Compose config validation pass locally, migrate the same Compose-based service set to the production server.

Do not store SSH passwords, database passwords, DingTalk credentials, PLM credentials, cookies, or tokens in the repository. Use local secret storage or interactive input during deployment.

## Backend validation

Run backend tests:

```powershell
cd E:\Project\Hengzhe-New-Product-Workflow\backend
..\.venv\Scripts\python.exe -m pytest -q
```

Expected outcome:

- All tests pass
- Import, claim, review, not-claim confirmation, and stocking export scenarios are covered

## Production database guard validation

Run the application with a non-local environment and a SQLite database URL.

Expected outcome:

- The backend refuses to start or raises a clear configuration error
- The error explains that SQLite is only allowed for local/test use

## Import validation

Use a small controlled workbook for each in-scope source:

- `选品1：海外仓开发部门开发新品认领-反馈.xlsx`
- `选品2：海外仓财根团队开发新品认领-反馈.xlsx`

Expected outcome:

- Valid child SKU rows import
- Source file, sheet, row, and snapshot are retained
- Duplicate import updates existing records instead of creating duplicates
- Missing central-only fields remain empty

## Assignment validation

Create multiple child SKUs under the same main SKU and run assignment preview.

Expected outcome:

- The main SKU group stays together
- Suggestions follow key site, key category 1, key category 2, current-load priority
- Supervisor can confirm assignments and create operator claim tasks

## Claim validation

Submit one claimed row and one not-claimed row.

Expected outcome:

- Claim without claim daily sales is rejected
- Not-claim without reason is rejected
- Valid claim creates a review task
- Valid not-claim creates a review task
- Operator-submitted fields keep created/updated timestamps

## Review validation

Review the claimed and not-claimed rows.

Expected outcome:

- Approved claim becomes exportable
- Confirmed not-claim becomes `已确认不认领`
- Confirmed not-claim never appears in stocking export
- Returned-for-supplement returns work to the operator and does not let supervisor edit operator fields

## Export validation

Export approved stocking rows.

Expected outcome:

- Workbook opens in Excel
- Sheet name is `备货申请表`
- Workbook has the 16 columns listed in [contracts/api.md](./contracts/api.md)
- `备货数量` equals `备货单销 × 30`
- `补货原因` is empty
- Same child SKU claimed by multiple approved operators exports as multiple rows

## Latest Validation Results

Recorded on 2026-07-03 Asia/Shanghai:

- Backend: `..\.venv\Scripts\python.exe -m pytest -q` passed with 28 tests.
- Frontend: `npm run build` passed. Vite reported only the bundle-size warning for the generated JS chunk.
- Alembic: empty SQLite smoke `upgrade head` passed through the latest migration.
- Docker Compose: `docker compose config` could not run on this machine because the `docker` CLI is not installed or not on PATH. Re-run this command on a machine with Docker before deployment.
