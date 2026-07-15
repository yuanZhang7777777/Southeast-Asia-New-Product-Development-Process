# Selection1 Detail Field Matching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve Selection1 columns A-BX and let an operator review and complete every child SKU under one main SKU in a single Excel-style claim matrix.

**Architecture:** Reuse the existing opportunity `snapshot`, claim drafts, claim API, and evidence upload API; do not add database tables or API endpoints. The importer stores A-BX plus CC-CH. The claim drawer renders one main-SKU table with child SKUs as rows, source fields as switchable columns, and a fixed claim editor per row.

**Tech Stack:** FastAPI / SQLAlchemy backend, React / TypeScript frontend, pytest, npm build.

## Global Constraints

- Do not commit secrets, server passwords, DingTalk credentials, ERP credentials, cookies, or `.env` files.
- Preserve source-table traceability: every imported record should keep source file, sheet, row, and snapshot metadata.
- Keep MVP narrow and reuse existing models.
- No new runtime dependency.

---

### Task 1: Complete Selection1 Snapshot

**Files:**
- Modify: `backend/app/selection1_importer.py`
- Test: `backend/tests/test_selection1_import.py`

**Interfaces:**
- Produces: importer still returns the existing `Selection1ImportResponse`.
- Produces: opportunity `snapshot` still contains `cells`, `fields_by_column`, `fields_by_header`, `pricing_snapshot`.

- [x] Add a failing import test requiring M, AW, and BX in `snapshot.cells` and `A:BX,CC:CH` traceability.
- [x] Store A-BX plus CC-CH while preserving header-first market and pricing aliases.
- [x] Run the focused import test and confirm pass.

### Task 2: Main-SKU Claim Matrix

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`
- Create: `frontend/src/claimDrafts.ts`
- Test: `frontend/tests/claimDrafts.test.ts`

**Interfaces:**
- Consumes: `Opportunity.snapshot.fields_by_header`
- Consumes: `Opportunity.snapshot.fields_by_column`
- Produces: compact A-L summary, module order Z-AN / AO-AV without AQ / M-Y / AW-BX, child-SKU rows, fixed claim inputs, and evidence upload.

- [x] Add a failing test proving a claimed first child is not overwritten when a second child rejects and fills pending siblings.
- [x] Move reject synchronization into a tested helper and reuse existing claim drafts.
- [x] Replace single-child detail switching with the main-SKU matrix.
- [x] Keep evidence upload inside every child-SKU claim row.
- [ ] Run the frontend test and production build after final cleanup.

### Task 3: Docs And Deploy

**Files:**
- Modify: `docs/21-后半段需求领导对齐问题清单.md`

**Interfaces:**
- Produces: documented confirmed rule that selection1 detail sections are header-first with column fallback.

- [x] Record the confirmed detail section rules in this existing plan without creating another handoff document.
- [ ] Run backend focused tests and frontend build.
- [ ] Deploy current code to the existing cloud dev service on port 8080.
