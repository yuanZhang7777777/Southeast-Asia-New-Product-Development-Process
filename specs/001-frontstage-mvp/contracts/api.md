# API Contract: Frontstage New Product MVP

This contract describes the first-version platform API behavior. Field names are stable business contracts; implementation can evolve as long as these behaviors remain true.

## Import

### `POST /opportunities/import/selection1`

Imports the development department feedback workbook.

**Request**:

- `source_file`: absolute or server-accessible workbook path
- `source_sheet`: sheet name, for example `开发0623期`
- `max_rows`: optional import limit for validation runs

**Success response**:

- `source_file`
- `source_sheet`
- `imported_count`
- `created_count`
- `updated_count`
- `skipped_count`
- `market_research_count`
- `prefill_claim_count`
- `task_count`

**Rules**:

- Duplicate source file + sheet + row updates existing records.
- Source row snapshots must be retained.

### `POST /opportunities/import/selection2`

Imports the Caigen feedback workbook.

**Request**:

- `source_file`
- `source_sheet`
- `max_rows`

**Success response**:

- Same summary fields as selection1 import.
- Additional count for opportunity-pool rows if implemented separately.

**Rules**:

- Missing site does not block import.
- Fields that cannot map to central-table target fields remain empty.
- Assigned/main salesperson must receive a required task when present.

## Assignment

### `POST /assignments/preview`

Generates one-click assignment suggestions.

**Request**:

- `opportunity_ids`
- Candidate operators or reference to current personnel config

**Response**:

- List of main SKU groups
- Suggested assignee
- Sub SKU count
- Match reason when available

**Rules**:

- Main SKU group is the assignment unit.
- Priority order is key site, key category 1, key category 2, then current load.

### `POST /assignments/confirm`

Creates operator claim tasks from supervisor-confirmed assignment.

**Request**:

- Opportunity IDs or main SKU group IDs
- Assignee name / ID
- Optional deadline

**Response**:

- Created task IDs

## Claim

### `POST /claims`

Operator submits claim or not-claim.

**Request**:

- `opportunity_id`
- `salesperson_name`
- `claim_result`: `claim` or `reject`
- `claim_daily_sales`: required when `claim_result=claim`
- `reject_reason`: required when `claim_result=reject`
- `feedback_summary`
- `note`

**Response**:

- Claim record ID

**Rules**:

- Claim daily sales is a daily-sales value.
- Not-claim reason is required for not-claim submissions.
- First-created and last-updated timestamps must be retained for operator-submitted fields.

## Review

### `POST /reviews`

Supervisor reviews an operator submission.

**Request**:

- `opportunity_id` or claim record ID
- `reviewer_name`
- `review_status`: `approved`, `confirmed_not_claim`, or `returned_for_supplement`
- `review_comment`

**Response**:

- Review record ID

**Rules**:

- `approved` creates (or reuses) one `draft` stocking request per claimed operator + child SKU and moves the claim to `waiting_stocking_request`; approval alone is not exportable.
- `confirmed_not_claim` marks the outcome as `已确认不认领`.
- `returned_for_supplement` returns the task to the operator.
- Supervisor cannot edit operator-submitted claim daily sales or not-claim reason.

## Stocking requests and export

All operator endpoints derive the operator identity from the authenticated role mapping. A manager or another operator cannot supply a salesperson name to edit someone else's request.

### `GET /stocking/requests` and `POST /stocking/requests` (manager compatibility)

`GET` returns the latest 200 stocking requests for manager inspection. `POST` creates or reuses a draft tied to an existing claim; the normal review flow creates this draft automatically, so the current workbench does not require a separate manager action.

### `GET /stocking/export-periods` (manager)

Returns all non-disabled imported business periods plus any eligible period not present in `ImportBatch`, with current `submitted + waiting_export` stocking counts and traceability counts that also include confirmed not-claim rows.

### `POST /stocking/self-selections` (operator)

Creates one sales-self main SKU with one or more child SKUs in one transaction. Child decisions are:

