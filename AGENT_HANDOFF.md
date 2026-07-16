# Agent Handoff

> Updated: 2026-07-16 19:00 Asia/Shanghai

## Current Mode

The frozen front-stage flow is running in production. Continue from `docs/02-功能实现状态.md` and `docs/20-项目推进总控.md` unless the user explicitly starts a later-stage feature. Use Superpowers-style discipline and Ponytail scope control. Do not use Spec Kit again unless the user explicitly asks; the user said it can make the current work confusing. Do not put any agent/tooling content into product docs or product pages.

Production is `http://101.132.26.138:8080`, SSH alias `hz-new-product-preprod`, current API/frontend release `vb373d65`, database `workflow_prod_20260715`. Future development target is `hz-new-product-dev` (`139.224.2.166:2323`), not the production host. Do not write SSH passwords or any other credentials into repo files, docs, commits, logs, or `.env.example`; use local secret storage or prompt-time input for deployment.

## Implementation Status

- Completed: project setup, PostgreSQL/SQLite guard, Alembic migrations, two feedback workbook importers, personnel config import, one-click assignment, claim/not-claim submission metadata, supervisor review, stocking export, central traceability export, product dashboard, source upload, operator profile config UI, inline operator claim UI, local demo data script, Phase 12 source-routing / batch-claim / review-state clarification, and minimal DingTalk new-product todo card sender.
- Current verification: on 2026-07-16, backend full `pytest -q` passed `204` tests in `422.53s`; frontend `npm test` passed `45` tests and `npm run build` passed. The latest Playwright/Edge allocation check covered 2048px and 1366px: all 16 enabled operators wrap into a responsive grid with zero horizontal overflow, and “提交分配 / 运营配置” remain adjacent. Earlier mobile, sticky workload, live draft-count and native drag-order checks also passed. Production release details are recorded in `docs/06-部署与服务器准备.md`.
- Current release pointer: branch `lxc/pricing-review-edit`, deployed implementation commit `b373d65`; local repeatable period-export implementation head is `41080bc`. It remains unmerged and undeployed. No database migration, template change, production/development deployment, or service restart occurred. `lxc/listing-observation-workbench` remains a divergent branch and was not merged or overwritten; integration/deployment is a separate task. Deployment and rollback details are in `docs/06-部署与服务器准备.md`.

## Latest Business Ground Truth

- Product role names: `运营` and `主管`.
- `销售` in older wording means the same people as `运营`.
- Current first-version flow: `内部反馈表导入 -> 主管分配 -> 运营填写是否认领和认领单销 -> 主管复核汇总 -> 导出`.
- First version does **not** close the middle bridge: no procurement / supply-chain / ordering platform todos.
- First version does **not** require online-table auto writeback.
- First version is central-field-aligned export only: use `东南亚海外仓新品表-PH/TH/VN` as the target field dictionary, but do not expose an online-table writeback entry.
- If future online-table matching fails, do **not** generate an exception list or push supervisor in first version. Export should still work; external online-table handling can remain manual.
- Avoid writing the material recipient into deliverable titles or body text. Use neutral wording such as `评审材料` or `业务人员`.

## Current Source Scope

Only these two internal feedback tables are in scope now:

1. `海外仓开发部门开发新品认领-反馈`
2. `海外仓财根团队开发新品认领-反馈`

Out of current scope:

- `直发热销转海外仓销售确认`
- `销售选品备货海外仓-销售调研`
- any `选品3` / `选品4` source logic
- automatic writeback to `东南亚海外仓新品表`
- exception-list workflow for central-table mismatch

Field facts already recorded:

- `海外仓开发部门开发新品认领-反馈` current tested sheet `开发0623期` has row-level `站点` at column `A`; do not infer site from filename when row field exists.
- `海外仓开发部门开发新品认领-反馈` aligns to central-table fields by header name, not column position. Tested against `东南亚海外仓新品表-TH.xlsx` sheet `6.23`: all 73 central fields before `开发是否接受核价结果` exist in `开发0623期`; the feedback sheet has 6 extra competitor fields at `AF:AK`.
- Key tested fields for that sheet: `CB=开发是否接受核价结果`, `CC=不认领理由`, `CD=主销售员`, `CE=是否认领`, `CF=认领单销`, `CG=销售反馈 / 总结`, `CH=备注`.
- `海外仓财根团队开发新品认领-反馈` current tested sheet `5.26期` has no site field. Existing sample SKUs matched PH central table, but future non-match should not block platform claim/review/export.
- `海外仓财根团队开发新品认领-反馈` is not a central-table truncation. Import should map what it can to the central-table target fields; central-only fields that cannot be mapped or uniquely matched default to empty, not `0`, while source snapshot/trace fields remain mandatory.
- 2026-07-04 field-source correction: first-version source analysis must ignore `选品3`, `选品4`, `直发转海外仓`, old-stock, and old-research rows. Only align `选品1` and `选品2/财根`.
- `选品1` should be treated as the central new-product table before `BV` / before `开发是否接受核价结果`, plus internal operator claim columns. Use header names, not fixed column letters, because older sheets can shift columns.
- `选品2/财根` should be treated as a separate opportunity-pool structure, not a central-table slice. Its main keys are `SPU` and `SKU`; historical cost mainly maps from `进价`; claim info is spread across main salesperson and multiple salesperson/daily-sales columns.
- `海外仓开发部门开发新品认领-反馈` enters supervisor assignment only. Its source-table salesperson / claim columns are retained as prefill/reference records, but import does **not** auto-create operator claim tasks and does **not** expose pending selection1 rows to the operator self-claim pool before supervisor assignment.
- `海外仓财根团队开发新品认领-反馈` enters both supervisor assignment and the operator self-claim opportunity pool. The assigned/main salesperson can still be assigned a required claim task; other operators may self-claim the same SKU with no upper limit. Ignoring a self-claimable opportunity creates no not-claim task.
- `集团八部销售员信息表.xlsx` was the first-version operator assignment seed. The production database and the supervisor “运营配置” drawer are now authoritative for enabled people, sites, categories, priority and display order; do not rely on old hard-coded personnel counts in documents.
- Latest v1 config UI exposes `销售员`, `重点站点`, `重点品类1`, `重点品类2`, enabled/disabled, `assignment_priority` and site-local `display_order`. Same-site rows can be reordered by drag or arrow buttons and are persisted only after “保存运营配置”. `岗位`, `运营分层`, and `业务类型` are not v1 supervisor-editable fields.
- Source field snapshots are in `docs/16-新品认领反馈源表实测字段清单.md` and `docs/17-源表字段总字典.md`.

## Confirmed Front-Stage Rules

