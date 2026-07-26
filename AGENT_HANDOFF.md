# Agent Handoff

> Updated: 2026-07-26 15:51 Asia/Shanghai

## Start Here

The canonical base branch is `lxc/integrated-workflow`. The current development/UAT branch is `lxc/uat-usability-fixes`; development runs `cced0b9-post-uat-followup-20260724_220446` on top of full release `cced0b9-later-uat-full-20260724_150554`, with the 后半段 UAT data reset for `后半段UAT-20260724`. Production was used only for read-only account/role/operator-profile checks and was not deployed, restarted or modified.

Read these files before changing behavior:

1. `docs/2026-07-09-已确认需求记录.md` — highest-priority confirmed business rules.
2. `docs/02-功能实现状态.md` — implementation, verification and open work.
3. `docs/20-项目推进总控.md` — current delivery order.
4. `docs/06-部署与服务器准备.md` — production/development separation and rollback.
5. `docs/21-后半段需求领导对齐问题清单.md` — later-stage confirmed rules and remaining external inputs.

Do not infer current behavior from old plans or prototypes when they conflict with the confirmed record.

For future code review, use GPT-5.5 only. Do not request GPT-5.6 / Sol unless the user explicitly changes this rule.


## 接管边界（给下一模型）

这份项目现在的关键不是继续猜业务，而是守住边界：

1. 环境边界：开发验证只用 `http://139.224.2.166:18081` / `workflow_dev_20260715` / SSH alias `hz-new-product-dev`；生产 `101.132.26.138:8080` 不连接、不部署、不写库、不重启，除非用户重新给出明确生产窗口。
2. 事实源边界：PLM Excel 只认到货事实和当前销售员；FineBI 只认 `店铺 + Item + 周期` 的刊登与周指标；三国历史新品表、财根开发表、市场监控和刊登监控只做历史来源证据，不互相替代。
3. 共享 Item 边界：FineBI 同一 `店铺 + Item` 对多个主 SKU / 子 SKU 是 `共享Item汇总`，不是冲突；指标只保存一份 Item 汇总，代表主 SKU 只用于归档展示，不做 SKU 级业绩拆分。
4. 历史档案边界：`historical_market_monitor_archive` / `historical_archive` 是“可查可追溯”档案层；它不能自动创建 FlowTask、认领、备货、二次调研、刊登或观察任务。当前待办激活必须另做规则确认。
5. 缺字段边界：历史二次结论、产品定位、目标单销、卖点总结缺失就留空；前端可以显示“待补”，不得写默认业务值。开发询价、成本和价格参考从 `snapshot.development_source` 展示兜底。
6. 采购边界：当前采购/备货表不是到货依据；到货仍以 PLM 为准。采购侧后续最多先做对账导入，不直接推进到二次调研。
7. 下一步边界：先让领导/业务看历史档案和共享 Item 清单，再决定哪些记录激活为“待补二次调研”或“已刊登补观察数据”。不要把 1,053 条历史档案一次性变成当前流程任务。

最新开发前端热修 2026-07-26 15:48 Asia/Shanghai：商品详情开发询价、成本参数和价格参考现在会从 `snapshot.development_source` 兜底读取历史线下开发表字段。开发环境首页资源为 `/assets/index-BWzs-fE5.js`、`/assets/index-B-hcCA8P.css`；热修包 `.deploy_tmp/frontend-devsource-detail-fallback-20260726_1548.tar.gz` SHA-256 `D24BA293971B52D136709CF9353F6F5A3ACC7E6BCF9B72A3B14DB84AACEF02B3`；开发机备份 `/opt/hengzhe-new-product-dev/backups/frontend_devsource_detail_fallback_20260726_1548`。

## 历史数据源地图（给下一模型）

用户当前最大的痛点是“数据从哪里来、哪些字段为什么空、历史数据该怎么切进系统”没有被一次讲清楚。下一模型先按下面边界重新设计历史导入，不要继续在 UI 上零散补洞。

### 已知源文件和用途

| 数据源 | 已知路径 / 位置 | 主要用途 | 当前处理状态 | 下一步 |
|---|---|---|---|---|
| 三国历史新品表 | `E:\Project\Hengzhe-New-Product-Workflow\东南亚海外仓新品表-PH.xlsx`、`东南亚海外仓新品表-TH.xlsx`、`东南亚海外仓新品表-VN.xlsx` | 历史新品源数据、开发询价、供应商、成本、包装、价格参考、历史认领人线索 | 已用于回填 `snapshot.development_source`，开发库 1,053 条历史档案里 1,035 条匹配到唯一源；18 条因缺失或多候选未写 | 重新做字段字典，尤其把两行表头的字段名带到 UI，避免截图中“成本参数 AQ-BR 有值但字段名为空” |
| 财根团队新品开发表 | `E:\Project\Hengzhe-New-Product-Workflow\财根团队新品开发表.xlsx` | 财根侧历史新品、开品周期、采购核价类字段、补全开发源信息 | 已纳入 `development_source` 回填来源之一 | 和三国表统一成“历史开发表字段合同”，不要当 selection2 旧格式硬套 |
| 市场监控 / 二次调研历史表 | `E:\Project\Hengzhe-New-Product-Workflow\【市场监控】海外仓精品市场调研.xlsx` | 历史二次调研、竞品、成本、定价、关键词、类目、到货通知等来源证据；只处理 `货品` 以 `开发新品` 开头的行 | 已做只读清洗和历史归类；1053 条开发新品来源来自这里。当前商品详情“市场调研”仍可能为空，是因为 UI 只按旧 Z-AN 展示部分竞品/售价/月销列，没有把这张表的全量字段重新分模块设计 | 下一模型要重新梳理这张表的真实 sheet、两行表头、合并单元格和字段分组；市场调研详情不要只显示“源表 Z:AN”，要展示来源字段名和空值原因 |
| 市场监控补测试数据 | `E:\soft\dingding\【市场监控】海外仓精品市场调研--补测试数据.xlsx` | UAT 测试用二次调研数据 | 2026-07-24 已导入开发环境 233 条，source marker `uat_market_monitor_excel_seed` | 只作为测试批次，不代表最终历史导入口径 |
| 刊登监控历史表 | `E:\Project\Hengzhe-New-Product-Workflow\刊登监控7.25.xlsx` | 历史刊登操作、店铺、Item、优化动作、操作日期来源证据 | 已做只读清洗；旧表 4 周指标多数为空是正常缺口 | 旧表只证明“曾经人工记录过刊登/优化”，周指标必须由 FineBI 补，不用旧表空值推断 |
| PLM 到货 Excel | PLM 接口 `/api/hz-inventory/overseas/details/exportSummaryExcel`，历史下载范围已跑 `2026-04-01` 到 `2026-07-25` | 到货事实、当前销售员、主 SKU、子 SKU、国家/仓、最后一次入库时间、首次上架时间、库存/可发 | 已生成 `outputs/historical_data/plm_excel_history_20260725.json`；116 天、66,291 行、29,718 个唯一 `国家+子SKU` 键 | 到货和负责人只能以 PLM Excel 为准；open-detail 只能做快速候选，不参与最终裁决 |
| FineBI Item 财务原始表 | FineBI report `35d21769f7a14a6191cdc4f4a211a04a`，widget `ItemID财务数据八部`，payload `config/finebi_payloads/itemid_finance.json` | 店铺 + Item + 周期维度的刊登证据和周指标：订单量、总收入、一次毛利额、一次毛利率 | 已下载 17 周 `0402-0408` 至 `0723-0729`；解析已修正合并单元格显示值；共享 Item 口径已改为正常业务证据 | 下一模型必须从过滤前原始表取数，尊重合并单元格；同一店铺 + Item 多主 SKU 是“共享 Item 汇总”，不是冲突 |
| 运营分配配置类目表 | `E:\soft\dingding\海外仓新品主攻类目&未来想孵化类目收集--用于新品分配.xlsx` 第二个 sheet | 公司类目名称、一级/二级类目下拉选项、运营分配配置 | 已按用户确认改为可维护类目配置，不再把一级/二级写死为自由文本 | 下一模型改分配台时要保持配置高内聚，避免 UI、导入器、分配规则各自维护一套类目 |

