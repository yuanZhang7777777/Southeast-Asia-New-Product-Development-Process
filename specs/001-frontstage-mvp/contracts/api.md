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

- `approved` makes a claimed submission exportable.
- `confirmed_not_claim` marks the outcome as `已确认不认领`.
- `returned_for_supplement` returns the task to the operator.
- Supervisor cannot edit operator-submitted claim daily sales or not-claim reason.

## Export

### `GET /stocking/available-list`

Lists exportable approved claim rows.

**Response row**:

- Salesperson
- Main SKU
- Child SKU
- Claim daily sales
- Stocking quantity
- Country
- Warehouse
- Source batch

**Rules**:

- Only approved claim records appear.
- Confirmed not-claim records never appear.
- Multiple approved claims for one child SKU appear as multiple rows.

### `GET /stocking/available-list/export`

Exports `备货申请表`.

**Workbook rules**:

- Sheet name: `备货申请表`
- Columns: `操作状态`, `时间`, `备货类型`, `选品数据源`, `销售员`, `主SKU`, `子sku`, `成本价`, `单个体积`, `备货单销`, `备货数量`, `备货国家`, `备货仓库`, `货值`, `体积`, `补货原因`
- `备货数量 = 备货单销 × 30`
- `补货原因` is empty in the first version

### Full-field traceability export

Exports the same approved child-SKU claim rows with central-table fields before `开发是否接受核价结果` plus platform claim/review/export fields.

**Rules**:

- Same row scope as stocking export.
- Used for leadership review and traceability.
- Not an input workbook and not an online-sheet writeback.