- Main SKU group is the main workflow unit.
- Child SKU is detail/export unit.
- Group is assigned together; child SKUs are not split during supervisor assignment.
- Existing source values are only prefill/reference. Platform submission is still required before supervisor review.
- Operator manually chooses whether to claim and fills claim daily sales.
- By default child SKUs are treated as selected for claim, but operator can mark some child SKUs as not claimed.
- Not-claim reason is required for not-claimed items.
- `认领单销` means daily sales; stocking quantity is `认领单销 × 30`.
- Supervisor role is fixed to `练玉君` for first version. `岗位=组长` in the salesperson config is an operator/personnel attribute, not the platform supervisor role.
- One-click auto allocation is in scope. Main SKU group is the allocation unit, child SKUs are not split.
- Auto allocation first filters enabled profiles by normalized site, then applies load-first greedy list scheduling on pending main-SKU group counts. Only when candidate loads tie does it compare category match, `assignment_priority`, site-local `display_order`, and operator name. A hit in either `重点品类1` or `重点品类2` is the same category tier. Priority is therefore a tie-breaker, not an unlimited weight. Equal-load candidates receiving unit main-SKU groups differ by at most one group within a fresh preview. If no profile matches the site, the item remains unassigned with `无站点匹配`. Historical performance is not included in v1.
- Current load is counted by main SKU groups assigned but not completed, plus draft assignments already made in the current one-click allocation run; do not balance by child SKU count in v1.
- One-click allocation defaults to all enabled operator profiles. Do not reintroduce a business UI textarea for manually typing candidate operators.
- Supervisor can review and adjust one-click allocation results before confirming and creating operator claim tasks.
- “运营配置” is grouped directly beside “提交分配” in the page toolbar and opens the existing drawer. Operator workload cards use a sticky responsive grid with no internal horizontal scrollbar; all enabled operators wrap into visible rows, and draft allocation changes update group/child-SKU counts immediately.
- Source import UI must use browser file upload by drag/drop or file picker. Server-local file path and "default workbook" wording are developer/testing conveniences only and must not appear in the business UI.
- Supervisor opportunity-pool UI must not expose a claim/recognize action. Claim submission must always be tied to a concrete operator identity.
- Operator claim UI is grouped by main SKU, with child SKU rows visible together. It is inline on the cards, not a right-side shared processing panel. Claim mode only submits `认领单销`; not-claim mode only submits `不认领原因` and optional research image evidence. The two modes are mutually exclusive.
- Operators can click `一键提交全部已填写` or `提交本组已填写`; the platform submits only child SKUs whose current draft is complete and leaves incomplete child SKUs as page drafts.
- Not-claim evidence images need a reserved UI path: paste from clipboard, drag/drop, or file picker. v1 can store attachment metadata in the claim note until a real file-storage table is added.
- If only part of a main SKU group is approved for claim, the main SKU group state is `部分认领通过`; child SKU rows show their own result as `可备货` or `已确认不认领`.
- Submit before review can be changed; after submit cannot self-withdraw unless supervisor returns for supplement.
- Supervisor review covers both claimed and not-claimed submissions.
- Claimed submission displays as `待复核-认领` / `运营已认领`; supervisor can only approve claim in the first version, with no review comment required.
- Not-claimed submission displays as `待复核-不认领` / `运营不认领`; supervisor can confirm not claim or return for supplement.
- Return-for-supplement displays as `已驳回-待运营补充`; return reason is required for not-claim submissions and is shown to the operator on the returned child SKU.
- Supervisor cannot edit operator-submitted `认领单销` or `不认领原因`; if content is wrong or incomplete, supervisor must return for supplement.
- Once supervisor confirms not-claim, the terminal state name is `已确认不认领`. First version has no automatic reopen and no platform rework entry. If business users need to adjust after export, they handle it manually in the exported / downstream stocking sheets, without flowing it back into the platform.
- Review pass only enters exportable list; Excel is generated when supervisor/data user clicks export, creating an export batch.
- Export is child-SKU detail only, no separate main-SKU summary page in v1.
- Each export batch should include two child-SKU detail outputs:
  - `备货申请表`: use the `海外仓备货申请表.xlsx` 16-column structure for downstream stocking work.
  - Full-field traceability output: generated by the same supervisor-approved export action, not an input/source workbook. Rows are the same approved child-SKU claim records; columns are `东南亚海外仓新品表-PH/TH/VN.xlsx` fields before `开发是否接受核价结果`, plus internal claim/review/export fields, kept only for leadership review and traceability.
- In `备货申请表`, `时间` uses the system write/export time, and `补货原因` stays empty for first version because this is new-product development, not replenishment.
- `备货申请表` first-version field rule:
  - `选品1`: `成本价` from central/source `商品成本-含税（元）`; `单个体积` from `包装后体积`.
  - `选品2/财根`: `成本价` from `进价` when available; `单个体积` from mapped per-piece volume when reliable, otherwise leave empty rather than guessing.
  - `备货单销` from platform-approved `认领单销`; `备货数量 = 认领单销 × 30`; `货值 = 成本价 × 备货数量`; `体积 = 单个体积 × 备货数量`.
