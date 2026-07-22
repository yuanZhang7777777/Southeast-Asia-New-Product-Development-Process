# Agent Handoff

> Updated: 2026-07-21 23:18 Asia/Shanghai

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
| Development | `http://139.224.2.166:18081` | `c017c5d` | Unified branch validation and business UAT only. SSH alias: `hz-new-product-dev`. |

Production database is `workflow_prod_20260715`; development database is `workflow_dev_20260715`. Databases, Redis, uploads, volumes, ports and environment variables are isolated. Never commit passwords, tokens, cookies, private keys or `.env` files.

PLM arrival endpoint settings and credentials are stored separately in both server `.env` files. `PLM_SYNC_ENABLED` remains `false` in both environments; do not enable it or restart production without explicit approval.

`caigen-arrival-notifier` is a separate service co-hosted with the workflow production environment on `101.132.26.138`. It is the only sender of arrival cards; neither workflow environment sends arrival cards. The workflow still owns its elimination-summary reminder. Development must not receive a persistent feed from the production notifier. Its current arrival/summary card template is selected through `DINGTALK_ARRIVAL_CARD_TEMPLATE_ID`; never commit the environment value.

## Local Candidate Awaiting Development Deployment

The current working tree contains the locally reviewed sales-self and formal stocking-request candidate, but it is **not committed or yet the code running at `139.224.2.166:18081`**:

- Review approval creates one draft per “operator + child SKU”; operators save and submit their own requests, and managers export only explicitly selected submitted requests.
- Sales-self supports three branches: existing stock goes directly to listing, stocking needed creates a request, and no stock/no stocking enters recoverable `stocking_paused`.
- Export uses the operator's application date and final 16-column snapshot; quantity is `ceil(daily_sales × 30)`, warehouse is optional, and replenishment reason is conditionally required.
- ERP volume preview returns the calculated value without persisting it; the normal UI saves that value with provenance label `unit_volume_source=erp`, while manual input uses `manual`. Source-table `包装后体积` is not reused as a silent fallback. If any required ERP configuration is absent, the operator can enter a positive unit volume manually.
- PLM only advances `waiting_arrival` claims backed by a real `stocking_available` `ExportRow`, matched by salesperson, child SKU and the immutable exported-country snapshot.
- Dual-role UI refreshes always use the currently selected role: the SSE connection is recreated after a manager/operator switch, and generation guards prevent older requests from overwriting the new role state.
- The demo seed covers draft, submitted/waiting-export, direct-listing and paused branches and can safely remove its own downstream export/arrival/listing data before reseeding.
- Source migration head is `d0e2f3a4b567`; the running development database remains on the baseline recorded below until an approved deployment occurs.
- Local candidate verification: 37 focused backend tests passed; all 16 frontend test files passed with 122 tests; `tsc --noEmit` passed; source Alembic head is `d0e2f3a4b567`. The final full backend rerun, Linux Vite build, Compose validation, migration read-back and browser UAT must be recorded after the permission-blocked development deployment resumes; do not substitute projected test counts.

## Verified Baseline

- Branch: `lxc/integrated-workflow`.
- Merge commit: `1aae41ef6b5b86ba086b43f1e61ae0b9ee3c7d83` with parents `fbf574c` and `a4a61e4`.
- Backend: full branch regression `252 passed`; secondary-research and listing-observation focused regression `10 passed`.
- Frontend: deployed branch `104 passed` and production build passed; the listing workbench, product lifecycle archive, export-period selection and claim UAT usability fixes are available in development.
- TypeScript/Vite production build: passed.
- Alembic: one head, `a8d4e6f7b901`.
- Development deployment: public and server-side health returned `environment=development`; real browser smoke verified the workbench defaults to `待刊登`, `全部` exposes all visible records, main-SKU groups fully collapse, only the result pane scrolls vertically, no result-pane horizontal overflow remains, and future periods stay hidden even if development test data already contains them.
- Commit `dd8edd0` rebuilt API and frontend; the follow-up `c017c5d` rebuilt frontend only. Worker, scheduler, PostgreSQL, Redis and reverse-proxy container IDs were preserved with `RestartCount=0`; production was not connected, restarted or deployed.
- Real development PLM E2E processed 2,263 rows and 22 salesperson groups, proved same-file idempotency, and completed one controlled Item through secondary research, listing, weeks 1-5 and the week-4 summary. Arrival cards were a one-time test redirected to 刘学城; persistent autosend remains disabled.
- Development UAT uses the existing 刘学城 account: `super_admin` supplies the supervisor and operator views, and an enabled Thailand operator profile is linked to the same user. No extra test account is required for the first single-person UAT.
- `GZMO075` now has three development-only simulated arrival records and is the prepared 0/3 secondary-research UAT group for 刘学城. Database backup before this setup: `/opt/hengzhe-new-product-dev/backups/workflow_dev_before_secondary_uat_20260721_114310.sql.gz`. No real PLM job or DingTalk delivery was triggered.

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

## Still Open

- Operators and supervisors must complete development-environment UAT with controlled data.
- Development does not currently provide all five ERP settings (`ERP_LOGIN_URL`, `ERP_PRODUCT_LIST_URL`, `ERP_DOWNLOAD_LIST_URL`, `ERP_USERNAME`, `ERP_PASSWORD`). Real ERP volume lookup cannot be accepted until they are supplied through server `.env` only; manual-volume fallback remains testable.
- The real weekly Item endpoint, authentication method and unfiltered aggregate response sample are not provided. Do not guess them. The integration point is the existing `apply_week_metrics(...)` boundary.
- Real scheduling, retry monitoring and operator message delivery for weekly Item metrics remain unconnected.
- Production release of the unified branch is not approved.

## Next Session Checklist

1. Confirm the active branch is based on `lxc/integrated-workflow` and inspect `git status` before editing.
2. Preserve the production/development boundary; normal development and deployment target only `hz-new-product-dev`.
3. Run backend tests, frontend tests/build and Alembic head verification before every release.
4. Update `docs/02-功能实现状态.md`, `docs/20-项目推进总控.md` and `docs/06-部署与服务器准备.md` when implementation or deployment state changes.
5. Use `neat-freak` at milestones; do not delete or archive historical requirement documents without explicit user approval.
