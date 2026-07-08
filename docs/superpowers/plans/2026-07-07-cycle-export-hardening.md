# Cycle Export Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or inline TDD. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make exports cycle-aware and safer while closing the remaining high-risk permission gaps.

**Architecture:** Reuse existing `source_sheet` and `import_batch_id` as the cycle selectors. Keep final exports clean by excluding already exported claim rows and by including only supervisor-confirmed not-claim rows. Add role guards at router boundaries and keep uploaded source workbooks outside the public static image path.

**Tech Stack:** FastAPI, SQLAlchemy, openpyxl, React/Vite, pytest.

---

### Task 1: Backend Cycle And Export Rules

- [ ] Add failing tests for cycle-filtered exports, duplicate export exclusion, confirmed-only not-claim export, protected arrival/summary routes, and claim task ownership.
- [ ] Update service queries and export endpoints with `source_sheet` / `import_batch_id` filters.
- [ ] Exclude already-exported claim rows from default available exports.
- [ ] Filter not-claim traceability rows to latest `confirmed_not_claim`.

### Task 2: Backend Safety Guards

- [ ] Make Docker/production defaults require auth.
- [ ] Protect arrival/summary routes.
- [ ] Make uploaded Excel files private while leaving product images usable.
- [ ] Add auth to evidence proxy.

### Task 3: Frontend Wiring

- [ ] Pass selected cycle to export/download APIs.
- [ ] Handle 401/403 as login expiration.
- [ ] Honor DingTalk `role` parameter after login.