- Export batch minimum metadata: exporter, export time, export file name, export scope.
- The manager-only export center reads `GET /stocking/export-periods` and lists every non-disabled imported business period newest-first, including a zero-count period. It defaults to the newest period and removes unscoped download buttons; every download is explicitly scoped to its period.
- A repeated period download includes all currently approved rows for that period. Each download creates a new audit batch and audit rows; a repeat does not regress or re-advance a claim or opportunity already in a later workflow state.
- New and bulk review records are claim-scoped. A historical null `approved` review covers every claim that existed at review time; historical null `confirmed_not_claim` and `returned_for_supplement` reviews target only the latest platform claim submission that existed then.
- If multiple operators claim the same child SKU and pass review, export/stocking output creates one row per operator claim, never merges them into one SKU row.
- Operator-submitted internal fields, especially `不认领原因` / `不认领理由`, must keep first-created time and last-updated time.

## Caigen Opportunity Pool Note

The generic `SKU 商品池` remains out of first-version scope unless explicitly re-approved. The confirmed v1 pool behavior applies only to `海外仓财根团队开发新品认领-反馈`: main assigned operator must handle claim/not-claim; other operators may self-claim the same SKU, with unlimited claimers and separate review/export rows.

## Latest Export / Source Audit Artifacts

- `backend/app/services.py` now exports the full central traceability structure as 73 central fields before `开发是否接受核价结果` plus platform fields. Source snapshot values are read by normalized header name.
- `backend/app/selection1_importer.py` and `backend/app/selection2_importer.py` store `fields_by_header` snapshots for reliable export mapping.
- Preview/audit outputs from 2026-07-04:
  - `outputs/export_preview_20260704/选品1重新导入模拟-新品中央字段导出.xlsx`
  - `outputs/export_preview_20260704/选品1重新导入模拟-备货申请表.xlsx`
  - `outputs/export_source_audit_20260704/选品1选品2-备货申请表字段口径核对-v2.csv`
- Real `选品1` reimport simulation on `开发0623期`: central traceability output had 68 non-empty fields out of 73 for the sampled SKU. Remaining blanks were actually blank upstream fields, not export mapping failure.

## Local Demo Data

- `backend/scripts/seed_demo_statuses.py` seeds local-only demo data with `source_type=local_demo_status_coverage`.
- The script clears only its own prior demo records, then creates operator profiles and opportunities covering pending assignment, assigned, open claim pool, claim submitted, rejected/not-claim review, returned for supplement, ready for stocking, confirmed not-claim, and mixed main-SKU status.
- Run from `backend`: `..\.venv\Scripts\python.exe scripts\seed_demo_statuses.py`.

## DingTalk / Notification Direction

- Do not create DingTalk todo tasks in first version.
- First-version DingTalk capability choice is `enterprise internal app + web application + work notification`.
- The web application is only a DingTalk entry wrapper for our own cloud-hosted React/FastAPI platform URL; the actual system still runs on our server.
- Account login baseline is implemented: backend issues signed Bearer tokens from `/auth/login`, `/auth/me` reads the current user, and production/shared deployments require enabled `role_mapping` rows before users can enter. Current first-version account login uses real name + password; if a user has no stored password yet, the default password is the lowercase pinyin initials of the name plus `123456`, then the user can change it through `/auth/password`.
- First-version accounts agreed on 2026-07-06: `刘学城` is `super_admin` and logs in with initial password `lxc123456`; `练玉君` is the supervisor/manager and logs in with initial password `lyj123456`.
- Super-admin is a permission role, not a hard-coded visible account name. `刘学城` with `role_mapping.role=super_admin` has all manager/operator permissions. Do not create or expose an account literally named `超级管理员`.
- Core role guards are in place behind effective auth mode: managers handle import, assignment, review, export, admin, notifications; operators handle claims and only their own pending tasks when auth is enabled.
- Current auth does not yet exchange a real DingTalk H5 `authCode` for `dingtalk_user_id`. Production DingTalk免登 still needs the official DingTalk user identity exchange wired after the app/corp parameters are confirmed.
- Create internal system todos; DingTalk work notification is the personal push + entry link channel.
- User interaction is handled by the platform page opened from DingTalk; submitted data writes to the platform database in v1.
- DingTalk online-table writeback remains a later capability, not first-version implementation.
- Entry link carries only positioning parameters such as `taskId`, `module`, `from=ding`.
- User identity should come from DingTalk H5免登, then map to system user/role.
- Push dedupe key: `taskId + status + receiverUserId`.
- DingTalk integration smoke test on 2026-07-03:
  - Enterprise access token retrieval succeeded.
  - Work notification text message to `刘学城` succeeded via `asyncsend_v2`; result check returned progress 100%, no failed/forbidden/invalid users, target read.
  - Direct contact search endpoint returned missing scope `qyapi_addresslist_search`; current fallback is department traversal to resolve DingTalk userId.
  - Do not log or commit DingTalk access tokens, Client Secret, or full userId values.
