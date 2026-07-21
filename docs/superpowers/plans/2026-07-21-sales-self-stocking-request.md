# 销售自选与备货申请 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 补齐运营正式备货申请，并让销售自选商品按库存/备货决策进入导出、待刊登或暂不推进。

**Architecture:** 继续以 `SalesClaimForecast` 表示运营对子 SKU 的责任与后半段状态，以现有 `StockingRequest` 保存运营最终申请，以 `ExportBatch/ExportRow` 记录主管选中导出的快照。销售自选创建普通 opportunity/snapshot/claim 后复用现有到货、二次调研和刊登链路；前端复用 `stock` 导航并按角色显示运营申请页或主管导出中心。

**Tech Stack:** FastAPI、SQLAlchemy 2、Alembic、Pydantic、openpyxl、React 18、TypeScript、Vite、Node test runner、Docker Compose。

## Global Constraints

- 仅开发环境验收；不得连接、重启或部署生产服务器 `101.132.26.138`。
- 不接入旧选品3、选品4 Excel；不新增工作流引擎或第三套选品工作台。
- 库存由运营人工确认；决策粒度是“运营 + 子 SKU”。
- 一条 claim 最多一条有效 `StockingRequest`；一条 `ExportRow` 必须可追溯到 request 和 claim。
- `备货数量 = ceil(备货单销 × 30)`；成本、单个体积、备货单销必须大于 0。
- 备货仓库为可选自由文本，可留空；补货原因仅在“补货”时必填。
- 申请日期默认北京时间当天且可编辑；Excel B 列输出申请日期，不使用导出时间。
- 主管只导出勾选的 `submitted` 申请；成功后转 `exported/waiting_arrival`，失败不推进，已导出不重复导出。
- PLM 只匹配存在 `ExportRow` 的 `waiting_arrival` claim；销售自选无需 ReviewRecord。
- ERP token 仅在内存；业务头使用 `Authorization: <accessToken>`，不得使用 Bearer/Cookie/固定 token；所有 URL 与凭据走环境变量。
- 不提交密码、token、Cookie、`.env`、测试下载产物或生产数据。

---

### Task 1: 备货申请数据模型、状态与纯计算

**Files:**
- Modify: `backend/app/models.py`
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/workflow_status.py`
- Modify: `backend/app/services.py`
- Create: `backend/alembic/versions/c9d1e2f3a456_add_stocking_request_workflow.py`
- Create: `backend/tests/test_stocking_requests.py`
- Create: `backend/tests/test_stocking_migration.py`
- Modify: `backend/tests/test_workflow_models.py`

**Interfaces:**
- Produces `stocking_quantity(daily_sales: float) -> int`.
- Produces `stocking_totals(cost_price: float, unit_volume: float, quantity: int) -> tuple[float, float]`.
- Produces `create_stocking_draft_for_claim(db, claim_record_id, actor_name=None) -> StockingRequest`, idempotent by claim.
- Adds `CLAIM_WAITING_STOCKING_REQUEST = "waiting_stocking_request"` and `CLAIM_STOCKING_PAUSED = "stocking_paused"`.

- [ ] **Step 1: Write failing model/calculation tests**

  Add tests equivalent to:

  ```python
  assert services.stocking_quantity(2) == 60
  assert services.stocking_quantity(2.01) == 61
  amount, volume = services.stocking_totals(12.5, 0.002, 61)
  assert amount == 762.5
  assert volume == 0.122
  ```

  Create two claims for one opportunity and assert each gets its own request; repeated creation for one claim returns the same request.

- [ ] **Step 2: Verify RED**

  Run:

  ```powershell
  & 'E:\Project\Hengzhe-New-Product-Workflow\.venv\Scripts\python.exe' -m pytest tests\test_stocking_requests.py tests\test_stocking_migration.py tests\test_workflow_models.py -q
  ```

  Expected: failure because the new fields/functions/revision do not exist.

- [ ] **Step 3: Implement the minimal schema**

  Add nullable migration-safe fields:

  ```python
  # SalesClaimForecast
  inventory_available: bool | None
  needs_stocking: bool | None
  stocking_decision_updated_at: datetime | None

  # StockingRequest
  claim_record_id: str | None  # FK + unique index for new records
  application_date: date | None
  submitted_at: datetime | None
  unit_volume_source: str | None

  # ExportRow
  stocking_request_id: str | None
  application_date: date | None
  stocking_type: str | None
  cost_price: float | None
  unit_volume: float | None
  amount: float | None
  volume: float | None
  replenishment_reason: str | None
  ```

  Keep old rows nullable. Replace every stocking `round(daily_sales * 30)` with one `math.ceil` helper. Change review approval to create per-claim drafts and set `waiting_stocking_request`.

- [ ] **Step 4: Verify GREEN**

  Repeat Step 2; run `alembic heads` and require exactly one head.

- [ ] **Step 5: Commit**

  ```powershell
  git add backend/app backend/alembic/versions/c9d1e2f3a456_add_stocking_request_workflow.py backend/tests/test_stocking_requests.py backend/tests/test_stocking_migration.py backend/tests/test_workflow_models.py
  git commit -m "feat: add stocking request state model"
  ```

### Task 2: ERP 产品体积解析与可手填降级

**Files:**
- Create: `backend/app/erp_product_list.py`
- Modify: `backend/app/config.py`
- Modify: `.env.example`
- Create: `backend/tests/test_erp_product_list.py`
- Modify: `backend/tests/test_config.py`

**Interfaces:**
- Produces `calculate_unit_volume(row: Mapping[str, object]) -> float | None`.
- Produces `parse_product_list_workbook(content: bytes, requested_skus: list[str]) -> dict[str, float | None]`.
- Produces `fetch_product_volumes(skus: list[str], settings: Settings) -> dict[str, float | None]`.

- [ ] **Step 1: Write failing parser/orchestration tests**

  Build in-memory workbooks with exact headers and assert:

  ```python
  assert calculate_unit_volume(packaging_complete) == 0.000132916
  assert calculate_unit_volume(packaging_incomplete_product_complete) == 0.000088775
  assert calculate_unit_volume(both_incomplete) is None
  ```

  Monkeypatch HTTP calls and assert login uses Open Login, business header is exactly `Authorization: token`, product request contains `skuList/isfile/portionFieldSet`, polling ignores old/failed/non-`productList` rows, and error messages contain no credentials/token.

- [ ] **Step 2: Verify RED**

  Run `pytest tests\test_erp_product_list.py tests\test_config.py -q`; expect missing module/settings failures.

- [ ] **Step 3: Implement minimal client**

  Add environment-only settings:

  ```python
  erp_login_url: str = ""
  erp_product_list_url: str = ""
  erp_download_list_url: str = ""
  erp_username: str = ""
  erp_password: str = ""
  ```

  Use stdlib HTTP and openpyxl. Packaging dimensions must be all valid before use; otherwise use all product dimensions. On ERP failure return `None` per SKU so the UI can request manual volume.

- [ ] **Step 4: Verify GREEN**

  Repeat Step 2. Confirm no external network access occurred and output contains no secrets.

- [ ] **Step 5: Commit**

  Commit message: `feat: resolve stocking volume from ERP`.

### Task 3: 运营申请、销售自选与权限 API

**Files:**
- Modify: `backend/app/routers/stocking.py`
- Modify: `backend/app/services.py`
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/product_board.py`
- Modify: `backend/tests/test_stocking_requests.py`
- Modify: `backend/tests/test_auth.py`
- Modify: `backend/tests/test_product_board.py`
- Modify: `backend/tests/test_mvp_flow.py`
- Modify: `backend/tests/test_secondary_research.py`