### 当前截图里的问题要怎么理解

1. `开发询价 / 成本 / 价格参考` 不是完全没补。开发库里已有 `snapshot.development_source`，例如 MINA65A1 能读到供应商、成本、稳定价、促销价、预计单销。当前 UI 仍有“字段名为空”的情况，是因为历史源字段的显示标签没有完整从两行表头映射出来，只把值按列展示了。
2. `市场调研` 空不能简单判断为没数据。当前 UI 主要看旧的 Z-AN 竞品/售价/月销列；但历史市场监控表还有二次结论、定位、成本、定价、关键词、到货通知等字段。下一模型要重做“市场调研模块字段字典”，按真实表头分组展示，并标清“源表确实空”还是“系统暂未映射”。
3. `源表字段` 页面现在是兜底排查入口，不是给运营看的最终设计。它可以保留给审计，但商品详情的正式展示应该按业务模块：基础信息、开发询价、市场调研、价格/毛利、成本/备货、二次调研、刊登与观察、来源证据。

### 下一模型优先任务

1. 先做“历史字段合同”：把三国开发表、财根开发表、市场监控表、刊登监控表的 sheet、表头行、列范围、字段中文名、业务模块、是否可为空整理成一张机器可读字典。
2. 再改导入：历史档案 snapshot 同时保存原始列、字段中文名和业务模块，不只保存列号和值。
3. 再改详情 UI：字段名来自字典；空值展示要区分“源表空”“未匹配源表”“系统暂未映射”。
4. 最后才考虑激活流程：历史档案可查后，再从无争议的 `PLM 已到货 + 缺二次调研` 开始生成补录任务。不要一开始把 1,053 条历史记录都变成当前待办。

## Current Development Release: `cced0b9-post-uat-followup-20260724_220446`

Development at `http://139.224.2.166:18081` now runs `cced0b9-post-uat-followup-20260724_220446`. Production was not deployed, restarted or modified.

1. `二次调研`: renamed the editable link label to `锚定链接` while reusing `secondary_competitor_url`; added `secondary_target_daily_sales` and `secondary_selling_points`; removed editable research-time input; submission now auto-writes `secondary_research_at`; correction ignores direct time edits; export endpoint `GET /secondary-research/export` writes one Excel row per child SKU for the current filters.
2. `刊登任务`: listing creation no longer accepts a user-entered first-week start. The backend always starts from the next complete Thursday-to-Wednesday cycle; for example, a Friday 2026-07-24 listing starts 2026-07-30 through 2026-08-05. The frontend shows this as read-only.
3. `刊登与观察`: `新增刊登 Item` is visible on the main-SKU row instead of hidden in “更多”, and expanding the group shows a default add row. Product detail navigation now keeps the source scenario mounted so returning from detail lands back in `刊登任务` or `周期观察` correctly.

Changed backend schema migration `f2a3b4c5d678_add_secondary_research_target_and_selling_points.py` has been applied to development. Preserve existing autosave, submit, correction, permissions, audit, read-only metrics and lifecycle behavior.

Deployment facts: release package `/opt/hengzhe-new-product-dev/releases/cced0b9-post-uat-followup-20260724_220446.tar.gz`, SHA-256 `467392f83eff0bb493f03a99b9d79526ed6d2991a79b38e5fb81c4b8d7bb9c41`; pre-deploy development DB backup `/opt/hengzhe-new-product-dev/backups/release_cced0b9-post-uat-followup-20260724_220446/workflow_dev_before_cced0b9-post-uat-followup-20260724_220446.sql.gz`; previous app directory `/opt/hengzhe-new-product-dev/app.previous_cced0b9-post-uat-followup-20260724_220446`; current assets `/assets/index-VlH9KQkF.js`、`/assets/index-DF5n5mJr.css`; Alembic `f2a3b4c5d678 (head)`.

Verification: focused frontend tests `72/72`, full frontend `npm test` `148/148`, `npm run build`, `python -m compileall -q backend\app backend\alembic\versions`, and `git diff --check` passed. Deployment checks passed for public health, Liu login, secondary-research list/export, asset HEADs, container status and recent logs. Backend pytest was not run because this local Python environment lacks `pytest`.

## Previous Development Release: `cced0b9-role-switch-hotfix-20260724_1538`

Development previously ran role-switch hotfix `cced0b9-role-switch-hotfix-20260724_1538` on top of full release `cced0b9-later-uat-full-20260724_150554`. The business data and UAT period remain `后半段UAT-20260724`; this hotfix only corrects role capability and includes the current frontend toolbar layout.

Production read-only role truth: `刘学城=super_admin`; `练玉君=manager`. The fix keeps Liu's stored role as `super_admin`, lets that role pass operator-owned APIs as himself, and lets the frontend show both supervisor and operator entry tabs for `super_admin`. It does not create a fake operator role mapping and does not change production.

Deployment and backup facts:

