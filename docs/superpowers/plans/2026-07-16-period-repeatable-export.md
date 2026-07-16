# Repeatable Period Exports Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the export center list every business period and allow the same period to be exported repeatedly as a complete current snapshot without regressing workflow state.

**Architecture:** Keep the existing export tables and audit models. Change eligibility queries from “never exported” to “currently approved,” add a read-only period summary endpoint, and render a compact period table above the existing detail table. Repeated downloads create new audit batches; status transitions are guarded so only the first export advances a record.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, openpyxl, React, TypeScript, Vite, Node test runner, pytest.

## Global Constraints

- Implement in the isolated `lxc/pricing-review-edit` worktree, whose lineage matches the current production front-stage flow.
- Do not merge or overwrite `lxc/listing-observation-workbench`; that branch diverged at `8d40d116` and has unresolved overlaps in `App.tsx`, services, schemas, API types, CSS, tests, and docs.
- Do not deploy development or production in this plan. Deployment/integration requires a separate explicit decision after verified commits exist.
- Do not add a database table, Alembic migration, runtime dependency, or saved Excel binary snapshot.
- Keep both existing Excel templates, sheet grouping, headers, and row fields unchanged.
- Keep manager-only authorization on all export endpoints.
- Exclude disabled opportunities, source prefill claims, unreviewed rejects, and claims with missing/non-positive daily sales.
- Each repeated download records a new `ExportBatch` and `ExportRow`; it must not move a claim or opportunity backward from a later workflow state.

---

## File Map

- `backend/app/services.py`: approved-row eligibility, idempotent export state transition, and period summary aggregation.
- `backend/app/schemas.py`: business period on export rows and `ExportPeriodSummary` response model.
- `backend/app/routers/stocking.py`: read-only `/stocking/export-periods` route and existing period-bound download routes.
- `backend/tests/test_stocking_export.py`: repeat-download and state-regression coverage.
- `backend/tests/test_traceability_export.py`: repeat not-claim export and period summary coverage.
- `frontend/src/api.ts`: `ExportPeriodSummary` type and API method.
- `frontend/src/exportPeriods.ts`: small pure helpers for current-period selection, filtering, and required period filter construction.
- `frontend/tests/exportPeriods.test.ts`: frontend period behavior tests.
- `frontend/src/App.tsx`: state loading and export-center period table.
- `frontend/src/styles.css`: compact period table and active-row styling.
- `frontend/package.json`: include the new test file in the existing Node test command.
- `AGENT_HANDOFF.md`, `docs/02-功能实现状态.md`, `docs/2026-07-09-已确认需求记录.md`: durable rule and implementation status updates.

### Task 1: Make Existing Export Queries Repeatable And State-Safe

**Files:**
- Modify: `backend/tests/test_stocking_export.py`
- Modify: `backend/tests/test_traceability_export.py`
- Modify: `backend/app/services.py:1496-1682`
- Modify: `backend/app/routers/stocking.py`

**Interfaces:**
- Consumes: existing `list_available_stocking_items`, `list_not_claim_traceability_rows`, and `record_export_batch`.
- Produces: the same public HTTP parameters; internal one-time exclusion arguments are removed, selection is based on current approval, and repeated state transitions are idempotent.

- [ ] **Step 1: Add the failing repeat-download test**

Add this test to `backend/tests/test_stocking_export.py`:

```python
def test_stocking_export_repeats_current_rows_without_regressing_later_status() -> None:
    opportunity_id = prepare_approved_claims([("销售A", 2.5)])

    first = client.get("/stocking/available-list/export?business_period=BATCH-EXPORT")
    assert first.status_code == 200

    with SessionLocal() as db:
        claim = db.query(models.SalesClaimForecast).filter_by(opportunity_id=opportunity_id).one()
        claim.downstream_status = "waiting_secondary_research"
        db.commit()

    second = client.get("/stocking/available-list/export?business_period=BATCH-EXPORT")
    assert second.status_code == 200
    workbook = load_workbook(BytesIO(second.content), data_only=True)
    assert workbook["PH"].max_row == 2

    with SessionLocal() as db:
        claim = db.query(models.SalesClaimForecast).filter_by(opportunity_id=opportunity_id).one()
        rows = db.query(models.ExportRow).filter_by(claim_record_id=claim.id).all()
        assert claim.downstream_status == "waiting_secondary_research"
        assert len(rows) == 2
```

Add a second test proving that approvals added after the first download join the next complete export:

