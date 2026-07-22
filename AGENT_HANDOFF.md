# Agent Handoff

> Updated: 2026-07-22 13:25 Asia/Shanghai

## Start Here

The canonical development branch is `lxc/integrated-workflow`. It merges the complete production front-stage line `lxc/pricing-review-edit@fbf574c` and the listing/observation line `lxc/listing-observation-workbench@a4a61e4` in merge commit `1aae41e`.

Read these files before changing behavior:

1. `docs/2026-07-09-已确认需求记录.md` — highest-priority confirmed business rules.
2. `docs/02-功能实现状态.md` — implementation, verification and open work.
3. `docs/20-项目推进总控.md` — current delivery order.
4. `docs/06-部署与服务器准备.md` — production/development separation and rollback.
5. `docs/21-后半段需求领导对齐问题清单.md` — later-stage confirmed rules and remaining external inputs.

Do not infer current behavior from old plans or prototypes when they conflict with the confirmed record.

## Environment Boundary

| Environment | Address | Current code | Rule |
|---|---|---|---|
| Production | `http://101.132.26.138:8080` | `b373d65` | In use. Do not connect, deploy or restart without a separately approved non-working-time release window. |
| Development | `http://139.224.2.166:18081` | `ac8a5359e350` | Unified branch validation and business UAT only. SSH alias: `hz-new-product-dev`. |

Production database is `workflow_prod_20260715`; development database is `workflow_dev_20260715`. Databases, Redis, uploads, volumes, ports and environment variables are isolated. Never commit passwords, tokens, cookies, private keys or `.env` files.

PLM arrival endpoint settings and credentials are stored separately in both server `.env` files. `PLM_SYNC_ENABLED` remains `false` in both environments; do not enable it or restart production without explicit approval.

`caigen-arrival-notifier` is a separate service co-hosted with the workflow production environment on `101.132.26.138`. It is the only sender of arrival cards; neither workflow environment sends arrival cards. The workflow still owns its elimination-summary reminder. Development must not receive a persistent feed from the production notifier. Its current arrival/summary card template is selected through `DINGTALK_ARRIVAL_CARD_TEMPLATE_ID`; never commit the environment value.

## Development Deployment: `ac8a5359e350`

The UAT usability release is running only at `http://139.224.2.166:18081`. The deployed code commit is `ac8a5359e350`; the canonical branch `lxc/integrated-workflow` contains that commit. This handoff-only documentation update is not deployed.

- The deployed UI uses editable length / width / height in centimetres and automatically calculates unit volume; dirty stocking drafts save when leaving the editing area, saves for the same request are serialized, and unchanged updates are backend semantic no-ops.
- Main/sub-SKU ordering is stable across stocking decisions, stocking cards are vertically stacked, the supervisor review detail pane no longer changes left-card width, and `listing_observation` has a Chinese label.
- Source and development database are both at the single Alembic head `e1f2a3b4c678` (`down_revision=d0e2f3a4b567`).
- Local release verification passed: backend `308 passed`, frontend `128 passed`, TypeScript/Vite production build, Alembic head and `git diff --check`.
- Release package: `/opt/hengzhe-new-product-dev/releases/ac8a5359e350.tar.gz`, SHA-256 `c14def5679ba8ec79ff8635a98db4c6a368bb15702c492c831b68a8123eea547`.
- Pre-migration backup: `/opt/hengzhe-new-product-dev/backups/workflow_dev_before_ac8a5359e350_20260722_131418.sql.gz`; environment backup: `/opt/hengzhe-new-product-dev/backups/config/.env_before_ac8a5359e350_20260722_131418`; rollback directories: `app.previous_20260722_131418` and `app.replaced_20260722_131418`.
- API, worker, scheduler, frontend and reverse-proxy were rebuilt. PostgreSQL and Redis kept their prior container IDs and all active services report `RestartCount=0`.
- Internal/external health returns `environment=development`; `PLM_SYNC_ENABLED=false` and `DINGTALK_CARD_AUTOSEND_ENABLED=false` remain unchanged. Recent service error count was zero.
- Read-only browser smoke verified the 刘学城 development account, exact left-card width stability before/after opening supervisor review, visible length/width/height fields, vertical stocking cards and zero console errors. No business form was submitted.
- Production was not connected, deployed, restarted or modified. Write-path business UAT remains open.

## Verified Baseline

