# Agent Handoff

> Updated: 2026-07-22 16:32 Asia/Shanghai

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
| Development | `http://139.224.2.166:18081` | `b0f27fde5109` | Unified branch validation and business UAT only. SSH alias: `hz-new-product-dev`. |

Production database is `workflow_prod_20260715`; development database is `workflow_dev_20260715`. Databases, Redis, uploads, volumes, ports and environment variables are isolated. Never commit passwords, tokens, cookies, private keys or `.env` files.

PLM arrival endpoint settings and credentials are stored separately in both server `.env` files. `PLM_SYNC_ENABLED` remains `false` in both environments; do not enable it or restart production without explicit approval.

`caigen-arrival-notifier` is a separate service co-hosted with the workflow production environment on `101.132.26.138`. It is the only sender of arrival cards; neither workflow environment sends arrival cards. The workflow still owns its elimination-summary reminder. Development must not receive a persistent feed from the production notifier. Its current arrival/summary card template is selected through `DINGTALK_ARRIVAL_CARD_TEMPLATE_ID`; never commit the environment value.

## Development Deployment: `b0f27fde5109`

The compact listing-workbench release is running only at `http://139.224.2.166:18081`. The deployed code commit is `b0f27fde5109`; the canonical branch `lxc/integrated-workflow` contains that commit. This handoff-only documentation update is not deployed.

- Listing controls now use compact gaps and padding; checkboxes no longer inherit full-width input styles; the result grid aligns at the top; the batch bar stays on one row above 560 px and stacks only on narrow phones.
- Local verification passed: backend `308 passed`, frontend `129 passed`, TypeScript/Vite production build, Alembic `e1f2a3b4c678 (head)` and `git diff --check`.
- Release package: `/opt/hengzhe-new-product-dev/releases/b0f27fde5109.tar.gz`, SHA-256 `db6b6e2f6cf3251ded69855c9a595db80105d405a86b90b46f4b3d29cd764224`, 236 items.
- Pre-release backup: `/opt/hengzhe-new-product-dev/backups/workflow_dev_before_b0f27fde5109_20260722_153034.sql.gz` (410909 bytes, mode 600, gzip checked); environment backup: `/opt/hengzhe-new-product-dev/backups/config/.env_before_b0f27fde5109_20260722_153034` (mode 600); previous app: `/opt/hengzhe-new-product-dev/app.previous_b0f27fde5109_20260722_153034`; rollback image: `hengzhe-new-product-dev-frontend-backup:b0f27fde5109_20260722_153034`.
- Only `frontend` was rebuilt and recreated. API, worker, scheduler, reverse-proxy, PostgreSQL and Redis kept their container IDs and `RestartCount=0`.
- Public and internal health return `ok/development`; current assets are `/assets/index-Dyt4ZkdJ.js` and `/assets/index-BiB-4QeZ.css`. `PLM_SYNC_ENABLED=false`, `WORKFLOW_AUTOMATION_ENABLED=false` and `DINGTALK_CARD_AUTOSEND_ENABLED=false` remain unchanged.
- At a 799 px viewport, the batch bar measures 51 px high (previously 164), the checkbox 13×13 px (previously 61×34), and one collapsed group 46 px high (previously 329); expanded content has no page-level horizontal overflow and the console log is empty.
- The user confirmed that the sales-self branches, application entry/autosave/submit and manager selected export write-path checks have no remaining issue. Production was not connected, deployed, restarted or modified.

## Verified Baseline

- Deployed code commit: `b0f27fde5109`; `lxc/integrated-workflow` contains it. This handoff-only documentation update does not change the development runtime.
- Backend: `308 passed`. Frontend: `129 passed`. TypeScript/Vite production build passed.
- Alembic: source and `workflow_dev_20260715` are at `e1f2a3b4c678 (head)`.
- Development health is `ok/development` inside the server and through the public `18081` path. Current assets are `/assets/index-Dyt4ZkdJ.js` and `/assets/index-BiB-4QeZ.css`.
- PostgreSQL and Redis container IDs remain `0383695d...` and `a764cb3f...`; API, worker, scheduler and reverse-proxy also retained their prior IDs, all with `RestartCount=0`.
- A 2026-07-22 read-only live PLM check downloaded and schema-validated historical exports without changing workflow-table counts: 2026-06-22 produced 652 parsed restock rows and zero new arrivals; 2026-07-01 produced 843 parsed rows, including four new arrivals and 839 restocks. None of the four new-arrival keys has an exact current platform match because the development database lacks the corresponding formally exported waiting-arrival records. The current exact-match write transition is therefore still open.
- Development UAT uses the existing 刘学城 account: `super_admin` supplies the supervisor and operator views, and an enabled Thailand operator profile is linked to the same user.

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
- The listing workbench keeps full viewing and editing in a compact collapsible main-SKU / Item / visible-week layout. Its title, common filters, result count and batch action remain outside the independently scrolling result pane; controls no longer stretch at tablet width, future weeks stay hidden, and current pending-data weeks show only the expected data date.

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

- Confirm a new-business cutover period and first users; from that period onward, new opportunities enter the platform first and the old workbook is read-only or receives platform exports, with no dual entry.
- Produce a read-only reconciliation report for the two historical workbooks before any importer: their live A:AR layout conflicts with the documented A:AO contract, 39 within-file duplicate-key groups contain field conflicts, one row is exactly duplicated across files, and 420 formula cells contain errors. Do not use last-row-wins or overwrite non-empty platform values.
- After the cutover and reconciliation gate, run one controlled current-code PLM exact-match transition when a newly and formally exported development record reaches `waiting_arrival`; keep persistent automation and card sending disabled and require exactly one planned match before the one-time write.
- Development does not currently provide all five ERP settings (`ERP_LOGIN_URL`, `ERP_PRODUCT_LIST_URL`, `ERP_DOWNLOAD_LIST_URL`, `ERP_USERNAME`, `ERP_PASSWORD`); the referenced asset document contains no uniquely locatable credentials. Real ERP volume lookup remains unaccepted until values are supplied through development `.env` only. The deployed fallback is manual dimensions with automatic volume calculation.
- The weekly Item source was already delivered in `E:\Project\hermes\group8_item_week_package_20260715.zip` and exists in the Hermes automation: FineBI report `35d21769f7a14a6191cdc4f4a211a04a`, widget `ItemID财务数据八部`, payload `config/finebi_payloads/itemid_finance.json`. The raw export contains Item, shop, order count, revenue and gross profit; the `< 7` filter is applied later by `build_item_workbook()`, not by the payload. Do not ask for a new endpoint or consume the filtered finished sheet. The open work is a small raw-export adapter into `apply_week_metrics(...)`, source snapshots, scheduling and retries.
- Real scheduling, retry monitoring and operator message delivery for weekly Item metrics remain unconnected.
- Production release of the unified branch is not approved.

## Next Session Checklist

1. Confirm the active branch is based on `lxc/integrated-workflow` and inspect `git status` before editing.
2. Preserve the production/development boundary; normal development and deployment target only `hz-new-product-dev`.
3. Run backend tests, frontend tests/build and Alembic head verification before every release.
4. Update `docs/02-功能实现状态.md`, `docs/20-项目推进总控.md` and `docs/06-部署与服务器准备.md` when implementation or deployment state changes.
5. Use `neat-freak` at milestones; update only the active document set and keep `docs/archive/` read-only.
