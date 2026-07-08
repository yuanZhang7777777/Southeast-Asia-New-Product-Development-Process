# Research: Frontstage New Product MVP

## Decision: PostgreSQL 16 is the production database

**Rationale**: The workflow will be used by 100+ internal users and needs concurrent writes, import batches, task states, review records, audit logs, export batches, and later scheduled integrations. PostgreSQL fits the existing `docker-compose.yml`, `.env.example`, and backend dependency stack.

**Alternatives considered**:

- SQLite for production: rejected because concurrent multi-user writes, backup/restore discipline, and operational observability are weaker.
- MySQL: viable, but the repository already ships PostgreSQL Compose configuration and psycopg dependencies.
- Online spreadsheet as database: rejected for workflow state because it cannot reliably enforce task state, audit logs, permissions, and concurrent submissions.

## Decision: SQLite remains allowed only for local tests and throwaway developer smoke checks

**Rationale**: The current pytest suite uses SQLite efficiently for fast isolated tests. Keeping it for tests avoids slowing down TDD while preserving PostgreSQL for production.

**Alternatives considered**:

- PostgreSQL-only tests: stronger parity, but slower and more complex for everyday TDD.
- In-memory fake repository: rejected because SQLAlchemy behavior and constraints should stay exercised.

## Decision: Continue with FastAPI + SQLAlchemy + Pydantic schemas

**Rationale**: The backend already has a working skeleton, tests, routers, models, and service layer. Replacing it would slow delivery without improving the business outcome.

**Alternatives considered**:

- Node.js backend: viable, but would duplicate current working backend and Excel parsing logic.
- Django: productive for admin-style apps, but would require replatforming existing code.

## Decision: Use openpyxl for Excel import/export in the MVP

**Rationale**: Source files and exports are `.xlsx`; openpyxl is already installed and used. It supports header matching, workbook reading, and preserving typed values for exports.

**Alternatives considered**:

- pandas: useful for analysis, but less direct for preserving Excel workbook structure and styles.
- CSV conversion: rejected because the business source and export artifacts are Excel workbooks with sheet names and formulas.

## Decision: Keep first implementation synchronous unless real import latency becomes a blocker

**Rationale**: The immediate MVP can be implemented and verified faster with synchronous import/export endpoints. Redis + RQ exists in the stack and can be used later for long-running import jobs, DingTalk notifications, and scheduled tasks.

**Alternatives considered**:

- Make all imports async immediately: adds job state and retry complexity before basic flow is complete.
- Run everything in frontend: rejected because source traceability, permissions, and audit logs belong on the server.

## Decision: DingTalk is entry/notification only for this feature

**Rationale**: The first version explicitly writes user submissions to the platform database and does not write back to online sheets. The concrete DingTalk choice is an enterprise internal app with web application entry and work notifications. The web application opens the cloud-hosted platform URL; work notifications send personal task links. User identity is verified after entry through DingTalk H5 login-free auth, not through URL parameters.

**Alternatives considered**:

- DingTalk online table as the submission surface: rejected for this feature because it conflicts with the confirmed export-only MVP.
- DingTalk todo tasks: rejected because the confirmed first version uses internal system todos and DingTalk push links only.
- Robot/private-chat cards: useful later for group summaries or richer private-chat cards, but not the first-version primary task channel. These cards should still jump into the same platform URL.
