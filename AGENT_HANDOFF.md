# Agent Handoff

> Updated: 2026-07-22 20:00 Asia/Shanghai

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
| Development | `http://139.224.2.166:18081` | `af4addc3f765` | Unified branch validation and approved Liu-only historical-arrival pilot. SSH alias: `hz-new-product-dev`. |

Production database is `workflow_prod_20260715`; development database is `workflow_dev_20260715`. Databases, Redis, uploads, volumes, ports and environment variables are isolated. Never commit passwords, tokens, cookies, private keys or `.env` files.

PLM arrival endpoint settings and credentials are stored separately in both server `.env` files. `PLM_SYNC_ENABLED` remains `false` in both environments; do not enable it or restart production without explicit approval.

`caigen-arrival-notifier` remains the only production arrival-card sender on `101.132.26.138`. The one explicit development exception is the isolated historical watchlist pilot described below: it can send only to 刘学城, keeps all global switches false and never writes workflow tables. Development does not receive a feed from the production notifier. The template is selected through `DINGTALK_ARRIVAL_CARD_TEMPLATE_ID`; never commit the environment value.

## Development Deployment: `af4addc3f765`

The historical-arrival pilot release is running only at `http://139.224.2.166:18081`. The deployed code commit is `af4addc3f765`; the canonical branch `lxc/integrated-workflow` contains that commit. Existing front-end behavior and assets are unchanged.

- Local verification passed: backend `356 passed`, focused Item reconciliation `12 passed`, both pilot reviews approved, Alembic `e1f2a3b4c678 (head)` and `git diff --check`. No front-end code changed; the prior `129 passed` and production build remain the current front-end baseline.
- Release package: `/opt/hengzhe-new-product-dev/releases/af4addc3f765.tar.gz`, SHA-256 `8a1961df9b8525af181bacff171b1a09a5d5a5911c48d5a082c94f544c57b11f`.
- Pre-release backup directory: `/opt/hengzhe-new-product-dev/backups/historical_arrival_pilot_20260722_194109/`; it contains the gzip-checked database dump, mode-600 `.env` copy, prior app archive and baseline counts. Rollback scheduler image: `hengzhe-new-product-dev-scheduler-backup:b0f27fde5109_20260722_194109`.
- Only `scheduler` was rebuilt and recreated (`35a8baef... -> ce8051c8...`). API, worker, frontend, reverse-proxy, PostgreSQL and Redis kept their container IDs; every active container has `RestartCount=0`.
- Public and internal health return `ok/development`; current assets are `/assets/index-Dyt4ZkdJ.js` and `/assets/index-BiB-4QeZ.css`. `PLM_SYNC_ENABLED=false`, `WORKFLOW_AUTOMATION_ENABLED=false` and `DINGTALK_CARD_AUTOSEND_ENABLED=false` remain unchanged.
- Runtime watchlist `/data/plm/historical-watchlist.json` has 2,237 unique keys and SHA-256 `c9ca8fd4dd2bc9c625649ca6b1561a1f74b62acf64de58f02579010d886207`. A no-send preview for 2026-07-01 matched 3 rows; the pilot state file remained absent and the five baseline workflow-table counts were unchanged.
- Development cron `/etc/cron.d/hengzhe-new-product-historical-arrival-pilot` starts on 2026-07-23: 08:00 downloads the prior Beijing day, 09:00-23:45 retries every 15 minutes under a non-blocking lock. Matches are chunked at 20 and delivered only to the uniquely resolved 刘学城 account; zero matches send nothing.
- Production was not connected, deployed, restarted or modified.

## Verified Baseline

