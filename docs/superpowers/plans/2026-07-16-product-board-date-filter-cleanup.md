# Product Board Date Filter Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove only the unlabeled native date picker from the product board while preserving every business-period control.

**Architecture:** Delete the unused UI control and its local-only filter branch. No API, backend, database, listing-workbench, or secondary-research behavior changes.

**Tech Stack:** React, TypeScript, Node test runner, Vite

## Global Constraints

- Keep all business-period filters and period-entry controls.
- Do not change backend or database behavior.
- Add no dependency or abstraction.

---

### Task 1: Remove the product-board arrival-date picker

**Files:**
- Modify: `frontend/tests/productBoard.test.ts`
- Modify: `frontend/src/ProductBoardView.tsx`
- Modify: `frontend/src/productBoard.ts`
- Modify: `docs/2026-07-09-已确认需求记录.md`

**Interfaces:**
- Consumes: `ProductBoardFilters` and `filterProductBoardRows(...)`.
- Produces: The same product-board filtering interface without `arrivalDate`.

- [x] **Step 1: Add a failing UI contract test**

Read `ProductBoardView.tsx` with `node:fs` and assert that it contains `全部期数` but does not contain `type="date"`.

- [x] **Step 2: Run the focused test and confirm failure**

Run: `node --test tests/productBoard.test.ts`

Expected: FAIL because `ProductBoardView.tsx` still contains the native date input.

- [x] **Step 3: Remove the minimum dead code**

Delete the date input from `ProductBoardView.tsx`; delete `arrivalDate` and `dateText(...)` plus the two arrival-date branches from `productBoard.ts`. Do not touch `businessPeriod`.

- [x] **Step 4: Align the requirement record**

Remove “到货日期” from the product-board filter list and state that the unlabeled calendar filter was removed while business-period filtering remains.

- [x] **Step 5: Verify**

Run: `node --test tests/productBoard.test.ts`

Expected: PASS.

Run: `npm test -- --run && npm run build`

Expected: all tests pass and Vite build succeeds.

- [x] **Step 6: Deploy and smoke test development only**

Build and update Compose project `hengzhe-new-product-dev`, then confirm `http://139.224.2.166:18081/api/health` returns `environment=development` and the deployed JS bundle no longer contains the removed date-control code path.
