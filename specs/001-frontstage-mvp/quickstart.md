# Quickstart: Validate Frontstage New Product MVP

## Prerequisites

- Python virtual environment exists at `.venv/`
- Backend dependencies are installed
- Frontend dependencies are installed
- For production-like deployment, `.env` points `DATABASE_URL` to PostgreSQL
- For local tests, pytest may use SQLite test database
- Deployment target for current validation is only the isolated development environment `http://139.224.2.166:18081` via SSH alias `hz-new-product-dev`. Do not connect, restart or deploy production `101.132.26.138` without a separate approved release window.

## Deployment direction

Develop and verify locally first, then back up and deploy the candidate only to the isolated development Compose stack. Run the final full backend suite, Linux frontend build, Compose validation, migration read-back and browser UAT there. Production promotion is a separate, explicitly approved task.

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

- Approved claim creates an operator-owned stocking-request draft and is not exportable until the operator submits it
- Confirmed not-claim becomes `已确认不认领`
- Confirmed not-claim never appears in stocking export
- Returned-for-supplement returns work to the operator and does not let supervisor edit operator fields

## Stocking-request validation

Use the authenticated operator account to save and submit a draft.

Expected outcome:

- Draft can be incomplete while saved, but submission requires positive cost, unit volume and daily sales
- ERP lookup uses the child SKU; failure returns “manual required” and allows a positive manual volume
- Source-table aggregate `包装后体积` is not silently prefilled
- `备货数量 = ceil(备货单销 × 30)`
- `备货仓库` may be blank; `补货原因` is required only for `补货`
- Editing a submitted request before export reopens it as draft and requires resubmission

## Export validation

As manager, select only submitted requests from the current available list and export them.

Expected outcome:

- Workbook opens in Excel
- Workbook contains country sheets and the 16 columns listed in [contracts/api.md](./contracts/api.md)
- Only explicitly selected, still-eligible requests are exported; one invalid row rejects the entire batch
- `备货数量` equals `ceil(备货单销 × 30)`
- `补货原因` is empty for `首次备货` and populated for `补货`
- Same child SKU submitted by multiple approved operators exports as independent rows
- Successful export records immutable `ExportBatch + ExportRow` snapshots and advances only those requests to `exported / waiting_arrival`

## Latest Validation Results

Recorded on 2026-07-21 Asia/Shanghai for the uncommitted local candidate:

- Backend: 37 focused stocking-request/export/PLM/demo tests passed. A broader run also passed 49 tests before the Windows sandbox denied pytest's own `tmp_path`; final full regression remains required in the development Linux container.
- Frontend: all 16 test files passed when run directly, 122 tests total; `npx tsc --noEmit` passed. Local Vite build is blocked by the same Windows child-process sandbox and must run in Linux.
- Alembic: source has one head, `d0e2f3a4b567`; development still runs `a8d4e6f7b901` until an approved deployment.
- Development deployment, Compose validation, migration read-back and browser UAT remain pending. Production was not touched.