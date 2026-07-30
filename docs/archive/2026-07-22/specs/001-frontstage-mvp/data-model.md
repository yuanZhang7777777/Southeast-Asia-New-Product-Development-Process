# Data Model: Frontstage New Product MVP

## SourceImportBatch

Represents one workbook import action.

**Fields**:

- `id`
- `source_type`: `selection1_developer_claim_feedback` or `selection2_caigen_claim_feedback`
- `source_file`
- `source_sheet`
- `imported_by`
- `imported_at`
- `created_count`
- `updated_count`
- `skipped_count`
- `status`

**Relationships**:

- Has many `SourceRowSnapshot`
- Has many `NewProductOpportunity`

**Validation rules**:

- Source type must be one of the two first-version feedback sources.
- Import must not proceed for unsupported workbook types.

## SourceRowSnapshot

Immutable trace of a source row.

**Fields**:

- `id`
- `import_batch_id`
- `opportunity_id`
- `source_file`
- `source_sheet`
- `source_row`
- `column_range`
- `payload`
- `created_at`

**Validation rules**:

- Must keep source file, sheet, and row number.
- Must preserve original source fields even when mapped target fields are empty.

## NewProductOpportunity

One imported child SKU opportunity aligned to the central field dictionary.

**Fields**:

- `id`
- `source_type`
- `source_file`
- `source_sheet`
- `source_row`
- `batch`
- `country`
- `site`
- `main_sku`
- `sub_sku`
- `main_sku_name`
- `sub_sku_name`
- `category_level1`
- `keyword`
- `product_type`
- `current_status`
- `snapshot`

**Relationships**:

- Belongs to a `MainSkuGroup` by `main_sku + source batch`
- Has many `OperatorClaimRecord`
- Has many `SupervisorReviewRecord`

**State transitions**:

```text
pending_assignment
-> assigned
-> claim_submitted
-> ready_for_stocking

pending_assignment / assigned
-> claim_rejected
-> 已确认不认领

claim_submitted / claim_rejected
-> returned_for_supplement
-> claim_submitted / claim_rejected
```

## MainSkuGroup

Logical assignment unit for one main SKU in one source batch.

**Fields**:

- `id`
- `source_type`
- `source_batch`
- `main_sku`
- `country`
- `site`
- `assigned_operator`
- `status`
- `sub_sku_count`

**Relationships**:

- Contains many `NewProductOpportunity`
- Has assignment tasks

**Validation rules**:

- Assignment must not split child SKUs in the same main SKU group.
- Group status may be `部分认领通过` when child SKU outcomes differ.

## OperatorClaimRecord

One operator's decision for one child SKU.

**Fields**:

- `id`
- `opportunity_id`
- `operator_name`
- `claim_result`: `claim` or `reject`
- `claim_daily_sales`
- `reject_reason`
- `feedback_summary`
- `note`
- `source`: `platform`, `source_prefill`, or `caigen_self_claim`
- `first_submitted_at`
- `last_updated_at`
- `status`

**Validation rules**:

- `claim_daily_sales` is required when `claim_result=claim`.
- `reject_reason` is required when `claim_result=reject`.
- Caigen opportunity pool may have multiple `claim` records for the same child SKU.
- Ignoring a Caigen self-claim opportunity does not create a reject record.

## SupervisorReviewRecord

Supervisor decision on one operator submission.

**Fields**:

- `id`
- `claim_record_id`
- `opportunity_id`
- `reviewer_name`
- `review_status`: `approved`, `confirmed_not_claim`, or `returned_for_supplement`
- `review_comment`
- `reviewed_at`

**Validation rules**:

- Supervisor cannot edit operator fields.
- `confirmed_not_claim` changes the opportunity/claim outcome to `已确认不认领`.
- `approved` on a claim record creates or reuses one operator-owned stocking-request draft; approval alone is not exportable.

## StockingRequest

One operator-owned request for one approved claim / child SKU.

**Fields**:

- `id`
- `opportunity_id`
- `claim_record_id` (unique)
- `application_date`
- `submitted_at`
- `request_type`: `initial` or `replenishment`
- `salesperson_name`
- `main_sku`
- `sub_sku`
- `cost_price`
- `unit_volume`
- `unit_volume_source`: `erp`, `manual`, or null
- `daily_sales`
- `quantity`
- `country`
- `warehouse`
- `amount`
- `volume`
- `reason`
- `status`: `draft`, `submitted`, or `exported`

**Validation rules**:

- Only the authenticated owner can save or submit; exported requests are read-only.
- Saving an already submitted request reopens it as `draft` and requires resubmission.
- `quantity = ceil(daily_sales × 30)`; amount and volume are calculated from final submitted values.
- `warehouse` is optional; `reason` is required only for `replenishment`.
- Unit volume comes from ERP dimensions or a positive manual value; source-table aggregate volume is not silently reused.

## FlowTask

Internal task record for assignment, operator claim, and supervisor review.

**Fields**:

- `id`
- `node_code`
- `task_type`
- `assignee_name`
- `assignee_role`
- `status`
- `deadline_at`
- `completed_at`

**Validation rules**:

- DingTalk todo ID is optional and not required in the first version.
- DingTalk entry links must not be treated as authorization.

## ExportBatch

One export action.

**Fields**:

- `id`
- `exported_by`
- `exported_at`
- `file_name`
- `scope`
- `row_count`
- `status`

**Relationships**:

- Has many `ExportRow`

**Validation rules**:

- Must include exporter, export time, file name, and export scope.

## ExportRow

One immutable child-SKU snapshot row in an exported workbook. `stocking_available` rows come from selected submitted requests; traceability batches may also contain confirmed not-claim rows.

**Fields**:

- `id`
- `export_batch_id`
- `opportunity_id`
- `claim_record_id`
- `stocking_request_id`
- `application_date`
- `stocking_type`
- `selection_source`
- `cost_price`
- `unit_volume`
- `amount`
- `volume`
- `replenishment_reason`
- `salesperson_name`
- `main_sku`
- `sub_sku`
- `claim_daily_sales`
- `stocking_quantity`
- `country`
- `warehouse`

**Validation rules**:

- `stocking_quantity = ceil(claim_daily_sales × 30)`.
- Confirmed not-claim records are excluded from `stocking_available` rows but may appear in a separate traceability export batch.
- Multiple selected submitted requests for the same child SKU generate independent export rows.
