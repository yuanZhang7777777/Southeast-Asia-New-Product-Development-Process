# Agent Handoff

> Updated: 2026-07-29 Asia/Shanghai
> Purpose: current facts, hard boundaries, and the next executable sequence only. Detailed history stays in `docs/20-项目推进总控.md` and `C:\Users\86173\.codex\work-logs\`.

## Read Order

1. This file: current scope and stop conditions.
2. `docs/2026-07-09-已确认需求记录.md`: confirmed business rules, highest priority.
3. `docs/20-项目推进总控.md`: detailed delivery timeline and recorded read-backs.
4. `docs/21-后半段需求领导对齐问题清单.md`: downstream workflow, PLM/FineBI facts, and unresolved business inputs.
5. `docs/02-功能实现状态.md`: implementation and test status.
6. `docs/06-部署与服务器准备.md`: environment, backup, deployment, and rollback procedures.
7. `AGENTS.md`: project safety and engineering rules.

Do not recover decisions from old release notes or screenshot-only discussions when they conflict with the files above or the user's newest message.

## Immediate Operating Boundaries

- The worktree is deliberately dirty and contains work from multiple agents. Start every implementation task with `git status --short`, inspect the relevant diff, and never run `git reset --hard`, `git checkout --`, or overwrite unrelated changes.
- The active code baseline is `main` at or after merge commit `59429cf`. For deployment, data migration, or rollback, cite the exact commit being used.
- This root `AGENT_HANDOFF.md` is the only active handoff. Any `AGENT_HANDOFF-*` file found in older branches or worktrees is historical evidence only and must not override this file.
- Production changes require a fresh explicit user approval, a production backup, a dry-run/read-back report, and the deployment runbook. Do not infer approval from an old handoff line.
- During documentation-only work, do not touch either database, deployment, OSS, PLM, FineBI, or DingTalk.
- Never commit credentials, cookies, tokens, `.env`, or personal passwords.

## Current Objective

Prepare a clean production-ready historical foundation before routine downstream automation:

1. Restore **selection1 historical claim/rejection facts** as traceable records.
2. Logically replace the legacy production 0714 batch with the canonical 0714 batch.
3. Only after claim facts are accepted, enable a separate, controlled PLM arrival-to-secondary-research bridge.

Selection2 historical cleanup remains isolated. It must not block selection1 claim recovery or be silently merged into it.

## Confirmed Business Contract

### Roles and allocation

- The only product roles are `operator` (运营), `manager` (主管), and `super_admin` (超级管理员). The `sales` role option has been removed from admin role choices; production has no `sales` role mapping that needs migration.
- Liu Xuecheng is the sole super administrator; Lian Yujun is the sole manager. Assignment candidates are enabled operators only.
- An operator may configure up to six first-level category groups. Selection1 now supports `category_level2`; assignment recommendation ranks `一级+二级` match first, then first-level match, then all enabled operators by current load. Main-SKU groups stay together within the same source/batch/site.

### Period and source identity

- Selection1 normal periods use `开发MMDD期`; `开发新品0623期` normalizes to `开发0623期`.
- New selection1 standard uploads can include `二级类目`; old historical rows without second-level category must remain blank.
- The development-finance-team source is exactly `开发0727期-财根`.
- Selection2 periods use the independent namespace `选品2-财根MMDD期`; do not merge them with selection1 merely because SKU values match. The standard selection2 shape maps `SPU` to main SKU, `SKU` to child SKU, fixes site/country to `PH`, and leaves categories blank.
- Historical identity is at least: `source namespace + normalized period + country/site + main SKU + child SKU`. Same main SKU with different child SKUs is normal product-specification structure. Same SKU in different countries/sites is not a duplicate.

### Historical selection1 claim recovery

- Scope: `开发0414期` through `开发0721期`. Do not import old periods before 0414. `开发0727期-财根` waits for the separately standardized business source and is excluded from this batch.
- Parse every period through `PERIOD_CLAIM_LAYOUTS` and verify the real headers; each period uses different claim columns.
- Positive numeric claimed daily sales means `认领`. Explicit no, a rejection reason, text entered in the claimed-sales cell, or a blank / `0` daily-sales cell with a filled salesperson means `不认领`; blank/`0` reasons are recorded as `来源表未填写认领单销` / `来源表认领单销为0`. No salesperson means no relationship. `history_selection1` is source/audit provenance only and is never shown as part of the result label.
- Persist country/site, main/child SKU, period, claimant, claimed sales or rejection reason, feedback, remark, source file/sheet/row/column, and attachments. Preserve unresolvable names as evidence but do not create future tasks for them.
- Historical source facts must not overwrite current `platform` claims and must not be represented as a completed manager review.

### Owner and PLM policy

- Historical claim recovery establishes the provisional **system-confirmed owner** for downstream work.
- PLM is the source of arrival facts and its salesperson is audit evidence only. It must not automatically overwrite a system-confirmed owner.
- After historical claim recovery, generate a mismatch list for `system owner != PLM salesperson`; do not reassign until business confirms a rule for that case.
- Arrival matching prefers `country/site + main SKU + child SKU`. `country/site + child SKU` is only a candidate-discovery fallback, followed by main-SKU validation. Missing country/site or ambiguous main SKU goes to an exception list rather than creating a task.

### Arrival, secondary research, listing, and observation

- A new-arrival candidate needs PLM first and last/most-recent inbound dates on the same natural day, ignoring time of day. Restocks are not new arrivals.
- A future secondary-research branch requires a valid system owner, an effective historical claim, no effective listing Item, no historical secondary-research/market-monitor evidence, and no prior notification for the same arrival batch.
- Historical import itself creates no secondary research, listing, observation, FlowTask, or DingTalk card.
- FineBI is the source of `shop + Item + period` listing/metric facts. One shop+Item may legally bind multiple main/child SKUs; metrics are one Item summary and must never be duplicated to every SKU.
- Secondary research requires review conclusion, product positioning, target daily sales, and selling points. `淘汰款` and `清仓款` do not enter listing; only 淘汰款 notifies the manager.

## Data Source Contract

| Source | Authority | Current use |
|---|---|---|
| Selection1 historical workbooks | historical product and claim/rejection facts | restore traceable historical records |
| Selection2 historical workbooks | independent finance-team source | parked until headers and rows are normalized |
| PLM Excel export | arrival date, inventory, country/site, audit salesperson | arrival fact only; no owner overwrite |
| Market-monitor workbook | historical secondary-research evidence | proves history; missing fields remain empty |
| Listing-monitor workbook | historical shop/Item/operation evidence | proves listing evidence; no metric inference from blank cells |
| FineBI Item finance raw data | shop+Item+period listing evidence and weekly metrics | Item-level summary only |

Known inputs and reports:

- PLM Excel history was previously downloaded for `2026-04-01` through `2026-07-25`; reuse cached output before any new download.
- FineBI raw data was previously captured for 17 periods. It requires merged-cell-aware parsing and unfiltered raw rows.
- Historical normalization and read-back outputs live under `outputs/historical_normalization/20260728/`.
- 2026-07-29 canonical rerun uses `选品1：7.27新海外仓开发部门开发新品认领-反馈.xlsx` (SHA256 `724a393e...cc696de`), writes `outputs/historical_normalization/20260729/canonical/`, and is limited to `开发0414期` through `开发0721期`. It has 3,862 raw rows, 3,831 normalized archive rows, 1,621 `认领` facts, 2,209 `不认领` facts. The raw canonical output still contains 14 unresolved groups / 31 source rows, but these must be overlaid with `E:/Project/Hengzhe-New-Product-Workflow/选品1历史清洗与业务核对包-20260728.xlsx`; after applying that business review, all 14 non-finance groups are covered and remaining business-confirmation groups are 0. `开发0727期-财根` is excluded. The local package itself does not write OSS, cards, tasks, or production.
- 2026-07-29 selection1 claim parsing now inherits a salesperson from the same `business period + country/site + main SKU` group when the current row has claim/rejection evidence but its salesperson cell is blank, and only if the group has exactly one salesperson. Example: `开发0526期 / TH / LJJ926 / LJJ926A5 / row 254` inherits `庞莹莹` and becomes `不认领` with reject reason `市场需求量过小`. The rerun output is `outputs/historical_normalization/20260729/canonical_with_group_inheritance/`: 3,831 non-finance archive rows, 3,831 claim/rejection facts, 0 missing relation keys, 1,621 `认领`, 2,210 `不认领`.
- 2026-07-29 clean Selection1 environment-sync package is `outputs/historical_normalization/20260729/selection1_environment_sync/import_rows.json`: 3,977 rows, replacing `开发0414期` with `E:/soft/dingding/历史选品1表财根周期拆分以及开发0414期.xlsx` and adding finance split periods `开发0624期-财根`, `开发0701期-财根`, `开发0708期-财根`, `开发0715期-财根`. `开发0727期-财根` is intentionally excluded until business provides the new normalized source.
- 2026-07-29 development and production were both synchronized with that clean Selection1 package. Runtime used a one-off container script, not a full service deployment, and did not create secondary research, listing, observation, PLM, FlowTask, or DingTalk records. Visible Selection1 opportunities read back as exactly 3,977 rows across the 18 clean periods. Backups: development `/opt/hengzhe-new-product-dev/app/backups/selection1_clean_sync_20260729/`; production `/opt/hengzhe-new-product/app/backups/selection1_clean_sync_20260729/`.
- 2026-07-29 image backfill for the same authoritative workbook uploaded 220 embedded product images to OSS and backfilled both environments with `created=0`, `backfilled_existing_archive=220`. Read-back for `开发0414期` plus the four finance split periods shows all 220 visible archive rows have images. Claim evidence images from feedback/remark cells used a small extracted bundle: development and production each attached 4 new images, found 2 already attached, and had 0 failed uploads. Backup folders: development `/opt/hengzhe-new-product-dev/app/backups/selection1_clean_images_20260729/`; production `/opt/hengzhe-new-product/app/backups/selection1_clean_images_20260729/`.
- PLM/FineBI classification outputs live under `outputs/historical_data/`.
- The canonical latest selection1 import shape is `模板/选品1标准表头.xlsx`.

## Production Historical Migration: Exact Sequence

### Required batch treatment

- Production currently has legacy `开发新品0714期`: 255 opportunities, 110 claims, 143 rejections.
- The canonical selection1 source is `开发0714期`: 258 opportunities, 111 claims, 147 rejections.
- Logically disable, never physically delete, the old production 0714 batch before importing canonical 0714. Operators/managers must not see disabled rows; super administrators may audit and restore them.
- Existing production periods `开发0414期` through `开发0623期` receive only idempotent source/claim/rejection/attachment repair. Missing canonical batches are `开发0630期`, `开发0707期`, `开发0714期`, and `开发0721期`. `开发0727期-财根` is not part of this release.

### Release gates

1. Inspect current code/diff and generate a local dry-run: period totals, claims, rejections, unmapped people, attachments, duplicates, and skipped rows.
2. Obtain user confirmation for the production window, back up the production database, and capture the existing batch inventory.
3. Logically disable legacy 0714, import or repair the canonical selection1 batches, then read back a production verification workbook.
4. Verify every period's total rows, claimed/rejected/unclaimed counts, account mappings, source row references, attachment success/failure, and disabled legacy-row count.
5. Only after that acceptance, perform a separate dry-run for PLM arrival activation. Cards first route to Liu Xuecheng in test mode; real operators and production deep links need separate approval.

## Current Implementation Focus

- Historical selection1 parsing and claim recovery: `backend/app/historical_selection1_claim_backfill.py`.
- Historical selection1 import/state restoration: `backend/app/historical_selection1_import.py`, `backend/app/historical_selection1_state_restore.py`.
- Future arrival bridge: `backend/app/historical_arrival_activation.py`, `backend/app/plm_processing.py`, `backend/app/notification_jobs.py`.
- Personnel/role UI and APIs: `backend/app/admin_console.py`, `backend/app/routers/admin.py`, `frontend/src/adminConsole.ts`.
- Development and production product boards display both current `platform` and read-only `history_selection1` claim/rejection relationships in `已分配运营`; this is display-only and must not create tasks or overwrite current claims. On 2026-07-30 production API was hotpatched to match the development behavior, and legacy visible `历史归档` rows were disabled.
- Product board period scope is currently clean in both environments: 18 visible periods from `开发0414期` through `开发0721期`, plus the four split finance periods `开发0624期-财根` / `开发0701期-财根` / `开发0708期-财根` / `开发0715期-财根`. `开发0727期-财根`, `历史归档`, and `5.26期` are disabled and must not appear to normal users.
- Product board frontend now mirrors listing observation's light rendering pattern: first 50 main-SKU groups render by default, then "加载更多" appends 50 at a time. Development is live with `/assets/index-fpFRxTYC.js`; production is live with `/assets/index-CZBFcbzS.js`. This is a frontend-only performance guard; filtering/statistics still use the full loaded dataset.
- Before changing behavior, trace all callers and update the narrow tests. The worktree already contains uncommitted changes in these areas; do not assume they are complete or deployable.

## Verification Commands

Use a repository-local temporary directory on Windows:

```powershell
New-Item -ItemType Directory -Force .codex_tmp\pytest | Out-Null
python -m pytest -q --basetemp .codex_tmp\pytest `
  backend/tests/test_historical_selection1_claim_backfill.py `
  backend/tests/test_historical_selection1_import.py `
  backend/tests/test_historical_selection1_state_restore.py `
  backend/tests/test_plm_processing.py `
  backend/tests/test_secondary_research.py `
  backend/tests/test_listing_observations.py
```

Then run affected frontend tests, `npm test`, `npm run build`, and `git diff --check`. Do not skip failures by weakening assertions or masking source-data gaps.

## Document Ownership

- Business decisions: `docs/2026-07-09-已确认需求记录.md`.
- Current execution order and detailed timeline: `docs/20-项目推进总控.md`.
- Downstream/PLM/FineBI rules and unresolved external inputs: `docs/21-后半段需求领导对齐问题清单.md`.
- Implementation and verification ledger: `docs/02-功能实现状态.md`.
- Environment and deployment: `docs/06-部署与服务器准备.md`.
- This file must stay short. Move completed timestamps, old release packages, and verbose run logs to the documents above or the weekly work log instead of appending them here.