- Release package kept on the development server: `/opt/hengzhe-new-product-dev/releases/cced0b9-role-switch-hotfix-20260724_1538.tar.gz`, SHA-256 `24a9e15edc607cec53c1d6adb45e2d780294e2cee43b5838d7f8549df9d9cdaa`.
- Pre-hotfix development DB backup: `/opt/hengzhe-new-product-dev/backups/release_cced0b9-role-switch-hotfix-20260724_1538/workflow_dev_before_cced0b9-role-switch-hotfix-20260724_1538.sql.gz` (`18742` bytes); `.env` backup: `/opt/hengzhe-new-product-dev/backups/release_cced0b9-role-switch-hotfix-20260724_1538/.env.before_cced0b9-role-switch-hotfix-20260724_1538`.
- Rollback app directories: `/opt/hengzhe-new-product-dev/app.previous_cced0b9-role-switch-hotfix-20260724_1538` and `/opt/hengzhe-new-product-dev/app.replaced_cced0b9-role-switch-hotfix-20260724_1538`.
- `api` and `frontend` were rebuilt and recreated. `reverse-proxy` was then recreated because Caddy still held the old frontend container IP after the frontend recreate and returned a transient `502` for `/`; health and page probes passed after the proxy restart. PostgreSQL, Redis, worker and scheduler stayed on the existing development volumes.
- Public health is `ok/development`; current assets are `/assets/index-VVsuyFe5.js` and `/assets/index-DBvoJwjS.css`.

Verification completed for this hotfix: `python -m py_compile backend\app\auth.py backend\tests\test_auth.py`; `node --test tests\stockingRequests.test.ts` passed `19/19`; full frontend `npm test` passed `146/146`; `VITE_API_BASE_URL=/api npm run build` passed; development probes for homepage, `/api/health`, assets, Liu login, Liu operator API, Liu manager API, Lian login and Lian manager API passed. Backend pytest was not run locally because this Python environment has no `pytest` module.

## Previous Full Development Release: `cced0b9-later-uat-full-20260724_150554`

Development at `http://139.224.2.166:18081` now runs the full tracked working-tree release `cced0b9-later-uat-full-20260724_150554`, SHA-256 `c4a5c315c6d118b1e6e34cc14fdfe4d2f66dd082c202ebda4981dacb86c25bdd`. It includes the previous UI hotpatch source changes inside a normal image build, so the hotpatch is no longer the current deployment boundary.

Deployment and backup facts:

- Release package kept on the development server: `/opt/hengzhe-new-product-dev/releases/cced0b9-later-uat-full-20260724_150554.tar.gz`.
- Pre-deploy development DB backup: `/opt/hengzhe-new-product-dev/backups/release_cced0b9-later-uat-full-20260724_150554/workflow_dev_before_cced0b9-later-uat-full-20260724_150554.sql.gz` (`440685` bytes). Use this file to restore the old development business data if needed.
- `.env` backup: `/opt/hengzhe-new-product-dev/backups/release_cced0b9-later-uat-full-20260724_150554/.env.before_cced0b9-later-uat-full-20260724_150554`; previous app directory: `/opt/hengzhe-new-product-dev/app.previous_cced0b9-later-uat-full-20260724_150554`.
- `api/worker/scheduler/frontend` were rebuilt and recreated; PostgreSQL, Redis and reverse-proxy stayed on the existing development volumes and checked services have `RestartCount=0`.
- Public health was `ok/development`; assets at that full-release deployment were `/assets/index-BylKSV6W.js` and `/assets/index-DBvoJwjS.css`; public JS contained no `localhost:8000` or `127.0.0.1:8000` API base.

Development data was reset for later-stage UAT after deployment. Old business test data was cleared; accounts, role mappings and operator assignment profiles were rebuilt from a read-only production export without copying production password hashes. Passwords are reset to the documented default `姓名拼音首字母 + 123456`. Current counts after reset: 23 users, 23 role mappings, 16 operator profiles, 13 opportunities, 14 claims, 3 stocking requests, 1 export row, 1 PLM item, 7 listing records and 29 observation periods. The business period is `后半段UAT-20260724`.

Login notes for verification: production read-only role check confirms `刘学城=super_admin` and `练玉君=manager`. 刘学城 must be able to switch between supervisor and operator views as a super administrator; 陈丽妹 remains a normal operator-account example.

Verification completed after data reset: public health, 刘学城 and 陈丽妹 login, secondary-research pending/submitted APIs, listing workbench all/pending-listing APIs, stocking export-periods and available-list APIs, product-board API, asset HEAD checks, server environment gates, Alembic head, recent API/frontend/scheduler/worker logs and restart counts.
## Previous Development Frontend Hotpatch: `dev-frontend-hotpatch-filters-20260724_1446`

After `cced0b9-listing-add-metrics-20260724_133848`, a frontend-only follow-up requested on 2026-07-24 was hotpatched to the development frontend container. It removes the separate secondary-research source/basic-info block, moves category, keyword and per-child open reasons into the main-SKU drawer header, keeps source data in the module tabs, embeds the editable secondary-research matrix below `市场调研`, tightens the source matrix cells, and moves observation advanced filters into the top filter row instead of an expandable second block.

The listing-observation menu label `新增周期` is now `延长观察`. The behavior is unchanged: it manually creates week 5 and later observation periods after first-round completion, and does not add a new Item. New Item creation remains `新增刊登 Item`.

Local verification for this hotpatch: focused listing/observation frontend tests `56/56`, full frontend `npm test` `146/146`, `npm run build`, and `git diff --check` passed before deployment. The hotpatch package was `.codex_tmp/dev-frontend-hotpatch-filters-20260724_1446.tar.gz`, SHA-256 `b3fd70f57de1a8dbafed51bdb34dd414369b2f722b24ca00243150d9b2bbc726`; remote backup is `/opt/hengzhe-new-product-dev/backups/release_dev-frontend-hotpatch-filters-20260724_1446/frontend_html_before`. It copied new `frontend/dist` files into the running development frontend nginx container without rebuilding images or recreating containers. Public health is `ok/development`; assets at that hotpatch were `/assets/index-BylKSV6W.js` and `/assets/index-DBvoJwjS.css`; public JS contains neither `localhost:8000` nor the old observation `高级筛选` / `advancedOpen` toggle; at-that-time Liu Xuecheng default-password login was verified without logging a token; current role parity is documented in the current release section above.

## Previous Development Release: Listing Additions And Folded Metrics

Development base release `cced0b9-listing-add-metrics-20260724_133848` previously ran at `http://139.224.2.166:18081`. It built on `cced0b9-observation-status-strip-20260724_122300`; its then-current frontend files were overlaid by hotpatch `dev-frontend-hotpatch-filters-20260724_1446`. Production was not connected, deployed, restarted or modified.

Implemented and deployed:

