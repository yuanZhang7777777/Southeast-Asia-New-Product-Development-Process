# Tasks: Frontstage New Product MVP

**Input**: Design documents from `specs/001-frontstage-mvp/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/api.md](./contracts/api.md), [quickstart.md](./quickstart.md)

**Tests**: Required. Project rules require TDD for behavior changes: write failing backend tests before production code, then implement the smallest passing change.

**Organization**: Tasks are grouped by user story so each story can be implemented and validated as an independent increment.

## Phase 1: Setup and Safety

**Purpose**: Lock the technical baseline before adding more workflow behavior.

- [X] T001 Add a failing configuration test that non-local environments reject SQLite in `backend/tests/test_config.py`
- [X] T002 Implement the non-local SQLite guard in `backend/app/config.py`
- [X] T003 Add Alembic to backend dependencies in `backend/requirements.txt` and `backend/requirements-dev.txt`
- [X] T004 Initialize migration structure under `backend/alembic/` and `backend/alembic.ini`
- [X] T005 Create the initial PostgreSQL-compatible migration for existing workflow tables in `backend/alembic/versions/`
- [X] T006 Update `.env.example` to document PostgreSQL as production storage and SQLite as test-only storage
- [X] T007 Run `backend` tests with `..\.venv\Scripts\python.exe -m pytest -q`

---

## Phase 2: Foundational Workflow Model

**Purpose**: Add shared model and status vocabulary needed by all user stories.

**Critical**: Complete this phase before adding new import, assignment, claim, review, or export behavior.

- [X] T008 Add failing model tests for import batches, export batches, and export rows in `backend/tests/test_workflow_models.py`
- [X] T009 Add `ImportBatch`, `ExportBatch`, and `ExportRow` models in `backend/app/models.py`
- [X] T010 Add schemas for import batch summaries and export batch metadata in `backend/app/schemas.py`
- [X] T011 Create status constants for opportunity, claim, task, and review states in `backend/app/workflow_status.py`
- [X] T012 Replace hard-coded status strings in `backend/app/services.py` with `backend/app/workflow_status.py`
- [X] T013 Add a migration for new foundational tables and status-related columns in `backend/alembic/versions/`
- [X] T014 Run `backend` tests with `..\.venv\Scripts\python.exe -m pytest -q`

**Checkpoint**: Database and shared workflow vocabulary are ready.

---

## Phase 3: User Story 1 - Import Feedback Tables (Priority: P1)

**Goal**: Import the two approved feedback workbooks with source traceability and central-field alignment.

**Independent Test**: Import a small selection1 fixture and a small selection2 fixture, then verify opportunity rows, source snapshots, import batch counts, and idempotent re-import.

### Tests for User Story 1

- [X] T015 [P] [US1] Add selection1 import batch and source traceability tests in `backend/tests/test_selection1_import.py`
- [X] T016 [P] [US1] Add selection2 Caigen import tests in `backend/tests/test_selection2_import.py`
- [X] T017 [P] [US1] Add central-field-mapping default-empty tests in `backend/tests/test_field_mapping.py`

### Implementation for User Story 1

- [X] T018 [US1] Extend `backend/app/selection1_importer.py` to create `ImportBatch` records and attach `import_batch_id` to snapshots
- [X] T019 [US1] Create reusable field mapping helpers in `backend/app/field_mapping.py`
- [X] T020 [US1] Create `backend/app/selection2_importer.py` for `选品2：海外仓财根团队开发新品认领-反馈.xlsx`
- [X] T021 [US1] Add `Selection2ImportRequest` and `SelectionImportResponse` reuse in `backend/app/schemas.py`
- [X] T022 [US1] Add `POST /opportunities/import/selection2` in `backend/app/routers/opportunities.py`
- [X] T023 [US1] Ensure duplicate source file + sheet + row updates existing opportunities in `backend/app/selection2_importer.py`
- [X] T024 [US1] Ensure unmatched central-table target fields remain empty instead of `0` in `backend/app/field_mapping.py`
- [X] T025 [US1] Run user-story tests with `..\.venv\Scripts\python.exe -m pytest tests/test_selection1_import.py tests/test_selection2_import.py tests/test_field_mapping.py -q`

**Checkpoint**: Both first-version feedback tables can enter the platform with traceability.

---

## Phase 4: User Story 2 - Supervisor Assignment (Priority: P1)

**Goal**: Generate one-click assignment suggestions by main SKU group and let the supervisor confirm assignments.

**Independent Test**: Use a fixture personnel workbook and multiple main SKU groups to verify site/category/load priority and task creation.

### Tests for User Story 2

- [X] T026 [P] [US2] Add personnel config import tests in `backend/tests/test_personnel_config.py`
- [X] T027 [P] [US2] Add assignment rule priority tests in `backend/tests/test_assignment_rules.py`
- [X] T028 [P] [US2] Add assignment confirmation task tests in `backend/tests/test_assignment_flow.py`

### Implementation for User Story 2

- [X] T029 [US2] Create `backend/app/personnel_importer.py` for `集团八部销售员信息表.xlsx`
- [X] T030 [US2] Add operator assignment profile model fields or table in `backend/app/models.py`
- [X] T031 [US2] Add migration for operator assignment profiles in `backend/alembic/versions/`
- [X] T032 [US2] Implement main-SKU-group assignment scoring in `backend/app/assignment_rules.py`
- [X] T033 [US2] Update `preview_assignments` in `backend/app/services.py` to use site, category1, category2, and current main-SKU-group load
- [X] T034 [US2] Update `confirm_assignment` in `backend/app/services.py` so one main SKU group creates claim tasks for all child SKUs under the confirmed assignee
- [X] T035 [US2] Update `backend/app/routers/assignments.py` request/response fields for match reason and main SKU group preview
- [X] T036 [US2] Run assignment tests with `..\.venv\Scripts\python.exe -m pytest tests/test_personnel_config.py tests/test_assignment_rules.py tests/test_assignment_flow.py -q`

**Checkpoint**: Supervisor can preview and confirm assignment by main SKU group.

---

## Phase 5: User Story 3 - Operator Claim Or Not Claim (Priority: P1)

**Goal**: Operators can submit claim or not-claim decisions with required fields, timestamps, and Caigen multi-claim support.

**Independent Test**: Submit claim, not-claim, invalid claim, invalid not-claim, and multiple Caigen self-claims for the same child SKU.

### Tests for User Story 3

- [X] T037 [P] [US3] Add claim validation tests in `backend/tests/test_claim_validation.py`
- [X] T038 [P] [US3] Add operator field timestamp tests in `backend/tests/test_claim_timestamps.py`
- [X] T039 [P] [US3] Add Caigen multi-claim tests in `backend/tests/test_caigen_opportunity_pool.py`

### Implementation for User Story 3

- [X] T040 [US3] Extend `SalesClaimForecast` in `backend/app/models.py` with source, task linkage, first-submitted, and last-updated fields
- [X] T041 [US3] Add migration for claim metadata fields in `backend/alembic/versions/`
- [X] T042 [US3] Update `ClaimCreate` in `backend/app/schemas.py` to include note and self-claim source when needed
- [X] T043 [US3] Update `submit_claim` in `backend/app/services.py` to enforce required fields and preserve first-created / last-updated timestamps
- [X] T044 [US3] Update `submit_claim` in `backend/app/services.py` to allow unlimited Caigen approved claim records for the same child SKU
- [X] T045 [US3] Update `backend/app/routers/claims.py` error responses for missing claim daily sales and missing not-claim reason
- [X] T046 [US3] Run claim tests with `..\.venv\Scripts\python.exe -m pytest tests/test_claim_validation.py tests/test_claim_timestamps.py tests/test_caigen_opportunity_pool.py -q`

**Checkpoint**: Operator submissions are valid, traceable, and ready for supervisor review.

---

## Phase 6: User Story 4 - Supervisor Review (Priority: P1)

**Goal**: Supervisor reviews submissions without editing operator fields and can approve, confirm not-claim, or return for supplement.

**Independent Test**: Review approved claim, confirmed not-claim, and returned-for-supplement paths.

### Tests for User Story 4

- [X] T047 [P] [US4] Add approved-claim review tests in `backend/tests/test_review_flow.py`
- [X] T048 [P] [US4] Add confirmed-not-claim terminal-state tests in `backend/tests/test_review_flow.py`
- [X] T049 [P] [US4] Add returned-for-supplement tests in `backend/tests/test_review_flow.py`

### Implementation for User Story 4

- [X] T050 [US4] Update `ReviewCreate` in `backend/app/schemas.py` to validate `approved`, `confirmed_not_claim`, and `returned_for_supplement`
- [X] T051 [US4] Update `submit_review` in `backend/app/services.py` to set `ready_for_stocking`, `已确认不认领`, or `returned_for_supplement`
- [X] T052 [US4] Update review task completion and returned task creation in `backend/app/services.py`
- [X] T053 [US4] Add service-level guard tests ensuring review payload cannot modify operator fields in `backend/tests/test_review_flow.py`
- [X] T054 [US4] Update `backend/app/routers/reviews.py` to return clear errors for invalid review statuses
- [X] T055 [US4] Run review tests with `..\.venv\Scripts\python.exe -m pytest tests/test_review_flow.py -q`

**Checkpoint**: Supervisor review produces correct business terminal states.

---

## Phase 7: User Story 5 - Export Approved Stocking Rows (Priority: P1)

**Goal**: Export approved child-SKU claim rows to the official stocking workbook and full-field traceability export.

**Independent Test**: Export a workbook containing approved claims, multiple operators for one child SKU, and confirmed not-claim exclusions.

### Tests for User Story 5

- [X] T056 [P] [US5] Add stocking workbook structure tests in `backend/tests/test_stocking_export.py`
- [X] T057 [P] [US5] Add multi-claim export row tests in `backend/tests/test_stocking_export.py`
- [X] T058 [P] [US5] Add full-field traceability export tests in `backend/tests/test_traceability_export.py`
- [X] T059 [P] [US5] Add export batch metadata tests in `backend/tests/test_export_batch.py`

### Implementation for User Story 5

- [X] T060 [US5] Update `list_available_stocking_items` in `backend/app/services.py` to list approved claim records rather than only latest claim per opportunity
- [X] T061 [US5] Update `build_available_stocking_workbook` in `backend/app/services.py` to match the 16-column `海外仓备货申请表.xlsx` structure
- [X] T062 [US5] Add export batch creation in `backend/app/services.py`
- [X] T063 [US5] Add export row persistence in `backend/app/services.py`
- [X] T064 [US5] Create full-field traceability export builder in `backend/app/services.py`
- [X] T065 [US5] Add traceability export route in `backend/app/routers/stocking.py`
- [X] T066 [US5] Update stocking export response filename and sheet name in `backend/app/routers/stocking.py`
- [X] T067 [US5] Run export tests with `..\.venv\Scripts\python.exe -m pytest tests/test_stocking_export.py tests/test_traceability_export.py tests/test_export_batch.py -q`

**Checkpoint**: Export-only MVP backend is functionally complete.

---

## Phase 8: Frontend MVP Screens

**Purpose**: Provide usable pages for the frozen first-version workflow.

- [X] T068 [P] Add API client methods for import, opportunities, assignments, claims, reviews, and exports in `frontend/src/api.ts`
- [X] T069 [P] Add import and import-result UI in `frontend/src/App.tsx`
- [X] T070 [P] Add supervisor assignment preview and confirm UI in `frontend/src/App.tsx`
- [X] T071 [P] Add operator claim/not-claim form UI in `frontend/src/App.tsx`
- [X] T072 [P] Add supervisor review UI in `frontend/src/App.tsx`
- [X] T073 [P] Add export list and export buttons in `frontend/src/App.tsx`
- [X] T074 Update `frontend/src/styles.css` for dense operational layout, stable table widths, and non-overlapping controls
- [X] T075 Run frontend build with `npm run build` in `frontend/`

---

## Phase 9: Production Readiness and Validation

**Purpose**: Prove the planned MVP can run safely with PostgreSQL and without accidental out-of-scope behavior.

- [X] T076 Add a backend test or smoke script verifying PostgreSQL `DATABASE_URL` startup in `backend/tests/test_config.py`
- [X] T077 Update `docker-compose.yml` only if needed to keep PostgreSQL, Redis, API, worker, scheduler, frontend, and reverse proxy aligned with current env names
- [X] T078 Update `README.md` with local test, local dev, and Docker Compose startup commands
- [X] T079 Update `AGENT_HANDOFF.md` with current implementation status and remaining task pointer to `specs/001-frontstage-mvp/tasks.md`
- [X] T080 Run backend full tests with `..\.venv\Scripts\python.exe -m pytest -q`
- [X] T081 Run frontend build with `npm run build` in `frontend/`
- [ ] T082 Run Docker Compose config validation with `docker compose config` (blocked locally: Docker CLI is not installed or not on PATH)
- [X] T083 Record validation results in `specs/001-frontstage-mvp/quickstart.md`

---

## Phase 10: Convergence

**Purpose**: Align implementation tasks with the clarified first-version `商品看板` requirement.

- [X] T084 Add a dedicated `商品看板` view in `frontend/src/App.tsx` that shows all platform product records grouped by main SKU with expandable child SKU rows, per FR-021 (missing)
- [X] T085 Add `商品看板` search and filters for main SKU, child SKU, product name, keyword, site, operator, status, health label, level-1 / level-2 category, and source batch in `frontend/src/App.tsx` and `frontend/src/styles.css`, per FR-023 and US6/AC3 (missing)
- [X] T086 Restore prototype-aligned top-level separation between `商品看板` and `机会池` / workflow nodes in `frontend/src/App.tsx` and `frontend/src/styles.css`, per FR-022 and clarification 2026-07-03 (partial)
- [X] T087 Run frontend build and screenshot verification for both `商品看板` and `机会池` views in `frontend/`, per US6 acceptance scenarios (missing)

---

## Phase 11: Latest UI / Assignment Clarifications

**Purpose**: Implement the confirmed 2026-07-03 UI corrections: browser upload, supervisor-only assignment controls, inline operator claim cards, evidence placeholders, and local demo status coverage.

- [X] T088 Add backend tests for browser Excel upload import and four-field operator assignment profile CRUD
- [X] T089 Implement `/opportunities/import/selection1/upload`, `/opportunities/import/selection2/upload`, and `/admin/operator-profiles` CRUD
- [X] T090 Narrow personnel assignment config import/UI to `销售员`, `重点站点`, `重点品类1`, `重点品类2`
- [X] T091 Replace frontend source-file path inputs with drag/drop and file-picker upload zones
- [X] T092 Prevent supervisor opportunity-pool claim action and bind operator submissions to a current operator identity in local demo mode
- [X] T093 Replace assignment candidate textarea with default all-enabled operator profiles and supervisor-editable config table
- [X] T094 Replace operator claim right-side panel with inline mutually exclusive claim/not-claim controls on each product card
- [X] T095 Add not-claim research image evidence placeholder with paste, drag/drop, and file picker support
- [X] T096 Add `backend/scripts/seed_demo_statuses.py` for local demo data covering all main workflow statuses
- [X] T097 Run backend full tests, frontend build, local demo seed, and screenshot verification after Phase 11

---

## Phase 12: Source Routing, Batch Claim, and Review-State Clarifications

**Purpose**: Implement the confirmed 2026-07-03 clarification that selection1 enters assignment only, Caigen enters both assignment and opportunity pool, operators can batch-submit complete child-SKU drafts under a main SKU, and review UI must distinguish claim vs not-claim submissions.

- [X] T098 Update `specs/001-frontstage-mvp/spec.md` and this task list with source routing, batch claim, and review-state acceptance rules
- [X] T099 Add backend tests for selection1 assignment-only import and supervisor return-reason validation/exposure
- [X] T100 Update `backend/app/selection1_importer.py` so selection1 source-table claim columns remain prefill/reference only and do not auto-create operator claim tasks
- [X] T101 Update backend opportunity list response to include latest platform claim and supervisor review summary fields
- [X] T102 Update `backend/app/services.py` so returned-for-supplement requires a supervisor reason
- [X] T103 Update frontend source-aware opportunity-pool routing so selection1 pending records stay out of operator self-claim pool while Caigen pending records remain visible
- [X] T104 Update frontend operator claim view to group by main SKU and support one-click submission of all complete child-SKU drafts
- [X] T105 Update frontend supervisor review cards/forms to show `待复核-认领`, `待复核-不认领`, `运营已认领`, `运营不认领`, and `已驳回-待运营补充` rules
- [X] T106 Run backend tests, frontend build, and Speckit analyze after Phase 12

---

## Phase 13: Dashboard UI Simplification

**Purpose**: Apply the confirmed product-card simplification: main SKU reason is shared by child SKUs, and dashboard cards should not show duplicate expand/detail actions until a richer detail view exists.

- [X] T107 Update product dashboard and claim cards so `开品理由` displays once at main-SKU-group level
- [X] T108 Remove duplicate `查看详情` action from product dashboard cards when it only toggles child SKU expansion
- [X] T109 Update spec/docs handoff for group-level reason and no-detail-page first-version scope
- [X] T110 Run frontend build and diff check after Phase 13

---

## Phase 14: DingTalk New-Product Todo Card Sender

**Purpose**: Implement the confirmed 2026-07-04 DingTalk interactive card delivery path for new-product todo reminders, without DingTalk Todo, online-table writeback, or card-side business detail.

- [X] T111 Add unit tests for operator/supervisor card variables, zero-count skip, createAndDeliver payload, and DingTalk userId masking
- [X] T112 Implement minimal `backend/app/dingtalk_card_sender.py` using environment-backed credentials and the confirmed card template
- [X] T113 Add `POST /notifications/dingtalk/new-product-todo-card` as an internal send endpoint with notification-log dedupe
- [X] T114 Update `.env.example`, handoff, status, and project-control docs for the confirmed card sender
- [X] T115 Run backend tests with `..\.venv\Scripts\python.exe -m pytest tests -q`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 Setup and Safety**: No dependencies.
- **Phase 2 Foundational Workflow Model**: Depends on Phase 1.
- **US1 Import**: Depends on Phase 2.
- **US2 Assignment**: Depends on Phase 2, can start after minimal imported fixture support exists.
- **US3 Claim**: Depends on Phase 2 and basic opportunity/task records.
- **US4 Review**: Depends on US3 claim records.
- **US5 Export**: Depends on US3 and US4.
- **Frontend MVP Screens**: Can start after backend contracts for each story stabilize.
- **Production Readiness**: Depends on backend and frontend MVP completion.

### Suggested MVP Order

1. Complete Phase 1 and Phase 2.
2. Complete US1 selection1 path first, then selection2.
3. Complete US2 assignment.
4. Complete US3 claim/not-claim.
5. Complete US4 supervisor review.
6. Complete US5 stocking export and traceability export.
7. Add frontend screens after backend behavior is stable.

### Parallel Opportunities

- T015, T016, and T017 can be written in parallel because they target separate test files.
- T026, T027, and T028 can be written in parallel because personnel import, scoring, and confirmation tests are separate.
- T037, T038, and T039 can be written in parallel because they cover distinct claim behaviors.
- T056 through T059 can be written in parallel because each export concern has a separate test focus.
- T068 through T073 can be implemented in parallel after API shapes are stable, but final integration should be reviewed in one pass.

---

## Parallel Example: User Story 1

```text
Task: "T015 Add selection1 import batch and source traceability tests in backend/tests/test_selection1_import.py"
Task: "T016 Add selection2 Caigen import tests in backend/tests/test_selection2_import.py"
Task: "T017 Add central-field-mapping default-empty tests in backend/tests/test_field_mapping.py"
```

---

## Implementation Strategy

### MVP First

The first demonstrable backend MVP is: selection1 import, manual/simple assignment confirmation, claim, review approve, and official 16-column stocking export. This path already partially exists and should be hardened first.

### Incremental Delivery

Each user story phase must end with a targeted test command and a checkpoint. Do not start broad frontend changes until the backend contract for the relevant flow is stable.

### TDD Rule

For every behavior task, write the failing test first, run it and confirm the expected failure, implement the smallest passing code, then run the targeted tests and full backend test suite when the story phase completes.