- 2026-07-04 update: the user explicitly prioritized DingTalk interactive card delivery for new-product todo reminders. Current active template is documented in `docs/19-钉钉新品待办卡片接入说明.md`; enterprise robot delivery and the current template were smoke-tested successfully. Work notification `link` / `action_card` remains a fallback path.
- Minimal backend sender is implemented in `backend/app/dingtalk_card_sender.py`, with route `POST /notifications/dingtalk/new-product-todo-card`. It sends only reminder + platform entry, not DingTalk Todo, online-table writeback, or card-side business detail.
- Automatic DingTalk card trigger wiring is implemented behind `DINGTALK_CARD_AUTOSEND_ENABLED=false` default. Current first-version reminder rules:
  - Operator card only shows `待认领` and `待补充`.
  - Operator `待认领` count = pending `sales_claim` tasks for that operator, excluding `returned_for_supplement`, grouped by main SKU. Assignment and reassign may refresh the operator card.
  - Operator `待补充` count = pending `sales_claim` tasks for that operator in `returned_for_supplement`, grouped by main SKU. Supervisor return-for-supplement may refresh the operator card.
  - Supervisor card only shows `认领待复核` and `不认领待复核`; it must be refreshed by hourly aggregate job/manual trigger, not by every operator claim/not-claim submission.
  - Do not notify supervisor for `待分配`; supervisor initiates allocation themselves.
  - Later `到货未处理` / `淘汰款` reminders are planned but not implemented in the current card口径.
- Before enabling automatic sends, fill `role_mapping.dingtalk_user_id` for the corresponding operator / supervisor names and set `PLATFORM_BASE_URL` to the cloud platform entry URL. Current local DB only has sample `刘学城` role mappings with empty DingTalk userId, so real card delivery is not yet addressable from local data.
- DingTalk cards still only provide reminder + entry. Robot/card messages jump into the same platform URL and do not replace platform auth, task state, or database writes.
- Known weekly rhythm: Wednesday morning supervisor imports/starts allocation; Thursday 18:00 is the current claim cutoff direction. Exact SLA per node is still pending business confirmation.

## Object Storage / OSS

- Aliyun OSS endpoint for this project: `oss-cn-shanghai.aliyuncs.com`
- Aliyun OSS bucket for this project: `hz-sea-np-flow-prod`
- These values are non-secret deployment/config references. Keep access keys, secret keys, STS tokens, signed URLs, and upload policies out of repo files and store them only in local secret storage or deployment secrets.
- First likely use: product images, not-claim evidence images, exported Excel files, and other platform attachments when dedicated file storage is implemented.
- Local Codex secret file: `C:\Users\86173\.codex\secrets\Hengzhe-New-Product-Workflow\oss.credentials.json`.
- Local Windows user environment has been prepared with:
  - `OSS_UPLOAD_ENABLED=true`
  - `OSS_ENDPOINT=oss-cn-shanghai.aliyuncs.com`
  - `OSS_BUCKET=hz-sea-np-flow-prod`
  - `OSS_PUBLIC_BASE_URL=https://hz-sea-np-flow-prod.oss-cn-shanghai.aliyuncs.com`
  - `OSS_CREDENTIALS_FILE=C:\Users\86173\.codex\secrets\Hengzhe-New-Product-Workflow\oss.credentials.json`