```python
def test_repeat_export_includes_newly_approved_rows_in_the_same_period() -> None:
    prepare_approved_claims([("销售A", 1)], main_sku="MAIN-FIRST", sub_sku="SUB-FIRST", source_row=1)
    first = client.get("/stocking/available-list/export?business_period=BATCH-EXPORT")
    assert first.status_code == 200

    prepare_approved_claims([("销售B", 2)], main_sku="MAIN-LATER", sub_sku="SUB-LATER", source_row=2)
    second = client.get("/stocking/available-list/export?business_period=BATCH-EXPORT")

    workbook = load_workbook(BytesIO(second.content), data_only=True)
    assert {workbook["PH"][f"F{row}"].value for row in range(2, workbook["PH"].max_row + 1)} == {
        "MAIN-FIRST",
        "MAIN-LATER",
    }
```

Add a preservation test for the existing disable guard:

```python
def test_repeatable_exports_still_exclude_disabled_opportunities() -> None:
    opportunity_id = prepare_approved_claims([("销售A", 1)])
    with SessionLocal() as db:
        opportunity = db.get(models.NewProductOpportunity, opportunity_id)
        assert opportunity is not None
        opportunity.current_status = "disabled"
        db.commit()

    response = client.get("/stocking/available-list?business_period=BATCH-EXPORT")

    assert response.status_code == 200
    assert response.json() == []
```

Rename `test_traceability_export_records_not_claim_rows_once` to `test_traceability_export_records_each_repeat_download` and change its final assertions to:

```python
assert len(exported) == 2
assert {row.main_sku for row in exported} == {"MAIN-NOT-CLAIM-ONCE"}
assert len({row.export_batch_id for row in exported}) == 2
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run from `backend`:

```powershell
E:\Project\Hengzhe-New-Product-Workflow\.venv\Scripts\python.exe -m pytest tests/test_stocking_export.py::test_stocking_export_repeats_current_rows_without_regressing_later_status tests/test_stocking_export.py::test_repeat_export_includes_newly_approved_rows_in_the_same_period tests/test_stocking_export.py::test_repeatable_exports_still_exclude_disabled_opportunities tests/test_traceability_export.py::test_traceability_export_records_each_repeat_download -q
```

Expected: the three repeat-download assertions fail because earlier `ExportRow` records are excluded; the disable-guard preservation test already passes.

- [ ] **Step 3: Remove one-time exclusion from the shared eligibility functions**

In `list_available_stocking_items`, keep only current business eligibility in the SQL filters:

```python
filters = [
    models.NewProductOpportunity.current_status != OPPORTUNITY_DISABLED,
    models.SalesClaimForecast.claim_result == CLAIM_RESULT_CLAIM,
    models.SalesClaimForecast.claim_daily_sales.is_not(None),
    models.SalesClaimForecast.claim_daily_sales > 0,
    models.SalesClaimForecast.source_column == "platform",
]
```

Delete the exported-claim subquery, exported-ID filter, downstream-status filter, and final visible-status rejection. Replace that final check with the explicit approval guard:

```python
review = latest_approved_review_for_claim(db, opportunity.id, claim.id)
if review is None:
    continue
```

In `list_not_claim_traceability_rows`, delete its exported-claim subquery and exported-ID filter. Keep `claim_result == reject`, `source_column == platform`, period filters, and latest `confirmed_not_claim` review enforcement.

Remove `exclude_exported_scope` from both service signatures and remove `exclude_exported_scope="traceability"` from the traceability router call. No public query parameter changes.

- [ ] **Step 4: Guard first-export state transitions**

Replace the unconditional claim update in `record_export_batch` with:

```python
claim = db.get(models.SalesClaimForecast, item.claim_record_id)
if claim and claim.downstream_status in (None, CLAIM_WAITING_EXPORT):
    claim.downstream_status = CLAIM_WAITING_ARRIVAL
```

Only update and audit an opportunity when it is still at the pre-export state:

```python
if opportunity and opportunity.current_status == OPPORTUNITY_READY_FOR_STOCKING:
    opportunity.current_status = OPPORTUNITY_WAITING_ARRIVAL
    audit(
        db,
        "opportunity.waiting_arrival",
        "new_product_opportunity",
        opportunity_id,
        {"export_batch_id": batch.id},
        exported_by,
    )
