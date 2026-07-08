# Fix Review Top Three Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Fix the top three review findings: DingTalk login bypass, unsafe default JWT secret, and central export data loss from duplicate headers.

**Architecture:** Keep the changes small and local. Auth fixes stay in auth/config; central field fixes stay in import/export mapping.

**Tech Stack:** FastAPI, Pydantic Settings, SQLAlchemy, openpyxl, pytest.

## Global Constraints

- Do not commit secrets, server passwords, DingTalk credentials, ERP credentials, cookies, or `.env` files.
- Preserve source-table traceability: every imported record should keep source file, sheet, row, and snapshot metadata.
- Prefer explicit workflow states and audit logs over hidden spreadsheet color/status conventions.
- Keep the MVP narrow.

---

### Task 1: Auth Boundary Hardening

**Files:**
- Modify: `backend/app/routers/auth.py`
- Modify: `backend/app/config.py`
- Test: existing auth/config tests if present; otherwise add one small focused test.

**Requirements:**
- Production/non-local DingTalk login must not trust client-supplied `dingtalk_user_id`.
- Local/test mode may keep the direct `dingtalk_user_id` shortcut for manual testing.
- Non-local settings must reject the default `auth_secret_key`.
- Keep account/password behavior unchanged in this task.

### Task 2: Central Field Duplicate Header Preservation

**Files:**
- Modify: `backend/app/selection1_importer.py`
- Modify: `backend/app/selection2_importer.py`
- Modify: `backend/app/services.py`
- Test: importer/export focused tests.

**Requirements:**
- Import must preserve duplicate central headers without collapsing later same-name columns.
- Export must be able to reconstruct duplicated template fields accurately.
- Keep the existing central traceability output format as close as possible unless a focused test proves a two-row header is required.