1. `刊登任务`: added a top-level `新增主 SKU 刊登` dialog for a completely new main SKU. It captures main SKU, product name, country/site, owner, shop, Item, listing strategy and first-week start, then reuses the existing listing batch creation path.
2. `刊登任务` and `周期观察`: main-SKU row `更多 -> 新增刊登 Item` expands the existing draft table under that main SKU. Existing same-Item continuation still uses `恢复跟踪`; new Item creation keeps the global Item uniqueness check.
3. `周期观察`: folded main-SKU rows show up to three Item status chips with the current state plus the latest fetched metrics week. If the current week is still observing and has no metrics, the chip falls back to the previous fetched week; expanded rows remain the full period history.
4. Backend `manual_context` support creates manual listing records with `source_type=manual_listing`, empty claim source, four initial observation periods and the existing `listing.created` audit. It does not backfill or forge secondary-research, stocking or source-claim history.

Verification: focused frontend tests `56/56`, full frontend `npm test` `146/146`, `npm run build`, Python compile for the touched backend files and backend test file, and deployment health checks passed. Backend pytest was not run because this local Python environment has no `pytest` module. Development deployment rebuilt `api/worker/scheduler/frontend`; Redis and reverse-proxy container IDs stayed unchanged. PostgreSQL was recreated by the Compose migration check but kept the existing development volume; `pg_isready`, Alembic `e1f2a3b4c678 (head)`, public health, asset HEAD checks and API/frontend recent logs are clean.

## Previous Development Deployment: Observation Status Strip

The previous development release was `cced0b9-observation-status-strip-20260724_122300`. It kept the user-approved secondary-research detail redesign from the previous release and added collapsed-row observation status chips. The authoritative rules remain `docs/2026-07-09-已确认需求记录.md` lines 126-132 and 178-184.

Completed frontend changes:

1. `刊登与观察 -> 周期观察`: the collapsed main-SKU row now shows compact Item status chips so operators can see `尚未开始`, current week, pending review, stopped and voided states without expanding. Expanded period rows still keep week/date/status, four read-only metrics, product positioning, optimization action and row actions on one compact row.
2. `二次调研`: the main filling area now groups by main SKU. Clicking the main SKU or child SKU name opens a right-side main-SKU drawer; the main SKU uses the first child-SKU image. The list keeps one row per child SKU with `AN 调研结论`, `AO 商品定位`, `AM 竞品链接`, `AL 调研时间`, research images and save state inline. Source information, claim history and other-operator records moved into the drawer. The drawer is module-based like operator claim and starts with `市场调研`, then includes the editable secondary-research matrix and source modules. Editing the first row syncs research time, competitor link, conclusion and positioning to rows that have not been directly edited.
3. `运营认领`: the business-period and operation-status filters stay in the same desktop toolbar row as search and pagination controls at 1366 px.

Preserved behavior: autosave, submission, correction, permission checks, audit logging, metric read-only display and lifecycle transitions. No backend APIs, database schema or business data were changed.

Changed file scope:

- `frontend/src/App.tsx`
- `frontend/src/ListingObservationView.tsx`
- `frontend/src/SecondaryResearchView.tsx`
- `frontend/src/listingObservation.ts`
- `frontend/src/styles.css`
- `frontend/src/listingDensity.css`
- `frontend/tests/listingObservation.test.ts`
- `frontend/tests/listingDensity.test.ts`
- `frontend/tests/imageUploads.test.ts`
- `frontend/tests/secondaryResearchDrafts.test.ts`

Review and verification completed: GPT-5.5 xhigh review reported no Critical, Important or Minor findings for the observation status-strip change; no GPT-5.6 was used. Listing/observation focused tests passed `54/54`; full frontend `npm test` passed `144/144`; `npm run build` and `git diff --check` passed. Development deployment rebuilt only `frontend`; public health was `ok/development`; assets were `/assets/index-DluiVTn3.js` and `/assets/index-CJ7-2muA.css`. API/frontend/reverse-proxy logs since deployment had no matched error/exception lines. Browser automation was not run because this Codex machine has no Playwright/system browser binary. Production was not connected or modified.

## Environment Boundary

| Environment | Address | Current code | Rule |
|---|---|---|---|
| Production | `http://101.132.26.138:8080` | `b373d65` | In use. Do not connect, deploy or restart without a separately approved non-working-time release window. |
| Development | `http://139.224.2.166:18081` | `cced0b9-post-uat-followup-20260724_220446` | Later-stage UAT build plus post-UAT secondary-research/listing follow-up is available for business verification. SSH alias: `hz-new-product-dev`. |

Production database is `workflow_prod_20260715`; development database is `workflow_dev_20260715`. Databases, Redis, uploads, volumes, ports and environment variables are isolated. Never commit passwords, tokens, cookies, private keys or `.env` files.

PLM arrival endpoint settings and credentials are stored separately in both server `.env` files. `PLM_SYNC_ENABLED` remains `false` in both environments; do not enable it or restart production without explicit approval.

`caigen-arrival-notifier` remains the only production arrival-card sender on `101.132.26.138`. The one explicit development exception is the isolated historical watchlist pilot described below: it can send only to 刘学城, keeps all global switches false and never writes workflow tables. Development does not receive a feed from the production notifier. The template is selected through `DINGTALK_ARRIVAL_CARD_TEMPLATE_ID`; never commit the environment value.

## Previous Development Deployment: `cced0b9-listing-add-metrics-20260724_133848`

This previous release ran only at `http://139.224.2.166:18081` from a local working-tree package after `cced0b9`; it has been superseded by `cced0b9-later-uat-full-20260724_150554`.

- Release package: `/opt/hengzhe-new-product-dev/releases/cced0b9-listing-add-metrics-20260724_133848.tar.gz`, SHA-256 `97ed02a3052d5d7ef48a0a739cf01bd748afbd8979d2a983dbbd64c619152526`; generated from tracked working-tree files and checked to exclude `.env`, `node_modules`, `dist`, `.codex_tmp` and local database files.
- Pre-release backup directory: `/opt/hengzhe-new-product-dev/backups/release_cced0b9-listing-add-metrics-20260724_133848`; previous application directory: `/opt/hengzhe-new-product-dev/app.previous_cced0b9-listing-add-metrics-20260724_133848`.
- Database backup: `/opt/hengzhe-new-product-dev/backups/release_cced0b9-listing-add-metrics-20260724_133848/workflow_dev_before_cced0b9-listing-add-metrics-20260724_133848.sql.gz` (`440070` bytes); `.env` backup: `/opt/hengzhe-new-product-dev/backups/release_cced0b9-listing-add-metrics-20260724_133848/.env.before_cced0b9-listing-add-metrics-20260724_133848` with mode `600`.
- `api/worker/scheduler/frontend` were rebuilt and recreated. Redis and reverse-proxy container IDs stayed unchanged. PostgreSQL was recreated by the Compose migration check, kept the existing development volume, is accepting connections, and all checked active services have `RestartCount=0`.
- Public health returned `ok/development`; base release assets were `/assets/index-N4Wy7wol.js` and `/assets/index-D1eDxDoK.css`, both returning `200` through the public `18081` path. Current public frontend assets are listed in the hotpatch section above.
- Post-deploy server checks found no matched `traceback|exception|critical|error` lines in API/frontend logs since deployment. The raw reverse-proxy log copy created during deployment was removed because it contained SSE token query strings.
- `APP_ENV=development`, `HTTP_PORT=18081`, `PLM_SYNC_ENABLED=false`, `WORKFLOW_AUTOMATION_ENABLED=false` and `DINGTALK_CARD_AUTOSEND_ENABLED=false` stayed unchanged.
- Production was not connected, deployed, restarted or modified.