- `inventory_available=true, needs_stocking=false` -> `waiting_listing`, no stocking request.
- `inventory_available=false, needs_stocking=true` -> request `draft` + claim `waiting_stocking_request`.
- `inventory_available=false, needs_stocking=false` -> recoverable `stocking_paused`, no downstream task.

The child list must be non-empty and child SKUs must be unique inside the request; any invalid row rejects the entire batch. `inventory_available=true, needs_stocking=true` is contradictory and must be rejected at the API boundary.

### `GET /stocking/my-requests` (operator)

Returns the authenticated operator's draft, submitted and exported requests plus direct-listing and paused records. Exported requests remain visible as read-only history.

### `PUT /stocking/requests/{request_id}` (operator)

Saves the authenticated operator's draft or updates a not-yet-exported submitted request. Editable fields are application date, request type, final cost price, unit volume/source, daily sales, country, optional warehouse and conditional reason. Editing a submitted request reopens it as `draft`, returns the claim to `waiting_stocking_request` and requires a new submit. Exported requests are immutable.

### `POST /stocking/requests/{request_id}/submit` (operator)

Validates the final request and calculates authoritative values:

- cost price, unit volume and daily sales must be finite and greater than zero;
- `quantity = ceil(daily_sales × 30)`;
- `amount = cost_price × quantity`;
- `volume = unit_volume × quantity`;
- warehouse is optional free text;
- reason is required only for `replenishment`.

Success sets request `submitted` and claim `waiting_export`.

### `POST /stocking/decisions/{claim_record_id}` (operator)

Updates the authenticated operator's inventory/stocking decision. A paused record can be changed back to stocking and resume as `waiting_stocking_request`.

### `POST /stocking/volume-preview` (operator)

**Request:** `{"skus":["CHILD-1", "CHILD-2"]}`. The raw list contains 1-500 strings; the router trims, drops blank values and de-duplicates in order, and returns 400 if nothing remains.

**Response:** one row per unique SKU with `unit_volume` and `status=resolved|manual_required`. Missing ERP configuration, lookup failure or incomplete dimensions must return the manual fallback without exposing credentials. The preview itself does not persist data; when the UI saves a resolved value it labels the source `erp`, while operator input is labeled `manual`. This source is a provenance label saved on the request; the normal UI includes it in the request update audit, but it is not tamper-proof proof of an ERP response.

### `GET /stocking/available-list` (manager)

Lists only requests with `request.status=submitted` whose claim is `waiting_export`. Optional filters remain `source_sheet`, `business_period` and `import_batch_id`. Confirmed not-claim, draft, paused, direct-listing and already exported records never appear.

### `POST /stocking/available-list/export` (manager)

**Request:** `{"request_ids":["request-id-1", "request-id-2"]}`. The list must contain 1-500 non-empty, unique IDs.

The server locks and revalidates the exact selected submitted requests, builds the workbook, then commits one `stocking_available` `ExportBatch` with immutable `ExportRow` snapshots linked to both request and claim. Success sets each request to `exported` and each claim to `waiting_arrival`. If any selected row is missing, ineligible or concurrently changed, the entire request fails and no row advances.

**Workbook rules**:

- File name: `海外仓备货申请表.xlsx`; rows are split into country sheets.
- Columns: `操作状态`, `申请日期`, `备货类型`, `选品数据源`, `销售员`, `主SKU`, `子sku`, `成本价`, `单个体积`, `备货单销`, `备货数量`, `备货国家`, `备货仓库`, `货值`, `体积`, `补货原因`.
- Column B is the operator's application date, never the export timestamp.
- Quantity, amount and volume use the authoritative submitted snapshot; warehouse may be blank and replenishment reason may not.

### `GET /stocking/traceability/export` (manager)

Exports current `submitted + waiting_export` child-SKU requests plus confirmed not-claim rows. It includes all 80 central-table fields from column A through and including column CB `开发是否接受核价结果`, followed by platform claim/review/export fields.

**Rules**:

- Independent from the formal stocking-export action: it reads the current eligible submitted scope plus confirmed not-claim traceability rows, does not substitute for operator submission, and does not advance claims to `waiting_arrival`.
- Used for leadership review and traceability.
- Not an input workbook and not an online-sheet writeback.