- Deployed code commit: `af4addc3f765`; `lxc/integrated-workflow` contains it.
- Backend: `356 passed`. Frontend remains unchanged at the prior `129 passed` plus TypeScript/Vite production-build baseline.
- Alembic: source and `workflow_dev_20260715` are at `e1f2a3b4c678 (head)`.
- Development health is `ok/development` inside the server and through the public `18081` path. Current assets are `/assets/index-Dyt4ZkdJ.js` and `/assets/index-BiB-4QeZ.css`.
- PostgreSQL and Redis container IDs remain `0383695d...` and `a764cb3f...`; API, worker, frontend and reverse-proxy also retained their prior IDs. Only scheduler changed to `ce8051c8...`; all have `RestartCount=0`.
- A 2026-07-22 read-only live PLM check downloaded and schema-validated historical exports without changing workflow-table counts: 2026-06-22 produced 652 parsed restock rows and zero new arrivals; 2026-07-01 produced 843 parsed rows, including four new arrivals and 839 restocks. None of the four new-arrival keys has an exact current platform match because the development database lacks the corresponding formally exported waiting-arrival records. The current exact-match write transition is therefore still open.
- A read-only DingTalk Sheet API check resolved node `6LeBq413JAzx7YBNCrBom74n8DOnGvpb` and its `精品流程` worksheet. Of 11 unique `main SKU + country + salesperson` groups represented by the supplemental workbook's 35 arrival-tagged rows, 8 groups matched 25 shop + Item rows; three groups were absent and one additional main-SKU match had a conflicting salesperson. All four-week metric cells in the 25 exact-responsibility matches were empty. Treat this sheet only as a historical listing reconciliation candidate; FineBI raw rows remain the weekly metric source.
- A read-only audit of the downloaded TH/VN/PH historical new-product workbooks produced 2,237 unique `country + child SKU` watch keys and 3,842 potential unique responsibility keys after separating rejection text, orphan rows and exact duplicates. 1,087 SKUs have multiple historical claimants. The files contain no actual arrival, shop or Item evidence; keep source file/hash/sheet/row/column traceability and do not replay them as completed workflow states.
- Fourteen validated FineBI periods from `0416-0422` through `0716-0722` contained 62,223 target-country mapping candidates. They matched 566 of the 2,237 watch keys: 202 unique pending-confirmation candidates, 364 multiple candidates and 1,671 unmatched. The single user workbook period `0423-0429` contains valid mappings but matched zero watch keys. No candidate was applied to the database.
- Review artifact: `outputs/2026-07-22-historical-item-reconciliation.xlsx`, SHA-256 `333efcd95395c630a54484ff7c68e18a1e7506b210d151f0e52538d53e384d20`; sheets separate summary, unique candidates, exploded multiple candidates, unmatched keys, anomalies and source periods.
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
- Include the DingTalk `精品流程` historical listing rows in that report as a separate candidate source. Match only after country and salesperson alignment, keep the one observed responsibility conflict and three missing groups explicit, and never infer child-SKU, arrival or weekly metrics from this sheet.
- Review the 202 unique FineBI candidates before any controlled prefill; keep the 364 multiple candidates manual and ignore the 1,671 unmatched for now. Old claimants remain provenance while the current PLM salesperson is authoritative for arrival notification and exact linkage.
- No provided asset implements real-time `child SKU -> shop + Item` discovery. FineBI raw rows include `ITEMID + 主SKU + 店铺 + 审核时间` and therefore provide delayed historical candidates after financial activity, but contain no child SKU and do not prove real-time listing. PLM and the ERP product-list wrapper also do not return shop/Item; unmatched records remain operator-entered.
- After the cutover and reconciliation gate, run one controlled current-code PLM exact-match transition when a newly and formally exported development record reaches `waiting_arrival`; keep persistent automation and card sending disabled and require exactly one planned match before the one-time write.
- Development does not currently provide all five ERP settings (`ERP_LOGIN_URL`, `ERP_PRODUCT_LIST_URL`, `ERP_DOWNLOAD_LIST_URL`, `ERP_USERNAME`, `ERP_PASSWORD`); the referenced asset document contains no uniquely locatable credentials. Real ERP volume lookup remains unaccepted until values are supplied through development `.env` only. The deployed fallback is manual dimensions with automatic volume calculation.
- The weekly Item source was already delivered in `E:\Project\hermes\group8_item_week_package_20260715.zip` and exists in Hermes: FineBI report `35d21769f7a14a6191cdc4f4a211a04a`, widget `ItemID财务数据八部`, payload `config/finebi_payloads/itemid_finance.json`. Historical-candidate parsing is implemented; the remaining work is aggregating tracked `Item + shop + period` metrics into `apply_week_metrics(...)`, with snapshots, scheduling and retries. Do not consume the filtered finished sheet.
- Real scheduling, retry monitoring and operator message delivery for weekly Item metrics remain unconnected.
- Production release of the unified branch is not approved.

## Next Session Checklist

1. Confirm the active branch is based on `lxc/integrated-workflow` and inspect `git status` before editing.
2. Preserve the production/development boundary; normal development and deployment target only `hz-new-product-dev`.
3. Run backend tests, frontend tests/build and Alembic head verification before every release.
4. Check the development pilot log after its first 08:00/09:00 cycle; if a card is sent, verify only 刘学城 received it and the five workflow-table counts remain unchanged.
5. Update `docs/02-功能实现状态.md`, `docs/20-项目推进总控.md` and `docs/06-部署与服务器准备.md` when implementation or deployment state changes.
6. Use `neat-freak` at milestones; update only the active document set and keep `docs/archive/` read-only.