```

- [ ] **Step 5: Run focused backend tests and verify GREEN**

Run the Step 2 command again.

Expected: `4 passed`; the second workbooks contain all current approved rows, each download has its own audit rows, the later claim state remains unchanged, and disabled opportunities stay excluded.

- [ ] **Step 6: Commit Task 1**

```powershell
git add backend/app/services.py backend/app/routers/stocking.py backend/tests/test_stocking_export.py backend/tests/test_traceability_export.py
git commit -m "fix: allow repeatable current exports"
```

### Task 2: Add Business-Period Export Summaries

**Files:**
- Modify: `backend/app/schemas.py:313-335`
- Modify: `backend/app/services.py`
- Modify: `backend/app/routers/stocking.py`
- Modify: `backend/tests/test_traceability_export.py`

**Interfaces:**
- Produces: `GET /stocking/export-periods -> list[ExportPeriodSummary]`.
- Produces: `AvailableStockingItem.business_period: str | None`; imported production rows have a value, while legacy period-less rows remain visible only through their existing APIs and cannot trigger an unscoped download.
- Response item: `{business_period, latest_imported_at, stocking_count, traceability_count}`.

- [ ] **Step 1: Add the failing period-summary test**

Add `from datetime import datetime, timezone` to `backend/tests/test_traceability_export.py`, then add:

```python
def test_export_periods_list_every_imported_period_with_current_counts() -> None:
    with SessionLocal() as db:
        db.add_all(
            [
                models.ImportBatch(source_type="selection1", source_sheet="S29", business_period="2026年第29期", imported_at=datetime(2026, 7, 1, tzinfo=timezone.utc)),
                models.ImportBatch(source_type="selection1", source_sheet="S30", business_period="2026年第30期", imported_at=datetime(2026, 7, 8, tzinfo=timezone.utc)),
                models.ImportBatch(source_type="selection1", source_sheet="S31", business_period="2026年第31期", imported_at=datetime(2026, 7, 15, tzinfo=timezone.utc)),
            ]
        )
        db.commit()

    prepare_approved_claim(business_period="2026年第29期", source_row=1, main_sku="MAIN-29", sub_sku="SUB-29")
    prepare_reject_claim(source_sheet="S29", business_period="2026年第29期", source_row=2, main_sku="REJECT-29", review_status="confirmed_not_claim")
    prepare_approved_claim(business_period="2026年第30期", source_row=3, main_sku="MAIN-30", sub_sku="SUB-30")

    response = client.get("/stocking/export-periods")

    assert response.status_code == 200
    assert [
        (row["business_period"], row["stocking_count"], row["traceability_count"])
        for row in response.json()
    ] == [
        ("2026年第31期", 0, 0),
        ("2026年第30期", 1, 1),
        ("2026年第29期", 1, 2),
    ]
```

- [ ] **Step 2: Run the summary test and verify RED**

```powershell
E:\Project\Hengzhe-New-Product-Workflow\.venv\Scripts\python.exe -m pytest tests/test_traceability_export.py::test_export_periods_list_every_imported_period_with_current_counts -q
```

Expected: FAIL with `404 Not Found` because `/stocking/export-periods` does not exist.

- [ ] **Step 3: Add response fields and aggregation**

Add `business_period: str | None = None` to `AvailableStockingItem` and populate it from `opportunity.batch`.

Add this schema:

```python
class ExportPeriodSummary(BaseModel):
    business_period: str
    latest_imported_at: datetime | None = None
    stocking_count: int = 0
    traceability_count: int = 0
```

Add `list_export_period_summaries(db)` after `list_not_claim_traceability_rows`. It must:

1. Query non-disabled `ImportBatch.business_period` values grouped by period and ordered by `max(imported_at) DESC`.
2. Call the now-repeatable `list_available_stocking_items(db)` and `list_not_claim_traceability_rows(db)` once each.
3. Count stocking items by `item.business_period`; count confirmed rejects by `opportunity.batch`.
4. Preserve imported period order, append any current-data periods missing from `ImportBatch` in lexical order, and return `traceability_count = stocking_count + confirmed_reject_count`.

Use existing `defaultdict` and SQLAlchemy `func`; add no dependency and no new query abstraction.

- [ ] **Step 4: Add the manager-only read route**

Add before `/available-list` in `backend/app/routers/stocking.py`:

```python
@router.get("/export-periods", response_model=list[schemas.ExportPeriodSummary])
def list_export_periods(db: Session = Depends(get_db)) -> list[schemas.ExportPeriodSummary]:
    return services.list_export_period_summaries(db)
