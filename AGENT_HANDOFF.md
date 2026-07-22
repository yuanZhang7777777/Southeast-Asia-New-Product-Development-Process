# Agent Handoff

> Updated: 2026-07-22 09:55 Asia/Shanghai

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
| Development | `http://139.224.2.166:18081` | `36a9ae9` | Unified branch validation and business UAT only. SSH alias: `hz-new-product-dev`. |

Production database is `workflow_prod_20260715`; development database is `workflow_dev_20260715`. Databases, Redis, uploads, volumes, ports and environment variables are isolated. Never commit passwords, tokens, cookies, private keys or `.env` files.

PLM arrival endpoint settings and credentials are stored separately in both server `.env` files. `PLM_SYNC_ENABLED` remains `false` in both environments; do not enable it or restart production without explicit approval.

`caigen-arrival-notifier` is a separate service co-hosted with the workflow production environment on `101.132.26.138`. It is the only sender of arrival cards; neither workflow environment sends arrival cards. The workflow still owns its elimination-summary reminder. Development must not receive a persistent feed from the production notifier. Its current arrival/summary card template is selected through `DINGTALK_ARRIVAL_CARD_TEMPLATE_ID`; never commit the environment value.

## Local Candidate: Not Deployed

- The current worktree adds manual `length_cm / width_cm / height_cm`, server-side unit-volume calculation, dirty-only serialized stocking draft autosave with backend no-op protection, stable main/sub-SKU ordering, non-stretching supervisor review layout and the Chinese label for `listing_observation`.
- Source Alembic now has one local head, `e1f2a3b4c678`, with `down_revision=d0e2f3a4b567`. The development database is still `d0e2f3a4b567`; no migration, deployment, restart or remote write was performed for this candidate.
- Full verification passed: backend `308 passed`, frontend `128 passed`, and TypeScript/Vite production build passed.
- Before write-path UAT, deploy only to the development environment using the backup and migration gates in `docs/06-部署与服务器准备.md`. Production remains out of scope.

## Development Deployment: `36a9ae9`

The reviewed sales-self and formal stocking-request candidate is committed as `36a9ae9` and is the code running at `139.224.2.166:18081`:

- Review approval creates one draft per “operator + child SKU”; operators save and submit their own requests, and managers export only explicitly selected submitted requests.
- Sales-self supports three branches: existing stock goes directly to listing, stocking needed creates a request, and no stock/no stocking enters recoverable `stocking_paused`.
- Export uses the operator's application date and final 16-column snapshot; quantity is `ceil(daily_sales × 30)`, warehouse is optional, and replenishment reason is conditionally required.
- ERP volume preview returns the calculated value without persisting it; the normal UI saves that value with provenance label `unit_volume_source=erp`, while manual input uses `manual`. Source-table `包装后体积` is not reused as a silent fallback. If any required ERP configuration is absent, the operator can enter a positive unit volume manually.
- PLM only advances `waiting_arrival` claims backed by a real `stocking_available` `ExportRow`, matched by salesperson, child SKU and the immutable exported-country snapshot.
- Dual-role UI refreshes always use the currently selected role: the SSE connection is recreated after a manager/operator switch, and generation guards prevent older requests from overwriting the new role state.
- The demo seed covers draft, submitted/waiting-export, direct-listing and paused branches and can safely remove its own downstream export/arrival/listing data before reseeding.
- Source and development database migration head are both `d0e2f3a4b567`; the upgrade chain from `a8d4e6f7b901` was applied only after the development backup succeeded.
- Verification: local and isolated development-server Linux backend regressions each passed all 305 tests; all 16 frontend files passed 122 tests; `tsc --noEmit`, Vite build, Compose build/config, migration read-back, internal/external health, image import and recent-log checks passed. Browser read-only UAT verified operator stocking/self-selection, manager selected export and existing listing history with zero console errors. Write-path business UAT remains open.

## Verified Baseline

- Branch: `lxc/integrated-workflow`.
- Merge commit: `1aae41ef6b5b86ba086b43f1e61ae0b9ee3c7d83` with parents `fbf574c` and `a4a61e4`.
- Backend: local and isolated Linux full branch regressions both `305 passed`; the Linux run used temporary SQLite with external integrations disabled.
- Frontend: all 16 test files passed with `122 passed`; TypeScript and Vite production build passed. Stocking request, selected export, listing workbench and product lifecycle archive are available in development.
- TypeScript/Vite production build: passed.
- Alembic deployment baseline: commit `36a9ae9` and the development database are at `d0e2f3a4b567`; the undeployed local source candidate extends it to `e1f2a3b4c678`.
- Development deployment: public and server-side health returned `environment=development`; real browser smoke verified manager/operator navigation, the operator stocking request and sales-self dialog, manager selected export, existing listing history and zero console errors.
- Commit `36a9ae9` rebuilt API, worker, scheduler and frontend; reverse-proxy was recreated to bind the new frontend, while PostgreSQL and Redis kept their original container IDs and `RestartCount=0`. Backup: `/opt/hengzhe-new-product-dev/backups/workflow_dev_before_36a9ae9_20260722_094053.sql.gz`; rollback directory: `/opt/hengzhe-new-product-dev/app.previous_20260722_094053`. Production was not connected, restarted or deployed.
- Real development PLM E2E processed 2,263 rows and 22 salesperson groups, proved same-file idempotency, and completed one controlled Item through secondary research, listing, weeks 1-5 and the week-4 summary. Arrival cards were a one-time test redirected to 刘学城; persistent autosend remains disabled.
- Development UAT uses the existing 刘学城 account: `super_admin` supplies the supervisor and operator views, and an enabled Thailand operator profile is linked to the same user. No extra test account is required for the first single-person UAT.
- `GZMO075` is no longer a usable 0/3 secondary-research fixture: the current development UI has no secondary-research row for it, and the product board shows it as disabled with listing-observation history. Do not instruct 刘学城 to search for it. A replacement fixture requires explicit approval, a fresh development backup and an isolated development-only write; none was created in this change.

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

- After the local candidate is deployed to development, 刘学城 must complete write-path UAT for sales-self branches, automatic/manual draft save, manual dimensions, submit and manager selected export. Later-stage UAT needs a new approved fixture because `GZMO075` is no longer pending secondary research.
- Development does not currently provide all five ERP settings (`ERP_LOGIN_URL`, `ERP_PRODUCT_LIST_URL`, `ERP_DOWNLOAD_LIST_URL`, `ERP_USERNAME`, `ERP_PASSWORD`); the referenced asset document contains no uniquely locatable credentials. Real ERP volume lookup remains unaccepted until values are supplied through development `.env` only. The currently deployed build accepts direct manual volume; the local candidate replaces that fallback with manual dimensions and automatic calculation.
- The real weekly Item endpoint, authentication method and unfiltered aggregate response sample are not provided. Do not guess them. The integration point is the existing `apply_week_metrics(...)` boundary.
- Real scheduling, retry monitoring and operator message delivery for weekly Item metrics remain unconnected.
- Production release of the unified branch is not approved.

## Next Session Checklist

1. Confirm the active branch is based on `lxc/integrated-workflow` and inspect `git status` before editing.
2. Preserve the production/development boundary; normal development and deployment target only `hz-new-product-dev`.
3. Run backend tests, frontend tests/build and Alembic head verification before every release.
4. Update `docs/02-功能实现状态.md`, `docs/20-项目推进总控.md` and `docs/06-部署与服务器准备.md` when implementation or deployment state changes.
5. Use `neat-freak` at milestones; update only the active document set and keep `docs/archive/` read-only.
