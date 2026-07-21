# Sales-self stocking Task 5 report

Date: 2026-07-21
Scope: Task 5 frontend workbench plus the follow-up operator-country response contract; no server, production, credential, or environment changes.

## Implemented

- Kept the existing `stock` route and made its label role-aware: operators see `备货申请`, managers see `导出中心`.
- Added the operator stocking workbench with main-SKU grouping, status/source/country/search filters, sales-self creation, all three decision branches, two-column request forms, ERP volume preview with manual fallback, draft save, and submit.
- Preserved selection1/selection2 draft visibility when `needs_stocking` is null; sales-self decision controls are only enabled while the backend allows decision changes.
- Added the manager workbench with business-period/status/query filters, current-filter selection, internal scrolling around the 16-column table, selected `POST /stocking/available-list/export` calls using `{ request_ids }`, and retained period-scoped traceability export.
- Role-gated refresh calls so operators do not request manager-only stocking list/period endpoints.
- Added product-board labels for `waiting_stocking_request`, `waiting_export`, and `stocking_paused`; the ordinary `waiting_listing` path continues to use the existing listing workbench.
- Kept horizontal scrolling inside the manager export table and made only the route-level stock screen consume the available full-width content area without changing global page overflow.

## Independent review follow-up

- Draft saving now sends a nullable update payload without running submit-level completeness checks, so missing ERP volume and other incomplete fields can remain a draft; strict validation still runs before submit and warehouse remains optional.
- Added opportunity `country` to the operator stocking response and used it for operator country options/filtering, including sales-self branches that intentionally have no request.
- Reconciled manager selections against the current filtered available-list rows on refresh and filter changes; export, count, and button state use that visible intersection only.
- Corrected `selection1_developer_claim_feedback` to display as `选品1`.
- Added a dialog name plus accessible names for the sales-self close/delete buttons and child SKU/name/decision controls.

## Files

- `frontend/src/StockingRequestView.tsx`
- `frontend/src/stockingRequests.ts`
- `frontend/src/api.ts`
- `frontend/src/App.tsx`
- `frontend/src/productBoard.ts`
- `frontend/src/styles.css`
- `frontend/tests/stockingRequests.test.ts`
- `frontend/tests/reviewLayout.test.ts`
- `frontend/tests/productBoard.test.ts`
- `frontend/tests/listingObservation.test.ts`
- `frontend/package.json`
- `backend/app/schemas.py`
- `backend/app/services.py`
- `backend/tests/test_stocking_requests.py`

## TDD and verification

- RED: `node tests/stockingRequests.test.ts` failed with `ERR_MODULE_NOT_FOUND` for the not-yet-created `src/stockingRequests.ts`.
- Focused GREEN: `node tests/stockingRequests.test.ts` passed 10/10.
- Related layout/listing checks: `node tests/reviewLayout.test.ts` passed 11/11 and `node tests/listingObservation.test.ts` passed 44/44.
- TypeScript: `npm.cmd exec -- tsc --noEmit` exited 0.
- Full frontend suite: `npm.cmd test` passed 117/117, 0 failed.
- Production build: `npm.cmd run build` exited 0; Vite transformed 80 modules and produced `dist/index.html`, CSS, and JS assets.
- `git diff --check` passed.

Follow-up RED/GREEN and final verification:

- RED frontend: `node tests/stockingRequests.test.ts` exited 1 because `buildStockingDraftUpdate` did not exist yet.
- RED backend: the focused country response test failed because the no-request branch omitted `country`.
- Focused GREEN: stocking request tests passed 14/14; review layout tests passed 11/11; the backend country contract passed 1/1.
- TypeScript: `npm.cmd exec -- tsc --noEmit` exited 0.
- Full frontend suite: `npm.cmd test` passed 121/121, 0 failed.
- Production build: `npm.cmd run build` exited 0; Vite transformed 80 modules.
- `git diff --check` passed after the follow-up.

The Node test runner and Vite required an approved unsandboxed run because Windows sandbox process creation returned `spawn EPERM`; the same repository-local commands then completed successfully.

## Decisions and boundaries

- Reused the existing request/download helpers, layout vocabulary, `stock` route, listing workbench, and product board; no dependency was added.
- The backend production change is limited to adding opportunity `country` to `OperatorStockingItemRead` and `_operator_stocking_item`; no router, model, migration, or write-path behavior changed.
- Only the focused backend operator-country response contract test was run; the full backend suite was intentionally not run.
- No server, deployment, production data, or secret was accessed.

## Documentation impact check

The current design and implementation plan already describe the implemented frontend contract. The Neat Freak audit found older project status/handoff documents that still say sales-self stocking is not implemented, including `docs/README.md`, `docs/00-新会话交接.md`, `docs/02-功能实现状态.md`, `docs/20-项目推进总控.md`, `docs/23-销售自选与备货申请需求对齐.md`, and `docs/2026-07-09-已确认需求记录.md`. They were intentionally not edited because Task 5 explicitly limits documentation writes to this report; the later documentation/status task should reconcile them after the whole workflow milestone is complete.