## Verified Baseline

- Deployed development release: `cced0b9-post-uat-followup-20260724_220446`, built from the tracked local working tree on `lxc/uat-usability-fixes`; full release `cced0b9-later-uat-full-20260724_150554` remains the data-reset base underneath it.
- Backend baseline remains `370 passed` from `29e3a06`. Current deployed release verification passed Python compile for touched backend files and backend test file, focused listing/observation frontend tests `56/56`, full frontend `npm test` `146/146`, `VITE_API_BASE_URL=/api npm run build`, and `git diff --check`. The post-UAT follow-up passed focused frontend tests `72/72`, full frontend `npm test` `148/148`, `npm run build`, Python compile for `backend/app` and Alembic versions, `git diff --check`, and development deployment checks. The initial sandbox `node --test` run hit Windows `spawn EPERM`, then passed outside the sandbox; backend pytest is not available locally.
- Alembic: source and `workflow_dev_20260715` are at `f2a3b4c5d678 (head)`.
- Development health is `ok/development` inside the server and through the public `18081` path. Current assets are `/assets/index-VlH9KQkF.js`、`/assets/index-DF5n5mJr.css`; public JS contains the `super_admin -> manager + operator` frontend mapping and no local API base.
- Development data was reset to `后半段UAT-20260724`: old business test records were cleared, production account/role/operator-profile config was imported read-only, passwords were reset to `姓名拼音首字母 + 123456`, and UAT coverage data now spans secondary research, stocking/export, listing tasks and observation periods. On 2026-07-24 16:10 Asia/Shanghai, extra UAT source marker `uat_extra_sku_seed` / `UAT-EXTRA-SKU-20260724` appended 60 opportunities, 60 claims, 5 listing records and 20 observation periods for 陈丽妹、赵钰婷、李干、庞莹莹、冯卓宏; dev backup `/opt/hengzhe-new-product-dev/backups/dev_before_extra_sku_seed_20260724_161046.sql.gz` was created before the write.
- Production read-only role check confirms `刘学城=super_admin` and `练玉君=manager`; 刘学城 can switch between supervisor and operator views as super administrator, while 陈丽妹 remains a normal operator-account example.

## Implemented Scope

Front stage:

- Import the two approved internal feedback workbooks with source file/sheet/row/snapshot traceability.
- Supervisor assignment by main-SKU group, operator claim/not-claim, supervisor review and audit history.
- Formal stocking export is a one-time selected-request transition to `waiting_arrival`; central traceability export remains repeatable by business period with independent batches and no workflow-state rollback.
- Product board, opportunity pool, assignment filters, operator configuration and pricing/percentage display rules.

Later stage:

- Secondary research with five positions: 引流款、利润款、淘汰款、稳定款、清仓款.
- Each site represents one country. Country/site filters use the existing structured site field, while shop name is only an auxiliary filter.
- 引流款、利润款、稳定款 enter listing; 淘汰款 and 清仓款 skip listing; only entering 淘汰款 creates the daily supervisor reminder event.
- One main SKU can have multiple manually entered shop + globally unique Item listing records.
- Each Item selects its own first Thursday-to-Wednesday period and observes four independent weeks; later periods are manually added.
- Weekly metrics are read-only; product positioning and optimization action are required; week 4 also requires a summary.
- Completed reviews are read-only by default and become editable only after the operator clicks `纠错`; stopped Items may finish already-fetched periods, while only explicit stop pauses future fetches and reminders.
- Product detail is the read-only lifecycle archive: secondary-research history and listing/observation history have separate entries, with listing records grouped by source business period.
- Secondary research preserves both pending and submitted records, scopes the latest business period to the active scenario / country / owner filters, and keeps all filters visible even when the result is empty. The deployed detail redesign uses one row per child SKU, with competitor link, research time, images and save state inline; source data, claim history and other-operator records open in a right-side main-SKU module drawer. The drawer also contains the editable secondary-research matrix and first-row values default-sync to untouched child rows.
- The listing workbench separates `刊登任务` and `周期观察`, defaults to observation with visible counts, keeps main-SKU and Item rows compact/collapsible, and shows only visible periods in its progress summary. SKU links and thumbnails open the existing product detail; future test periods no longer make the header claim that first-round observation is complete. The deployed compact redesign places period metrics, positioning, optimization and actions in one row and surfaces current-week / stopped / voided Item status.
- Stocking requests are collapsed by default and only one request expands at a time. Operator configuration still assigns one site per operator, but site choices come from existing assignment/profile data and display known labels such as `泰国（TH）`.

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
- Produce a read-only reconciliation report for the two historical workbooks before any importer: their live A:AR layout conflicts with the documented A:AO contract, 39 within-file duplicate-key groups contain field conflicts, one row is exactly duplicated across files, and 420 formula cells contain errors. After reconciliation, only accepted historical claims, submitted secondary research, listings and observation metrics may enter as source-traceable read-only archive records; they must not replay completed states as current tasks. Do not use last-row-wins or overwrite non-empty platform values.
- Include the DingTalk `精品流程` historical listing rows in that report as a separate candidate source. Match only after country and salesperson alignment, keep the one observed responsibility conflict and three missing groups explicit, and never infer child-SKU, arrival or weekly metrics from this sheet.
- Review the 202 unique FineBI candidates before any controlled prefill; keep the 364 multiple candidates manual and ignore the 1,671 unmatched for now. Old claimants remain provenance while the current PLM salesperson is authoritative for arrival notification and exact linkage.
- No provided asset implements real-time `child SKU -> shop + Item` discovery. FineBI raw rows include `ITEMID + 主SKU + 店铺 + 审核时间` and therefore provide delayed historical candidates after financial activity, but contain no child SKU and do not prove real-time listing. PLM and the ERP product-list wrapper also do not return shop/Item; unmatched records remain operator-entered.
- Use one historical PLM arrival hit to create exactly one traceable secondary-research task in development, preserving source-row evidence and the PLM salesperson. 刘学城 is the acting UAT user; do not replay completed workflow states from the old workbooks.
- Development does not currently provide all five ERP settings (`ERP_LOGIN_URL`, `ERP_PRODUCT_LIST_URL`, `ERP_DOWNLOAD_LIST_URL`, `ERP_USERNAME`, `ERP_PASSWORD`); the referenced asset document contains no uniquely locatable credentials. Real ERP volume lookup remains unaccepted until values are supplied through development `.env` only. The deployed fallback is manual dimensions with automatic volume calculation.
- The weekly Item source was already delivered in `E:\Project\hermes\group8_item_week_package_20260715.zip` and exists in Hermes: FineBI report `35d21769f7a14a6191cdc4f4a211a04a`, widget `ItemID财务数据八部`, payload `config/finebi_payloads/itemid_finance.json`. Historical-candidate parsing is implemented; the remaining work is aggregating tracked `Item + shop + period` metrics into `apply_week_metrics(...)`, with snapshots, scheduling and retries. Do not consume the filtered finished sheet.
- Real scheduling, retry monitoring and operator message delivery for weekly Item metrics remain unconnected.
- Production release of the unified branch is not approved.