```

- [ ] **Step 5: Run the period and export regression tests**

```powershell
E:\Project\Hengzhe-New-Product-Workflow\.venv\Scripts\python.exe -m pytest tests/test_stocking_export.py tests/test_traceability_export.py tests/test_product_board.py -q
```

Expected: all tests pass; the summary is newest-first, includes the zero-count imported period, and the product board still moves first exports to the existing visible state.

- [ ] **Step 6: Commit Task 2**

```powershell
git add backend/app/schemas.py backend/app/services.py backend/app/routers/stocking.py backend/tests/test_traceability_export.py
git commit -m "feat: summarize exports by business period"
```

### Task 3: Render The Period Export Workbench

**Files:**
- Create: `frontend/src/exportPeriods.ts`
- Create: `frontend/tests/exportPeriods.test.ts`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/package.json`
- Modify: `frontend/tests/reviewLayout.test.ts`

**Interfaces:**
- Consumes: `GET /stocking/export-periods`, existing period-filtered download methods, and `AvailableStockingItem.business_period`.
- Produces: latest-period default, current-period detail filtering, required period download filters, and one busy state per download button.

- [ ] **Step 1: Write the failing pure helper tests**

Create `frontend/tests/exportPeriods.test.ts`:

```typescript
import assert from "node:assert/strict";
import test from "node:test";

import { exportPeriodFilter, filterRowsForExportPeriod, selectExportPeriod } from "../src/exportPeriods.ts";

const periods = [
  { business_period: "开发0714期", stocking_count: 2, traceability_count: 3 },
  { business_period: "开发0707期", stocking_count: 1, traceability_count: 1 }
];

test("默认选择后端返回的最新期并保留仍存在的当前期", () => {
  assert.equal(selectExportPeriod(periods, ""), "开发0714期");
  assert.equal(selectExportPeriod(periods, "开发0707期"), "开发0707期");
  assert.equal(selectExportPeriod(periods, "不存在"), "开发0714期");
});

test("明细和下载都强制绑定一个业务期数", () => {
  const rows = [{ business_period: "开发0714期", claim_record_id: "A" }, { business_period: "开发0707期", claim_record_id: "B" }];
  assert.deepEqual(filterRowsForExportPeriod(rows, "开发0707期").map((row) => row.claim_record_id), ["B"]);
  assert.deepEqual(exportPeriodFilter("开发0714期"), { business_period: "开发0714期" });
  assert.throws(() => exportPeriodFilter(""), /请选择业务期数/);
});
```

Append `tests/exportPeriods.test.ts` to the existing `frontend/package.json` test command.

Add this failing interaction contract to `frontend/tests/reviewLayout.test.ts`:

```typescript
test("导出中心按期展示且不保留无范围导出按钮", () => {
  const stockView = app.slice(app.indexOf("function StockView"), app.indexOf("function ArrivalPreviewView"));

  assert.match(stockView, /export-periods-table/);
  assert.match(stockView, /period\.stocking_count\s*<=\s*0/);
  assert.match(stockView, /period\.traceability_count\s*<=\s*0/);
  assert.match(stockView, /exportPeriodFilter\(period\.business_period\)/);
  assert.doesNotMatch(stockView, /api\.traceabilityExport\(\)/);
  assert.doesNotMatch(stockView, /api\.availableStockingExport\(\)/);
});
```

- [ ] **Step 2: Run the helper tests and verify RED**

Run from `frontend`:

```powershell
npm test
```

Expected: FAIL because `frontend/src/exportPeriods.ts` does not exist.

- [ ] **Step 3: Add the minimum pure helpers**

Create `frontend/src/exportPeriods.ts`:

```typescript
export type ExportPeriodLike = { business_period: string };
export type ExportPeriodRowLike = { business_period?: string | null };

export function selectExportPeriod(periods: readonly ExportPeriodLike[], current: string) {
  return current && periods.some((period) => period.business_period === current)
    ? current
    : periods[0]?.business_period || "";
}

export function filterRowsForExportPeriod<T extends ExportPeriodRowLike>(rows: readonly T[], businessPeriod: string): T[] {
  return businessPeriod ? rows.filter((row) => row.business_period === businessPeriod) : [];
}

export function exportPeriodFilter(businessPeriod: string) {
  if (!businessPeriod) throw new Error("请选择业务期数");
  return { business_period: businessPeriod };
}
```

- [ ] **Step 4: Add API types and state loading**

In `frontend/src/api.ts`, add `business_period?: string | null` to `AvailableStockingItem`, add:

```typescript
export type ExportPeriodSummary = {
  business_period: string;
  latest_imported_at?: string | null;
  stocking_count: number;
  traceability_count: number;
};
```

and add `exportPeriods: () => request<ExportPeriodSummary[]>("/stocking/export-periods")` beside the existing stocking methods.

In `App.tsx`, add `exportPeriods` state, clear it on logout, load it in `refresh`, and pass it with `setStatusMessage` into `StockView`. Keep the existing global refresh/error aggregation pattern.