- Deployed code commit: `ac8a5359e350`; `lxc/integrated-workflow` contains it. This handoff-only documentation update does not change the development runtime.
- Backend: `308 passed`. Frontend: `128 passed`. TypeScript/Vite production build passed.
- Alembic: source and `workflow_dev_20260715` are at `e1f2a3b4c678 (head)`.
- Development health is `ok/development` inside the server and through the public `18081` path. Current assets are `/assets/index-z3SBLd1W.js` and `/assets/index-DmxfXngb.css`.
- PostgreSQL and Redis container IDs remained `0383695d...` and `a764cb3f...` with `RestartCount=0`; all rebuilt application services also report `RestartCount=0`.
- Real development PLM E2E previously processed 2,263 rows and 22 salesperson groups, proved same-file idempotency, and completed one controlled Item through secondary research, listing, weeks 1-5 and the week-4 summary. Arrival cards were a one-time test redirected to 刘学城; persistent autosend remains disabled.
- Development UAT uses the existing 刘学城 account: `super_admin` supplies the supervisor and operator views, and an enabled Thailand operator profile is linked to the same user.
- `GZMO075` is not a usable 0/3 secondary-research fixture: the current development UI has no secondary-research row for it, and the product board shows it as disabled with listing-observation history. A replacement fixture requires explicit approval, a fresh development backup and an isolated development-only write.

## Implemented Scope

Front stage:

- Import the two approved internal feedback workbooks with source file/sheet/row/snapshot traceability.
- Supervisor assignment by main-SKU group, operator claim/not-claim, supervisor review and audit history.
- Formal stocking export is a one-time selected-request transition to `waiting_arrival`; central traceability export remains repeatable by business period with independent batches and no workflow-state rollback.
- Product board, opportunity pool, assignment filters, operator configuration and pricing/percentage display rules.

Later stage:

- Secondary research with five positions: 引流款、利润款、淘汰款、稳定款、清仓款.
- 引流款、利润款、稳定款 enter listing; 淘汰款 and 清仓款 skip listing; only entering 淘汰款 creates the daily supervisor reminder event.
- One main SKU can have multiple manually entered shop + globally unique Item listing records.
- Each Item selects its own first Thursday-to-Wednesday period and observes four independent weeks; later periods are manually added.
- Weekly metrics are read-only; product positioning and optimization action are required; week 4 also requires a summary.
- Completed reviews remain editable with audit; stopped Items may finish already-fetched periods; only explicit stop pauses future fetches and reminders.
- Product detail is the read-only lifecycle archive: secondary-research history and listing/observation history have separate entries, with listing records grouped by source business period.
- The listing workbench keeps full viewing and editing in a collapsible main-SKU / Item / visible-week layout. Its title, common filters, result count and batch action remain outside the independently scrolling result pane; future weeks stay hidden, and current pending-data weeks show only the expected data date.

Detailed field, state, permission and API rules stay in the confirmed requirement and architecture documents; do not duplicate them here.

## Documentation Model

Daily maintenance is limited to the active documents indexed by `docs/README.md`:

- `README.md`, `AGENT_HANDOFF.md` and `AGENTS.md` for onboarding, handoff and project rules.
- `docs/2026-07-09-已确认需求记录.md` for confirmed business rules.
- `docs/02-功能实现状态.md` and `docs/20-项目推进总控.md` for implementation status and delivery priority.
- `docs/04-系统架构重新设计方案.md` and `docs/06-部署与服务器准备.md` for architecture, API, environment, deployment and rollback.
- `docs/19-钉钉新品待办卡片接入说明.md` for DingTalk technical integration only.
- `docs/21-后半段需求领导对齐问题清单.md` for later-stage open inputs.

Unique source evidence and the original Spec Kit bundle are frozen under `docs/archive/2026-07-22/`. Deleted plans and prototypes remain recoverable from Git history. Do not restore archived or deleted files as competing authorities.

## Still Open

- 刘学城 must complete write-path UAT for sales-self branches, automatic/manual draft save, manual dimensions, submit and manager selected export. Later-stage UAT needs a new approved fixture because `GZMO075` is no longer pending secondary research.
- Development does not currently provide all five ERP settings (`ERP_LOGIN_URL`, `ERP_PRODUCT_LIST_URL`, `ERP_DOWNLOAD_LIST_URL`, `ERP_USERNAME`, `ERP_PASSWORD`); the referenced asset document contains no uniquely locatable credentials. Real ERP volume lookup remains unaccepted until values are supplied through development `.env` only. The deployed fallback is manual dimensions with automatic volume calculation.
- The real weekly Item endpoint, authentication method and unfiltered aggregate response sample are not provided. Do not guess them. The integration point is the existing `apply_week_metrics(...)` boundary.
- Real scheduling, retry monitoring and operator message delivery for weekly Item metrics remain unconnected.
- Production release of the unified branch is not approved.

## Next Session Checklist

1. Confirm the active branch is based on `lxc/integrated-workflow` and inspect `git status` before editing.
2. Preserve the production/development boundary; normal development and deployment target only `hz-new-product-dev`.
3. Run backend tests, frontend tests/build and Alembic head verification before every release.
4. Update `docs/02-功能实现状态.md`, `docs/20-项目推进总控.md` and `docs/06-部署与服务器准备.md` when implementation or deployment state changes.
5. Use `neat-freak` at milestones; update only the active document set and keep `docs/archive/` read-only.