- Cloud deployment should set the same non-secret values plus `OSS_ACCESS_KEY_ID` and `OSS_ACCESS_KEY_SECRET` through the server secret manager / container environment. Do not copy the local JSON file into Git.
- Important config precedence: current backend config reads `OSS_ACCESS_KEY_ID` / `OSS_ACCESS_KEY_SECRET` environment variables before `OSS_CREDENTIALS_FILE`. If old environment variables exist, they override the local secret file.
- Latest verified credential mask is `LTAI***Qxbq`. A stale environment AccessKey mask `LTAI***WyMF` caused the latest 403 confusion by overriding the secret file. Do not write the full AccessKey Secret into code, docs, logs, or commits.
- 2026-07-06 user confirmation: `hz-sea-np-flow-prod` upload/delete is verified with the `LTAI***Qxbq` credential pair. For local runs and cloud deployment, either remove stale `OSS_ACCESS_KEY_ID` / `OSS_ACCESS_KEY_SECRET` or set both through the secret manager to the verified pair. The plaintext AccessKey Secret was provided in chat for deployment use, but must remain only in secret storage / deployment secrets, not in repository files.
- Implementation status on 2026-07-03: product-image extraction uploads to OSS when enabled, otherwise falls back to local `/uploaded-sources/product-images/...`.
- OSS historical probes on 2026-07-03 and 2026-07-04 returned `403 AccessDenied`. Representative request IDs: `6A47870A9FA7DD38327FDC9A`, `6A478726199EDA36342CCFF3`, `6A48A9BB5073033737923FD9`, `6A48ACACB6DB8D3835AD0AE5`, `6A48C3AA0EF7D03531AA6010`.
- OSS correction / verification on 2026-07-06: after clearing only the stale OSS env vars in the test process, backend config read the secret file credential mask `LTAI***Qxbq`; direct `PutObject` to `product-images/connectivity/` succeeded with status 200, request ID `6A4B12BD761454303865B431`; direct delete succeeded with status 204, request ID `6A4B12BD7614543038A5B431`.
- Formal project upload path via `upload_product_image()` also succeeded and produced URL `https://hz-sea-np-flow-prod.oss-cn-shanghai.aliyuncs.com/product-images/connectivity_probe/row-20260706-qxbq-20260706T022813Z.png`; the probe object was deleted afterward with status 204, request ID `6A4B12CCA1570F303209406F`.
- Current OSS conclusion: bucket write/delete permission is working for `LTAI***Qxbq`. Before local run or deployment, either clear stale `OSS_ACCESS_KEY_ID` / `OSS_ACCESS_KEY_SECRET` env vars or set them to the verified credential through the secret manager. Keep server-local file storage as a fallback for runtime outages, not as the primary assumption.
- 2026-07-07 cloud update: cloud `.env` has OSS upload enabled through deployment secrets, upload/delete was verified from the `api` container, and existing cloud product image references were migrated from local `/uploaded-sources/product-images/...` to OSS URLs. Verification count after migration: `local_left=0`, `oss_count=269`. A database backup was created on the server before migration at `backups/pre-oss-image-migration-20260707-163344.sql`.
- 2026-07-07 export behavior: central traceability exports embed product images into the `产品图片` column instead of writing the URL text. If an image cannot be read from local fallback storage or project OSS, the cell is left blank; it does not fall back to a link string.
- 2026-07-07 central-schema rule: because `东南亚海外仓新品表-PH.xlsx` sheets have different column counts across dates, v1 freezes one canonical central export schema from PH `6.23`, columns `A:CB` through `开发是否接受核价结果`. Imports keep source values by normalized header name in `fields_by_header`; export writes the fixed schema by field name, not by source column position. Source fields outside the canonical schema stay in snapshots until the schema is explicitly upgraded.