## Next Session Checklist

1. Use `http://139.224.2.166:18081` for business verification of current frontend hotpatch `dev-frontend-hotpatch-market-monitor-20260724_1803`, role hotfix `cced0b9-role-switch-hotfix-20260724_1538`, and reset period `后半段UAT-20260724`. Do not deploy, restart or modify production.
2. Inspect `git status` before any follow-up edit because local docs now include the deployment record.
3. After the UI pass is accepted, resume the historical-PLM single-task UAT and old-Item weekly-metrics UAT in `docs/20-项目推进总控.md`.
4. Use GPT-5.5 only for any follow-up code review; do not call GPT-5.6 / Sol.
5. Update only the active document set when implementation or deployment state changes; keep `docs/archive/` read-only and run `neat-freak` at milestones.


Hotfix note 2026-07-24 16:20 Asia/Shanghai: development API container was single-file hotpatched for secondary-research owner scope. Super administrators/managers now use the selected `salesperson_name` when saving drafts or submitting a secondary-research group; normal operators remain locked to their own operator identity. Runtime file and host app file were updated at `/opt/hengzhe-new-product-dev/app/backend/app/routers/secondary_research.py`; backup is `/opt/hengzhe-new-product-dev/backups/hotfix_secondary_owner_20260724_1620/secondary_research.py.before`. Verification: 刘学城 switched to 江琴 and PATCHed `UAT-SELF-PH-PLM` with HTTP 200.


Data note 2026-07-24 16:29 Asia/Shanghai: development UAT data marker `uat_lwh_extra_seed` / `UAT-LWH-SKU-20260724` appended 10 main SKUs for 陆伟豪, with 30 opportunities/claims, 4 listing records and 16 observation periods. Backup before write: `/opt/hengzhe-new-product-dev/backups/dev_before_lwh_seed_20260724_162908.sql.gz`. Verification: 陆伟豪 / default password logged in, secondary-research API returned 4 groups, listing-workbench returned 4 listing records and 16 period rows.


Data note 2026-07-25 12:51 Asia/Shanghai: historical-data intake received a minimal read-only source audit helper `backend/app/historical_data_audit.py` and selection1 import now resolves main fields by header aliases, including Caigen extended workbooks with a leading `开品周期` column. This only adds reporting/import compatibility; it does not run PLM/FineBI downloads, mutate development data, or write production.

Data note 2026-07-24 17:06 Asia/Shanghai: development imported cleaned market-monitor workbook `E:\soft\dingding\【市场监控】海外仓精品市场调研--补测试数据.xlsx` as source marker `uat_market_monitor_excel_seed`. Cleaning kept 233 unique `国家+销售员+主SKU+子SKU` rows from 257 raw rows, skipped 24 duplicates, preserved A:AR snapshots, and created 233 opportunities, 233 secondary-research claims and 692 market-research competitor rows under business period `后半段UAT-20260724`. Backup before write: `/opt/hengzhe-new-product-dev/backups/dev_before_market_monitor_excel_seed_20260724_170620.sql.gz`. Verification: 陆伟豪/赵钰婷/江琴 logins returned secondary-research API 200 with imported groups visible.


Data/hotpatch note 2026-07-24 17:58 Asia/Shanghai: development frontend-only hotpatch `dev-frontend-hotpatch-market-monitor-20260724_1803` is live at `http://139.224.2.166:18081` with assets `/assets/index-D3COogHI.js` and `/assets/index-DBvoJwjS.css`. It fixes market-monitor snapshot header matching for string `headers_by_column` and maps competitor fields from real R/S/T, U/V/W and X/Y/Z columns. Development data source `uat_market_monitor_excel_seed` was status-patched after backup `/opt/hengzhe-new-product-dev/backups/dev_before_market_monitor_status_history_20260724_175027.sql.gz`: 233 opportunities remain `waiting_secondary_research`, 233 claims have `source_column=platform`, claim states read back as 226 `waiting_secondary_research`, 6 `listing_observation` and 1 user-progressed `waiting_listing`. Historical Item files `E:\soft\dingding\业务数据需求 20260715\海外仓item数据分析_0709-0715.xlsx` and `E:\soft\dingding\海外仓item异常分析_0716-0722\海外仓item数据分析_0716-0722.xlsx` matched 8 Items and filled 32 observation periods; ZG041 did not match historical Item rows and stays waiting secondary research. Verification: `VITE_API_BASE_URL=/api npm run build`, frontend `npm test` 146/146, `git diff --check`, public health and API-container read-back all passed. Production was not changed.


Data note 2026-07-25 13:35 Asia/Shanghai: generated `outputs/import_templates/选品1选品2标准导入模板-20260725.xlsx` for standard 选品1/选品2 import handoff. Historical intake outputs were also generated under `outputs/historical_data/`: watchlist `historical-watchlist-20260725.json` (2,237 keys), FineBI raw candidate report `finebi-item-candidates-raw-local-plus-hermes-20260725.json` (443 matched keys; 218 unique / 225 multiple from available raw weeks), and PLM open-detail candidate report `plm_open_watchlist_matches_20260725.json` after caching 2026-04-01 through 2026-07-25 on development (`116` days, `0` failures, `1,509` matched rows / `861` unique keys). PLM open-detail has no salesperson field, so it is only an arrival-candidate filter; run PLM Excel exports for matched dates before any owner-accurate write. No production deployment or business-table mutation was performed.

