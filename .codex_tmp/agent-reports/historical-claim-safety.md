# historical-claim-safety

## Changed files

- `backend/app/historical_selection1_claim_backfill.py`
- `backend/app/historical_selection1_import.py`
- `backend/tests/test_historical_selection1_claim_backfill.py`
- `backend/tests/test_historical_selection1_import.py`

## RED

Command:

```powershell
New-Item -ItemType Directory -Force .codex_tmp\pytest | Out-Null; python -m pytest -q --basetemp .codex_tmp\pytest backend/tests/test_historical_selection1_claim_backfill.py::test_text_with_digits_in_daily_sales_is_rejection_not_claim backend/tests/test_historical_selection1_import.py::test_parse_excludes_period_outside_current_historical_migration_scope
```

Result: `2 failed`.

- `暂不认领，竞品100` was misclassified as a claim.
- `开发1001期` was parsed into rows instead of being skipped.

## GREEN

Command:

```powershell
New-Item -ItemType Directory -Force .codex_tmp\pytest | Out-Null; python -m pytest -q --basetemp .codex_tmp\pytest backend/tests/test_historical_selection1_claim_backfill.py::test_text_with_digits_in_daily_sales_is_rejection_not_claim backend/tests/test_historical_selection1_import.py::test_parse_excludes_period_outside_current_historical_migration_scope
```

Result: `2 passed in 3.57s`.

Command:

```powershell
New-Item -ItemType Directory -Force .codex_tmp\pytest | Out-Null; python -m pytest -q --basetemp .codex_tmp\pytest backend/tests/test_historical_selection1_claim_backfill.py backend/tests/test_historical_selection1_import.py
```

Result: `39 passed in 28.62s`.

Command:

```powershell
git diff --check -- backend/app/historical_selection1_claim_backfill.py backend/app/historical_selection1_import.py backend/tests/test_historical_selection1_claim_backfill.py backend/tests/test_historical_selection1_import.py
```

Result: passed; only CRLF conversion warnings.

## Unresolved

- No database, server, OSS, DingTalk, or deployment action was performed.
- Existing dirty changes in the same scoped files predated this subtask; this commit stages only the scoped files and report, and does not stage other workspace files.

## Commit

`be0826a`

## Fix round 1

### Review source

`.codex_tmp/agent-reports/historical-claim-safety-review.md`

### Changes

- Added migration-period enforcement to database scan paths shared by `backfill_selection1_claims()`, `normalize_selection1_claims()`, and evidence scanning through `_historical_snapshot()`.
- Non-whitelisted periods now skip entirely even when rows already exist in local DB fixtures as `history_selection1` or nested current selection1 snapshots.
- Added a regression assertion that default claim backfill does not call OSS evidence upload; evidence upload remains available only through the explicit evidence path.
- Corrected the reviewed commit hash in this report to `be0826a`.

### RED

Command:

```powershell
New-Item -ItemType Directory -Force .codex_tmp\pytest | Out-Null; python -m pytest -q --basetemp .codex_tmp\pytest backend/tests/test_historical_selection1_claim_backfill.py::test_non_migration_period_snapshots_do_not_backfill_claims backend/tests/test_historical_selection1_claim_backfill.py::test_non_migration_period_claims_are_not_normalized_or_deleted backend/tests/test_historical_selection1_claim_backfill.py::test_default_claim_backfill_does_not_upload_evidence
```

Result: `2 failed, 1 passed`.

- Non-whitelisted `开发1001期` / `开发0924期` snapshots still created or normalized historical claims.
- Default upload-path assertion already passed before implementation.

### GREEN

Command:

```powershell
New-Item -ItemType Directory -Force .codex_tmp\pytest | Out-Null; python -m pytest -q --basetemp .codex_tmp\pytest backend/tests/test_historical_selection1_claim_backfill.py::test_non_migration_period_snapshots_do_not_backfill_claims backend/tests/test_historical_selection1_claim_backfill.py::test_non_migration_period_claims_are_not_normalized_or_deleted backend/tests/test_historical_selection1_claim_backfill.py::test_default_claim_backfill_does_not_upload_evidence
```

Result: `3 passed in 3.30s`.

Command:

```powershell
New-Item -ItemType Directory -Force .codex_tmp\pytest | Out-Null; python -m pytest -q --basetemp .codex_tmp\pytest backend/tests/test_historical_selection1_claim_backfill.py backend/tests/test_historical_selection1_import.py
```

Result: `42 passed in 28.63s`.

Command:

```powershell
git diff --check -- .codex_tmp/agent-reports/historical-claim-safety.md backend/app/historical_selection1_claim_backfill.py backend/app/historical_selection1_import.py backend/tests/test_historical_selection1_claim_backfill.py backend/tests/test_historical_selection1_import.py
```

Result: passed; only CRLF conversion warnings.

### Unresolved

- No server, development/production database, OSS, DingTalk, or deployment action was performed.
- Fix round 1 commit hash is reported in final chat; embedding a commit's own hash inside that commit would change the hash.