## Confirmed First-Version Product Dashboard

- `商品看板` is in first-version scope. It is the all-product status overview, not a later-stage workflow page and not the same thing as the opportunity pool.
- The dashboard lists complete platform product records grouped by main SKU, with expandable child SKU rows, visible to operators and supervisor.
- `开品理由` is a main-SKU-group level display field. Child SKU rows should not repeat it.
- First version has no richer product detail page/drawer. Dashboard cards should keep only `展开 / 收起子 SKU`; do not add a duplicate `查看详情` button unless it opens a genuinely richer detail view.
- Default filters: site, operator, status, health label, level-1/level-2 category, source batch. Search supports main SKU, child SKU, product name, keyword.
- Keep `商品看板` separate from `机会池`: dashboard shows all product statuses; opportunity pool shows only pending / claimable new-product opportunities.
- Health labels are `正常 / 需关注 / 异常`, display/filter only. First version uses clear workflow-state triggers, not a scoring model. Later arrival / monitoring triggers should be added when those stages are implemented.

## Back-Stage Planning Already Discussed

Keep these as later-stage planning, not first-version implementation unless user asks:

- 到货承接: source is PLM `真仓库存明细数据-普通商品-汇总数据` downloaded through the PLM interface / download center, not browser automation by default. Daily pull target is around 08:00, pulling the previous Asia/Shanghai calendar day. Tested 2026-07-02: login, download-center listing, and direct xlsx download succeeded. First pass monitors arrival time only; source fields include `子SKU`, `主SKU`, `海外仓`, `国家`, `预计到港时间`, `最后一次入库时间`, `首次上架时间`, `海外仓可发`, `真仓库存`.
- PLM credentials are saved locally at `C:\Users\86173\.codex\secrets\Hengzhe-New-Product-Workflow\plm.credentials.json`; this file is outside the repo and should be read at runtime to log in for fresh tokens. Do not copy credentials into docs, code, commits, or work logs.
- DingTalk internal H5 app credentials are saved locally at `C:\Users\86173\.codex\secrets\Hengzhe-New-Product-Workflow\dingtalk.credentials.json`; this file is outside the repo and stores App ID, AgentId, Client ID, and Client Secret. Do not copy credentials into docs, code, commits, or work logs.
- After actual warehouse entry: each main SKU does secondary market research before listing.
- Secondary market research: operator fills; supervisor can see global results. Normal path goes into pricing/listing. If market is no longer viable, submit supervisor confirmation with actions such as not listing, observe, or return for supplement.
- Pricing review: original suggested price, secondary research reference price, final listing price, adjustment reason.
- Listing confirmation: ItemID, listing link, shop, selling price, listing date.
- Weekly monitoring starts from listing date, every 7 days, records by ItemID, main SKU summarizes.
- Monitoring fields: sales, sales amount, inventory, ad spend, ROI/ACOS, abnormal labels; operator fills action/remark.
- `【市场监控】海外仓精品市场调研.xlsx` is a post-export market-monitoring / secondary-research work table, not the PLM raw table and not the stocking application table. Current local workbook sheets: `说明`, `PH精品`, `TH精品`, `VN精品`, `MY精品` (empty). Current local workbook has `AO=产品定位（引流款/利润款/淘汰款）` and `AQ=6.22号公司:单销`; use header matching, not fixed column letters. If secondary research marks a product as `淘汰款`, notify supervisor to update product positioning in the external system, so clearance sales do not trigger false high-sales auto replenishment.
- Detailed per-column source confirmation for the market-monitoring workbook is in `docs/18-市场监控表字段来源确认问题清单.md`. Keep that as the single editable checklist for exact source table / field / logic / timing.
- Four-week summary: generated after day 28; operator fills, supervisor views summary.

## Prototype Deliverable

Current reviewed prototype files:

- `outputs/product_review_20260630/新品流程产品原型.html`
- `outputs/product_review_20260630/新品流程产品原型-单文件版.html`
- `outputs/product_review_20260630/新品流程产品原型-可发送.zip`

The user already said the prototype was verified as OK. Do not reopen prototype design unless requested.

## Must-Read In New Session

Read these before asking or changing anything:

1. `AGENT_HANDOFF.md`
2. `docs/20-项目推进总控.md`
3. `docs/19-钉钉新品待办卡片接入说明.md`
4. `docs/02-功能实现状态.md`
5. `docs/00-新会话交接.md`
6. `docs/01-需求文档-东南亚新品流程.md`
7. `docs/14-新品流程产品原型需求确认.md`
8. `docs/15-新品流程业务会议待确认问题清单.md`
9. `docs/16-新品认领反馈源表实测字段清单.md`
10. `docs/17-源表字段总字典.md`

Optional context if implementation resumes later:

- `docs/05-分配任务规则设计草案.md`
- `docs/09-MVP第一版-选品1单表跑通规格.md`
- `docs/10-前端UX与功能测试验收清单.md`

## Next Session Start

Do **not** ask again whether first version is export-only. It is already confirmed:

```text
第一版正式冻结为：只导入、分配、认领/不认领、主管复核、导出；不做在线表自动写回入口。
```

If the user asks "接下来做什么", continue from `docs/20-项目推进总控.md` and `docs/02-功能实现状态.md`:

1. Read `docs/06-部署与服务器准备.md` and confirm which host is production versus development.
2. Before changing code, fetch `lxc/pricing-review-edit` or its eventual merged base and inspect the active worktree status.
3. Re-run backend tests and frontend test/build before any release.
4. Develop later-stage work on `hz-new-product-dev`; production changes require an explicit release request and candidate-container health check.
5. Production releases must preserve PostgreSQL, Redis, worker and scheduler, then verify Caddy Admin API upstreams and public static asset hashes.

Only return to `docs/15` for later-stage open questions such as PLM 到货、二次调研、刊登、监控、四周总结, not for the frozen first-version export-only boundary.

## New Session Opening Prompt

```text
请先读取 AGENT_HANDOFF.md、docs/20-项目推进总控.md 和 docs/02-功能实现状态.md，以它们为最新口径继续，不要重新猜需求。

请读取并以 AGENT_HANDOFF.md 为准，同时查看：
docs/20-项目推进总控.md
docs/19-钉钉新品待办卡片接入说明.md
docs/02-功能实现状态.md
docs/00-新会话交接.md
docs/01-需求文档-东南亚新品流程.md
docs/14-新品流程产品原型需求确认.md
docs/15-新品流程业务会议待确认问题清单.md
docs/16-新品认领反馈源表实测字段清单.md
docs/17-源表字段总字典.md

使用 Ponytail 原则控制范围，不要过度设计。不要使用 Spec Kit，除非我明确要求。

当前最新口径：
第一版只围绕两张内部反馈表做导入、主管分配、运营认领/不认领、主管复核和导出。
中间桥、在线表自动写回、匹配异常清单、采购/供应链待办都先不做。
第一版“只导出，不做在线表自动写回入口”已经确认，不要再问。

请先告诉我当前已完成、未完成、下一步建议；如果继续写代码，优先从本地演示验证和剩余 UI/导出问题开始。
```

## Guardrails

- Do not add Ponytail, Superpowers, Spec Kit, OpenClaw-style platforms, or other external agent tooling to business runtime dependencies. The project module is named `notification-adapter`.
- Do not expose internal status codes on product pages; show Chinese business states only.
- Do not include internal Agent / Superpowers / Spec Kit process text in product pages or business-facing docs.
- Do not reintroduce `改派` unless user explicitly asks; current flow is allocation, claim/not claim, review, export.
- Do not revive automatic central-table writeback or exception-list workflow as first-version scope.
- Current dirty docs are intentional planning work. Do not revert user or prior planning changes.