**Interfaces:**
- Consumes Task 1 state/helpers and Task 2 volume resolver.
- Produces operator endpoints for self selection, own requests, save, submit, decision, and volume preview.

- [ ] **Step 1: Write failing API tests**

  Assert exact cases:

  ```python
  # selected stock branch
  assert response.status_code == 200
  assert claim.downstream_status == "waiting_stocking_request"

  # inventory exists + no stock
  assert claim.downstream_status == "waiting_listing"

  # no inventory + no stock
  assert claim.downstream_status == "stocking_paused"
  ```

  Cover operator A receiving 403 for operator B's request; sales-self creates one opportunity/snapshot/claim per child; duplicate child SKU makes the whole batch fail; warehouse may be blank; cost/volume/daily sales/country/date are required on submit; replenishment requires reason; submitted but not exported remains editable; exported is read-only.

- [ ] **Step 2: Verify RED**

  Run focused request/auth/product-board tests and confirm endpoint/status failures are expected.

- [ ] **Step 3: Implement minimal APIs**

  Define request models with:

  ```python
  class StockingRequestUpdate(BaseModel):
      application_date: date
      request_type: Literal["initial", "replenishment"]
      cost_price: float
      unit_volume: float
      daily_sales: float
      country: str
      warehouse: str | None = None
      reason: str | None = None
  ```

  Remove router-wide manager dependency; apply `require_roles("operator")` or `require_roles("manager")` per endpoint. Always derive operator name from `AuthContext`. Use a single transaction for multi-child creation. Generate `销售自选YYYYMMDD` in Asia/Shanghai.

- [ ] **Step 4: Verify GREEN**

  Run focused tests, then `test_mvp_flow.py` and `test_secondary_research.py`.

- [ ] **Step 5: Commit**

  Commit message: `feat: add operator stocking request workflow`.

### Task 4: 主管选择导出、PLM 门槛与追溯

**Files:**
- Modify: `backend/app/routers/stocking.py`
- Modify: `backend/app/services.py`
- Modify: `backend/app/plm_processing.py`
- Modify: `backend/tests/test_stocking_export.py`
- Modify: `backend/tests/test_export_batch.py`
- Modify: `backend/tests/test_plm_processing.py`
- Modify: `backend/tests/test_traceability_export.py`

**Interfaces:**
- Consumes request submission snapshot.
- Produces `POST /stocking/available-list/export` with body `{"request_ids": ["..."]}`.

