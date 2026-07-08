# Implementation Plan: Frontstage New Product MVP

**Branch**: `001-frontstage-mvp` | **Date**: 2026-07-02 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/001-frontstage-mvp/spec.md`

## Summary

Build the first-version frontstage workflow for Southeast Asia overseas-warehouse new product opportunities: import the two approved internal feedback workbooks, assign by main SKU group, let operators claim or not claim child SKUs, let the supervisor review without editing operator fields, export approved child-SKU stocking rows, and provide a dedicated `商品看板` for all-product status overview. The implementation will continue from the existing FastAPI + React repository, formalize PostgreSQL as the production database, keep SQLite only for local automated tests, and avoid online-sheet writeback or procurement/supply-chain tasks in this feature.

## Technical Context

**Language/Version**: Python 3.12 backend; TypeScript + React 19 frontend

**Primary Dependencies**: FastAPI, SQLAlchemy 2, Pydantic Settings, openpyxl, pytest, React, Vite, Ant Design, lucide-react

**Storage**: PostgreSQL 16 for production; SQLite only for local tests and throwaway developer smoke checks

**Testing**: pytest for backend service and API tests; TypeScript compiler and Vite build for frontend validation

**Target Platform**: Develop and validate locally first; later migrate the Docker Compose deployment to the production server at `101.132.26.138:2323` over SSH as `root`. API, worker, scheduler, PostgreSQL, Redis, frontend, and reverse proxy stay in the Compose deployment.

**Project Type**: Web application with REST API backend and browser frontend opened from DingTalk entry links

**Performance Goals**: Weekly import/export batches should complete in minutes for 100+ internal users and large Excel inputs; normal task list and review interactions should feel immediate for operators and supervisor.

**Constraints**: MVP scope is frozen to import, assignment, claim/not-claim, supervisor review, export, and the dedicated `商品看板` status overview. No online-table automatic writeback, no central-table exception workflow, no procurement or supply-chain platform todos, and no market-monitoring/PLM workflow implementation in this feature. Any later-stage nodes shown on `商品看板` are read-only status labels unless a later feature explicitly implements them.

**Scale/Scope**: Group 8 internal workflow, initially 100+ users, weekly feedback workbook imports, multiple country/sheet batches, and unlimited Caigen self-claims per child SKU.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

The project constitution file currently contains unfilled Spec Kit placeholders, so no additional constitution-specific gates are active. Project-specific gates are taken from `AGENTS.md` and current business docs:

- **MVP scope gate**: PASS. Plan includes the first-version `商品看板` status overview and excludes online-table writeback, central-table exception list, procurement/supply-chain todos, PLM arrival tracking, and market-monitoring workflow implementation.
- **Traceability gate**: PASS. Import batch and source row snapshot are first-class data model entities.
- **Database gate**: PASS. PostgreSQL is the production database. SQLite is limited to local tests/dev smoke checks.
- **TDD gate**: PASS. Implementation tasks must add failing tests before production code for behavior changes.
- **No secrets gate**: PASS. Plan does not place PLM, DingTalk, database, or server credentials in source-controlled files.
- **Deployment secret gate**: PASS. The production server target can be documented, but SSH passwords and other credentials must stay outside the repository.

## Project Structure

### Documentation (this feature)

```text
specs/001-frontstage-mvp/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── api.md
├── checklists/
│   └── requirements.md
└── tasks.md              # Created by speckit-tasks, not by this plan step
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── config.py
│   ├── db.py
│   ├── models.py
│   ├── schemas.py
│   ├── services.py
│   ├── selection1_importer.py
│   ├── selection2_importer.py      # new
│   └── routers/
│       ├── opportunities.py
│       ├── assignments.py
│       ├── claims.py
│       ├── reviews.py
│       └── stocking.py
└── tests/
    ├── test_mvp_flow.py
    ├── test_selection2_import.py   # new
    └── test_assignment_rules.py     # new

frontend/
├── src/
│   ├── api.ts
│   ├── App.tsx                      # includes product dashboard, opportunity pool, assignment, claim, review, export screens while small
│   ├── styles.css
│   └── pages/                      # add if App.tsx becomes too large
└── package.json

docker-compose.yml
.env.example
```

**Structure Decision**: Use the existing web application layout. Keep backend business logic in `services.py` only while changes remain small; create focused importer modules for workbook-specific parsing. Split frontend pages only when the existing `App.tsx` becomes difficult to review.

## Phase 0: Research Decisions

Research output is captured in [research.md](./research.md). All planning unknowns have decisions:

- Production database: PostgreSQL 16
- Local automated tests: SQLite
- Excel parsing/export: openpyxl
- Background jobs: Redis + RQ for later async imports/notifications, but first implementation can stay synchronous until batch size demands async handling
- DingTalk: entry and notification only in this feature

## Phase 1: Design Outputs

- Data model: [data-model.md](./data-model.md)
- API contract: [contracts/api.md](./contracts/api.md)
- Validation guide: [quickstart.md](./quickstart.md)

The Spec Kit agent-context update script is not present in this repository; `.specify/scripts/powershell/` only contains setup/check scripts. No context update command was available to run.

## Post-Design Constitution Check

- **MVP scope gate**: PASS. Design artifacts preserve the first-version boundary, including `商品看板` as an all-product status overview but excluding later-stage workflow execution.
- **Traceability gate**: PASS. Data model includes import batches, snapshots, export batches, and audit logs.
- **Database gate**: PASS. Contracts and quickstart assume PostgreSQL for production and SQLite only for tests.
- **TDD gate**: PASS. Quickstart and next task generation will require tests before implementation.
- **No secrets gate**: PASS. No generated artifact stores credentials.

## Complexity Tracking

No constitution or scope violations require justification.