Data note 2026-07-25 13:55 Asia/Shanghai: checked the existing arrival-notifier project `E:\Project\caigen_arrval` and confirmed its production flow uses PLM Excel export `/api/hz-inventory/overseas/details/exportSummaryExcel`, not the open-detail JSON endpoint, to obtain `销售员`, `主SKU`, `子SKU`, `首次上架时间` and `最后一次入库时间`. The workflow platform already has the matching `download_plm_export(...)` path; keep open-detail only as a fast historical candidate filter, then补跑 Excel export for matched dates before owner-accurate import or secondary-research task creation.

Data note 2026-07-25 18:45 Asia/Shanghai: implemented read-only historical monitoring audit `backend/app/historical_monitoring_sources.py` with tests `backend/tests/test_historical_monitoring_sources.py`. It parses `E:\Project\Hengzhe-New-Product-Workflow\【市场监控】海外仓精品市场调研.xlsx` and `E:\Project\Hengzhe-New-Product-Workflow\刊登监控7.25.xlsx`, filtering only `货品` values starting with `开发新品` for this new-product workflow. Outputs: `outputs/historical_data/historical-monitoring-sources-audit-20260725.json` and `outputs/historical_data/历史新品二次调研与刊登监控清洗报告-20260725.md`. Summary: market monitor 1505 raw rows / 1053 development-new rows / 452 excluded non-new-product rows; missing secondary conclusion 837, positioning 979, target daily sales and selling points 1053 each; listing monitor 666 raw rows / 420 development-main-SKU matches / 3 invalid Item rows / 79 rows currently FineBI-fillable. This is report-only: no database writes, no task creation, no status advancement, no notifications, and no production access.

Data note 2026-07-25 19:10 Asia/Shanghai: implemented read-only historical status classification `backend/app/historical_status_classification.py` with tests `backend/tests/test_historical_status_classification.py`. It combines the historical monitoring audit, PLM open-detail candidate matches and FineBI Item candidates without writing business tables. Outputs: `outputs/historical_data/historical-status-classification-20260725.json` and `outputs/historical_data/历史到货二次调研刊登状态归类报告-20260725.md`. Summary over 1053 development-new rows: 到货监控中 198, 未到货但疑似已刊登 188, 已到货待补二次调研 214, 已刊登但二次调研缺失 453; conflicts 494; FineBI-fillable observation candidates 287. No deployment, DB writes, task creation, status advancement, notifications or production access.

Data note 2026-07-25 21:41 Asia/Shanghai: implemented historical archive dry-run/import scaffold `backend/app/historical_archive_import.py` with tests `backend/tests/test_historical_archive_import.py`, and extended `historical_status_classification` output to preserve secondary research source fields. The script defaults to dry-run, writes review outputs only, and requires explicit `--apply-dev` for DB writes. Even in apply mode it only creates `NewProductOpportunity` records with `source_type=historical_market_monitor_archive`, `current_status=historical_archive`, plus `SourceRecordSnapshot`; it does not create FlowTask, claim, stocking, secondary-research, listing or observation records. Real dry-run output: `outputs/historical_data/historical_archive_import_20260725/historical-archive-import-summary-20260725.json`, `历史档案导入冲突清单-20260725.xlsx`, `历史二次调研待补清单-20260725.xlsx`; 1053 rows, 494 conflicts, 667 pending-secondary candidates. No development DB apply, deployment, production access, notification or workflow status advancement was performed.

Data note 2026-07-25 22:20 Asia/Shanghai: completed direct local historical PLM Excel and FineBI Item downloads for the history cut-in report. PLM Excel used `exportSummaryExcel` with `latestStorageTimeStart/End` per Beijing day, `blocNameList=[集团八部]`, empty SKU filters, `queryType=1`, `bindType=1`, `mergeSaleName=0`, `hideZeroData=0`; 2026-04-01 through 2026-07-25 produced 116 workbooks, 0 failed dates, 66,291 parsed rows and 29,718 unique `国家+子SKU` keys in `outputs/historical_data/plm_excel_history_20260725.json`. FineBI used report `35d21769f7a14a6191cdc4f4a211a04a`, widget `ItemID财务数据八部`, payload `config/finebi_payloads/itemid_finance.json` with `集团=集团八部`; 17 weekly periods `0402-0408` through `0723-0729` downloaded successfully to `outputs/historical_data/finebi_live/`, 0 failures. Reconciled FineBI candidates output `outputs/historical_data/finebi-item-candidates-raw-0402-0729-20260725.json`: 69,232 candidates, 606 matched watchlist keys, 225 unique, 381 multiple, 1,631 unmatched. Re-ran status classification with PLM Excel and FineBI: `outputs/historical_data/historical-status-classification-plm-excel-finebi-20260725.json` and Markdown report; 1,053 records now classify as 138 到货监控中, 221 已到货待补二次调研, 655 已刊登但二次调研缺失, 39 未到货但疑似已刊登, with 316 conflict rows and 362 FineBI-fillable candidates. Dry-run archive outputs are under `outputs/historical_data/historical_archive_import_plm_excel_finebi_20260725/`; no development DB apply, deployment, production access, notification or workflow status advancement was performed.


Data note 2026-07-25 23:39 Asia/Shanghai: corrected the historical archive report wording so `has_listing_item` is presented as `是否有刊登证据`, with separate evidence status, confirmed shop/Item, candidate count and candidate list. PLM-vs-historical salesperson differences now stay as source fields and no longer count as hard conflicts. Re-ran PLM-Excel/FineBI classification and archive dry-run: 1,053 rows, status counts unchanged (138 到货监控中, 221 已到货待补二次调研, 655 已刊登但二次调研缺失, 39 未到货但疑似已刊登), hard conflicts reduced to 45 true `FineBI同一店铺Item对应多个主SKU` rows, 104 multi-Item candidates, 274 missing-FineBI-evidence rows and 362 FineBI-fillable candidates. Added `outputs/historical_data/historical_archive_import_plm_excel_finebi_20260725/历史FineBI同店铺Item多主SKU明细-20260725.xlsx` for the concrete shop+Item owner details. Applied a development-only sample import of 12 historical archive records (3 per status) to `http://139.224.2.166:18081`, import batch `8391a67e-a4c7-48f5-9f08-321c1bb29db5`; read-back confirmed 12 opportunities, 12 source snapshots, and 0 flow instances / tasks / claims. No production access, deployment, restart, notification or workflow activation was performed.

Data note 2026-07-26 Asia/Shanghai: corrected FineBI `ItemID财务数据八部` parsing to respect Excel merged-cell display values for key columns (`ITEMID`, `主SKU`, `店铺`, `审核时间`). The 2026-07-23 to 2026-07-29 raw workbook shows merged ranges such as rows 48-50 where blank raw cells inherit displayed ITEMID/main SKU/shop/audit time; previous conflict and blank-identifier workbooks generated before this correction must be treated as preliminary and regenerated before business review.

