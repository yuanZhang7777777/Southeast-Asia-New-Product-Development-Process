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

`9d8a86b`