- [ ] **Step 1: Write failing export/arrival tests**

  Assert draft requests are absent, selected submitted requests only are exported, B is application date, H–O use final values, manager identity is recorded, failure rolls back, exported requests disappear, and repeated IDs cannot re-export. Assert PLM rejects `waiting_export`, accepts only `waiting_arrival + ExportRow`, and accepts sales-self without ReviewRecord.

- [ ] **Step 2: Verify RED**

  Run:

  ```powershell
  & 'E:\Project\Hengzhe-New-Product-Workflow\.venv\Scripts\python.exe' -m pytest tests\test_stocking_export.py tests\test_export_batch.py tests\test_plm_processing.py tests\test_traceability_export.py -q
  ```

- [ ] **Step 3: Implement selected export**

  Build workbook bytes from current request snapshots first; only after successful build create `ExportBatch/ExportRow`, set each request to `exported`, and set only the linked claim to `waiting_arrival`. PLM query must require an `ExportRow` existence join and must not require ReviewRecord.

- [ ] **Step 4: Verify GREEN**

  Repeat Step 2, then run full backend `pytest -q`.

- [ ] **Step 5: Commit**

  Commit message: `feat: export submitted stocking requests`.

### Task 5: 前端运营申请与主管导出界面

**Files:**
- Create: `frontend/src/stockingRequests.ts`
- Create: `frontend/src/StockingRequestView.tsx`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/productBoard.ts`
- Modify: `frontend/src/styles.css`
- Create: `frontend/tests/stockingRequests.test.ts`
- Modify: `frontend/tests/reviewLayout.test.ts`
- Modify: `frontend/tests/productBoard.test.ts`
- Modify: `frontend/tests/listingObservation.test.ts`
- Modify: `frontend/package.json`

**Interfaces:**
- Consumes Tasks 3–4 API.
- Produces role-adaptive `stock` screen.

- [ ] **Step 1: Write failing helper/layout tests**

  Add `stockingRequests.test.ts` to the explicit package script. Assert branch mapping, `Math.ceil(2.01 * 30) === 61`, manual volume `> 0`, conditional reason, optional warehouse, sales-self cost required, role labels, selected export body, paused board label, and ordinary waiting-listing compatibility.

- [ ] **Step 2: Verify RED**

  Run `npm.cmd test`; new tests must fail because helpers/UI/API are missing.

- [ ] **Step 3: Implement minimal UI**

  Keep `App.tsx` as orchestration only and add focused `StockingRequestView.tsx`. Reuse existing group cards/forms/tabs/table styles. Operators get “备货申请” and sales-self form; managers get existing period/16-column view plus status filter, checkboxes, select all, and “导出选中”. Do not add a dependency.

- [ ] **Step 4: Verify GREEN**

  Run `npm.cmd test` and `npm.cmd run build`.

- [ ] **Step 5: Commit**

  Commit message: `feat: add stocking request workbench`.

### Task 6: 隔离集成验收、文档与开发部署

**Files:**
- Modify: `backend/scripts/seed_demo_statuses.py`
- Modify: `backend/tests/test_seed_demo_statuses.py`
- Modify: `docs/00-新会话交接.md`
- Modify: `docs/01-需求文档-东南亚新品流程.md`
- Modify: `docs/02-功能实现状态.md`
- Modify: `docs/04-系统架构重新设计方案.md`
- Modify: `docs/08-端到端流程链路规划.md`
- Modify: `docs/20-项目推进总控.md`
- Modify: `docs/23-销售自选与备货申请需求对齐.md`
- Modify: `docs/README.md`

**Interfaces:**
- Consumes all completed functionality.
- Produces reproducible dev test data and deploys only to `139.224.2.166:18081`.

- [ ] **Step 1: Extend seed test first**

  Require seed output to include `waiting_stocking_request`, `stocking_paused`, direct `waiting_listing`, and one `submitted` request. Watch it fail, minimally update the seed, then watch it pass.

- [ ] **Step 2: Run full local verification**

  ```powershell
  & 'E:\Project\Hengzhe-New-Product-Workflow\.venv\Scripts\python.exe' -m pytest -q
  Push-Location frontend; npm.cmd test; npm.cmd run build; Pop-Location
  Push-Location backend; & 'E:\Project\Hengzhe-New-Product-Workflow\.venv\Scripts\python.exe' -m alembic heads; Pop-Location
  docker compose config --quiet
  ```

  Require clean outputs, one Alembic head, and no tracked secret/download file.

- [ ] **Step 3: Review**

  Generate task and whole-branch review packages. Fix every Critical/Important finding with covering tests, then rerun affected and full suites.

- [ ] **Step 4: Deploy only to dev**

  Inspect the existing dev deployment SOP, acquire no production resources, deploy the reviewed commit to `139.224.2.166:18081`, run Alembic, verify health/database-backed APIs/login/roles, and exercise the two sample SKUs. Keep DingTalk auto-send off unless the configured test receiver is explicitly刘学城.

- [ ] **Step 5: Align documentation**

  Run `neat-freak`, reconcile status/hand-off/total-control docs to actual code and deployed commit, keep historical docs but do not delete them automatically, and append the weekly work log without secrets.

- [ ] **Step 6: Commit**

  Commit message: `docs: align stocking request delivery`.