Data note 2026-07-26 Asia/Shanghai: regenerated FineBI candidate reconciliation and historical archive dry-run with the merged-cell-aware parser. New files: `outputs/historical_data/finebi-item-candidates-raw-0402-0729-merged-aware-20260726.json`, `outputs/historical_data/historical-status-classification-plm-excel-finebi-merged-aware-20260726.json`, `outputs/historical_data/历史到货二次调研刊登状态归类报告-PLMExcel-FineBI-合并单元格修正版-20260726.md`, and review workbooks under `outputs/historical_data/historical_archive_import_plm_excel_finebi_merged_aware_20260726/`. Summary remains 1,053 records with status counts unchanged: 138 到货监控中, 221 已到货待补二次调研, 655 已刊登但二次调研缺失, 39 未到货但疑似已刊登. Merged-cell-aware dry-run counts: 65 hard conflict rows, 98 multi-Item candidate rows, 269 missing-FineBI-evidence rows, 876 PLM-arrived rows, 362 FineBI-fillable rows. Do not use the pre-fix 20260725 FineBI conflict workbooks for business review.

Data note 2026-07-26 13:35 Asia/Shanghai: adjusted historical archive policy so FineBI `同一店铺 + Item` mapped to multiple main SKUs is `shared_item_binding`, not a hard conflict. Re-ran merged-aware classification and archive dry-run: 1,053 rows, status counts unchanged (138 到货监控中, 221 已到货待补二次调研, 655 已刊登但二次调研缺失, 39 未到货但疑似已刊登), hard conflicts 0, shared Item binding 65, multi-Item candidates 98, missing-FineBI-evidence 269, PLM-arrived 876, FineBI-fillable 362, skipped / 未导入 0. New local outputs: `outputs/historical_data/historical-status-classification-plm-excel-finebi-shared-item-20260726.json`, `outputs/historical_data/历史到货二次调研刊登状态归类报告-共享Item修正版-20260726.md`, and `outputs/historical_data/historical_archive_import_shared_item_20260726/`. Applied full development-only historical archive import to `http://139.224.2.166:18081`, import batch `0fdad0de-4219-4056-ac22-b8e68070d356`: created 1,041 records, updated the previous 12 sample records, skipped 0. Backup before write: `/opt/hengzhe-new-product-dev/backups/dev_before_historical_archive_shared_item_20260726_133146.sql.gz`; remote review outputs copied to `/opt/hengzhe-new-product-dev/outputs/historical_archive_import_shared_item_20260726/`. Read-back confirmed `historical_market_monitor_archive` opportunities 1,053 and source snapshots 1,053; flow instances 0 and flow tasks 0; sales claims 338, stocking requests 4, listing records 25 and observation periods 101 unchanged from before the import. No production access, deployment, restart, notification or workflow activation was performed.

Data note 2026-07-26 13:59 Asia/Shanghai: backfilled historical archive development-source fields from `东南亚海外仓新品表-PH.xlsx`, `东南亚海外仓新品表-TH.xlsx`, `东南亚海外仓新品表-VN.xlsx` and `财根团队新品开发表.xlsx`. The source parser reads the two-row grouped headers and preserves `开发询价`, supplier/cost/package fields, competitor links and price/reference-sales snapshots under `snapshot.development_source`; it does not change workflow state. Local review matched 1,053 historical archive rows: 1,035 unique matches, 6 multiple-candidate rows and 12 missing rows. Applied only to development `workflow_dev_20260715`: updated 1,035 historical archive snapshots and skipped 18 uncertain rows. Backup before write: `/opt/hengzhe-new-product-dev/backups/dev_before_development_source_backfill_20260726_135559.sql.gz`; remote review outputs are under `/opt/hengzhe-new-product-dev/outputs/historical_development_source_backfill_20260726/`. Read-back confirmed historical archive opportunities 1,053, snapshots 1,053 and `development_source` rows 1,035; flow tasks stayed 0 and claims/stocking/listing/observation stayed 338/4/25/101. Production was not connected, deployed, restarted or modified.

Data note 2026-07-26 15:25 Asia/Shanghai: implemented the leadership-confirmed shared Item summary policy for historical archives. FineBI `店铺 + Item + 周期` is now treated as the metrics fact dimension; `同一店铺 + Item` mapped to multiple main/sub SKUs is labeled `共享Item汇总`, not a conflict. Local dry-run output `outputs/historical_data/historical_archive_import_shared_item_summary_20260726/` stayed at 1,053 rows, hard conflicts 0, skipped / 未导入 0, shared Item binding 65, multi-Item candidates 98, missing-FineBI-evidence 269, PLM-arrived 876 and FineBI-fillable 362. Applied development-only snapshot correction to `workflow_dev_20260715`: final import batch `d0b5e995-2b2d-47cf-a7d1-bb5c1ec836ab` updated 1,053 historical archive snapshots, created 0 and skipped 0; backup before write: `/opt/hengzhe-new-product-dev/backups/dev_before_shared_item_summary_snapshot_20260726_152514.sql.gz`; remote outputs copied to `/opt/hengzhe-new-product-dev/outputs/historical_archive_import_shared_item_summary_20260726/`. Read-back confirmed historical opportunities 1,053, historical source snapshots 1,053, `development_source` still 1,035, item-summary snapshots 694 and shared Item snapshots 65; flow instances/tasks stayed 0/0 and claims/stocking/listing/observation stayed 338/4/25/101. Production was not connected, deployed, restarted or modified.

Data/frontend note 2026-07-26 15:48 Asia/Shanghai: fixed historical product detail display so 开发询价、成本参数 and 价格参考 fall back to `snapshot.development_source.development_inquiry` and `snapshot.development_source.pricing_snapshot` when normal source columns are absent. This explains the previous MINA65A1 blank UI: development data existed in the archive snapshot but the frontend only read `fields_by_column/cells`. Development frontend hotpatch is live at `http://139.224.2.166:18081` with assets `/assets/index-BWzs-fE5.js` and `/assets/index-B-hcCA8P.css`; backup `/opt/hengzhe-new-product-dev/backups/frontend_devsource_detail_fallback_20260726_1548`; package SHA-256 `D24BA293971B52D136709CF9353F6F5A3ACC7E6BCF9B72A3B14DB84AACEF02B3`. Read-back for MINA65A1 confirmed source file `东南亚海外仓新品表-PH.xlsx` row 74, supplier `南通艺之博纸制品有限公司`, cost 3.0, stable/promo price 77 and estimated daily sales 2. Production was not connected, deployed, restarted or modified.