- [ ] **Step 5: Replace ambiguous global export buttons with the period table**

In `StockView`:

- Initialize `selectedPeriod` with `selectExportPeriod(periods, current)` in an effect.
- Filter the existing detail rows with `filterRowsForExportPeriod(rows, selectedPeriod)` before applying search and pagination.
- Render a compact table with columns `业务期数 / 海外仓备货表 / 中央字段追溯表 / 操作`.
- Render `查看明细`, `导出海外仓表`, and `导出中央追溯表` buttons on each period row.
- Disable a file button when its count is zero or that exact download is busy.
- Await the existing API download method with `exportPeriodFilter(period.business_period)`; report success/failure through `onStatus` and always clear the busy key in `finally`.
- Remove the two unscoped export buttons so the UI cannot download all periods accidentally.
- Keep the existing 16-column detail table and `ListControls`; change empty messages to refer to the selected period.

Use existing `btn`, `primary`, `tag`, `table-wrap`, `Download`, and state patterns. Add no modal, card nesting, custom icon, or dependency.

- [ ] **Step 6: Add compact, non-scrolling period-table styles**

Add styles scoped to `.export-periods-wrap`, `.export-periods-table`, `.export-period-row.active`, and `.export-period-actions`. Override the global table minimum only for this table:

```css
.export-periods-table {
  min-width: 720px;
}

.export-period-row.active td {
  background: #eef6ff;
}

.export-period-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
```

Keep radius at `8px` or less and ensure button labels wrap instead of forcing page-level horizontal overflow.

- [ ] **Step 7: Run frontend tests and build**

```powershell
npm test
npm run build
```

Expected: all Node tests pass and TypeScript/Vite production build exits `0`.

- [ ] **Step 8: Commit Task 3**

```powershell
git add frontend/package.json frontend/src/api.ts frontend/src/exportPeriods.ts frontend/src/App.tsx frontend/src/styles.css frontend/tests/exportPeriods.test.ts frontend/tests/reviewLayout.test.ts
git commit -m "feat: add period export workbench"
```

### Task 4: Full Verification And Durable Documentation

**Files:**
- Modify: `AGENT_HANDOFF.md`
- Modify: `docs/02-功能实现状态.md`
- Modify: `docs/2026-07-09-已确认需求记录.md`
- Modify: `docs/superpowers/plans/2026-07-16-period-repeatable-export.md`
- Append: `C:/Users/86173/.codex/work-logs/2026-29.md`

**Interfaces:**
- Produces: verified branch commits and a handoff that explicitly says no server was deployed.

- [ ] **Step 1: Run complete local verification**

From `backend`:

```powershell
E:\Project\Hengzhe-New-Product-Workflow\.venv\Scripts\python.exe -m pytest -q
```

From `frontend`:

```powershell
npm test
npm run build
```

From the worktree root:

```powershell
git diff --check
git status --short
```

Expected: backend full suite passes, frontend tests/build pass, `git diff --check` is empty, and only intentional documentation changes remain.

- [ ] **Step 2: Reconcile durable docs with `neat-freak`**

Record these exact facts in the authoritative docs:

- Export center lists all non-disabled imported business periods newest-first, including zero-count periods.
- Repeated downloads contain all currently approved rows for that period.
- Every download creates a new audit batch; repeated downloads do not regress later statuses.
- No database migration, template change, production deployment, or development deployment occurred.
- `lxc/listing-observation-workbench` remains a separate divergent line and was not overwritten.

Do not duplicate implementation detail into unrelated business documents and do not delete or merge conflicting docs without user approval.

- [ ] **Step 3: Mark this plan complete and commit docs**

Mark completed checkboxes only after their commands passed, then run:

```powershell
git add AGENT_HANDOFF.md docs/02-功能实现状态.md docs/2026-07-09-已确认需求记录.md docs/superpowers/plans/2026-07-16-period-repeatable-export.md
git commit -m "docs: record repeatable period exports"
```

- [ ] **Step 4: Append the weekly work log**

Append one entry to `C:/Users/86173/.codex/work-logs/2026-29.md` with project, implementation summary, changed files, exact test totals, commit IDs, no-deployment statement, and the unresolved branch-integration follow-up. Do not include credentials or environment secrets.

- [ ] **Step 5: Final branch review**

```powershell
git log -5 --oneline --decorate
git status --short --branch
```

Expected: clean `lxc/pricing-review-edit`, ahead of origin by the intentional design/plan/implementation/docs commits; production remains at `b373d65` until the user explicitly requests release.
