import math
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class HealthResponse(BaseModel):
    status: str
    app: str
    environment: str


class UserRead(BaseModel):
    id: str
    dingtalk_user_id: str | None
    name: str
    enabled: bool

    model_config = {"from_attributes": True}


class DingTalkLoginRequest(BaseModel):
    auth_code: str | None = None
    dingtalk_user_id: str | None = None
    name: str = "鏈湴娴嬭瘯鐢ㄦ埛"


class AccountLoginRequest(BaseModel):
    name: str
    password: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(min_length=6)


class AuthRoleRead(BaseModel):
    role: str
    name: str


class AuthLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead
    roles: list[AuthRoleRead]
    default_role: str
    operator_name: str | None = None


class OpportunityBase(BaseModel):
    source_type: str = "manual"
    source_file: str | None = None
    source_sheet: str | None = None
    source_row: int | None = None
    batch: str | None = None
    country: str | None = None
    site: str | None = None
    developer_department: str | None = None
    developer_name: str | None = None
    category_level1: str | None = None
    category_level2: str | None = None
    keyword: str | None = None
    image_url: str | None = None
    main_sku_name: str | None = None
    main_sku: str
    sub_sku_name: str | None = None
    sub_sku: str
    product_type: str | None = None
    reason: str | None = None


class OpportunityCreate(OpportunityBase):
    snapshot: dict[str, Any] = Field(default_factory=dict)


class PendingReviewClaimRead(BaseModel):
    claim_record_id: str
    claim_result: str
    salesperson_name: str | None = None
    claim_daily_sales: float | None = None
    reject_reason: str | None = None
    feedback_summary: str | None = None
    note: str | None = None


# 列表专用轻量视图：不带 snapshot（源表快照可达数十 KB/行），完整快照走 GET /opportunities/{id}。
class OpportunityListRead(OpportunityBase):
    id: str
    current_status: str
    claim_pool_open: bool = False
    latest_claim_record_id: str | None = None
    latest_claim_result: str | None = None
    latest_claim_salesperson: str | None = None
    latest_claim_daily_sales: float | None = None
    latest_reject_reason: str | None = None
    latest_feedback_summary: str | None = None
    latest_claim_note: str | None = None
    latest_review_status: str | None = None
    latest_review_comment: str | None = None
    pending_review_claims: list[PendingReviewClaimRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class HistoricalClaimRead(BaseModel):
    id: str
    salesperson_name: str | None = None
    claim_result: str | None = None
    claim_daily_sales: float | None = None
    reject_reason: str | None = None
    feedback_summary: str | None = None
    source_column: str | None = None
    source_period: str | None = None
    source_row: int | None = None
    source_note: Any | None = None
    evidence_images: list[dict[str, Any]] = Field(default_factory=list)
    manager_review_status: str | None = None
    manager_review_comment: str | None = None


class OpportunityRead(OpportunityListRead):
    snapshot: dict[str, Any] = Field(default_factory=dict)
    historical_claims: list[HistoricalClaimRead] = Field(default_factory=list)


class OpportunityImportRequest(BaseModel):
    items: list[OpportunityCreate]


class OpportunityUpdateRequest(BaseModel):
    main_sku: str | None = None
    sub_sku: str | None = None
    main_sku_name: str | None = None
    sub_sku_name: str | None = None
    site: str | None = None
    country: str | None = None
    category_level1: str | None = None
    category_level2: str | None = None
    developer_department: str | None = None
    developer_name: str | None = None
    keyword: str | None = None
    product_type: str | None = None
    reason: str | None = None
    image_url: str | None = None
    current_status: str | None = None
    source_cells: dict[str, Any] | None = None
    edit_reason: str

    model_config = {"extra": "forbid"}


class Selection1ImportRequest(BaseModel):
    source_file: str | None = None
    source_sheet: str = "开发0623期"
    business_period: str | None = None
    max_rows: int | None = None


class Selection1ImportResponse(BaseModel):
    import_batch_id: str | None = None
    source_file: str
    source_sheet: str
    business_period: str | None = None
    imported_count: int
    created_count: int
    updated_count: int
    skipped_count: int
    market_research_count: int
    prefill_claim_count: int
    task_count: int


class Selection2ImportRequest(BaseModel):
    source_file: str | None = None
    source_sheet: str = "5.26期"
    max_rows: int | None = None


class Selection2ImportResponse(BaseModel):
    import_batch_id: str | None = None
    source_file: str
    source_sheet: str
    business_period: str | None = None
    imported_count: int
    created_count: int
    updated_count: int
    skipped_count: int
    market_research_count: int
    prefill_claim_count: int
    task_count: int


class ImportJobRead(BaseModel):
    id: str
    kind: str
    status: str
    source_file: str
    source_sheet: str
    business_period: str | None = None
    error: str | None = None
    result: dict[str, Any] | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}


class ExcelSheetListResponse(BaseModel):
    sheets: list[str]
    default_sheet: str | None = None


class ImportBatchSummary(BaseModel):
    id: str
    source_type: str
    source_file: str | None
    source_sheet: str | None
    business_period: str | None = None
    imported_by: str | None
    imported_at: datetime | None
    created_count: int
    updated_count: int
    skipped_count: int
    status: str

    model_config = {"from_attributes": True}


class ExportBatchMetadata(BaseModel):
    id: str
    exported_by: str | None
    exported_at: datetime | None
    file_name: str
    scope: str
    row_count: int
    status: str

    model_config = {"from_attributes": True}


class AssignmentPreviewItem(BaseModel):
    main_sku: str
    sub_sku_count: int
    suggested_assignee: str | None
    match_reason: str | None = None
    opportunity_ids: list[str] = Field(default_factory=list)


class AssignmentPreviewRequest(BaseModel):
    opportunity_ids: list[str]
    candidates: list[str] = Field(default_factory=list)


class AssignmentPreviewResponse(BaseModel):
    items: list[AssignmentPreviewItem]


class AssignmentConfirmRequest(BaseModel):
    opportunity_ids: list[str]
    assignee_name: str
    assignee_user_id: str | None = None
    deadline_at: datetime | None = None


class ReassignRequest(BaseModel):
    task_id: str
    assignee_name: str
    assignee_user_id: str | None = None
    reason: str


class TaskRead(BaseModel):
    id: str
    flow_instance_id: str
    opportunity_id: str | None = None
    node_code: str
    task_type: str
    assignee_name: str | None
    assignee_role: str | None
    status: str
    deadline_at: datetime | None
    completed_at: datetime | None
    claim_record_id: str | None = None
    claim_result: str | None = None
    claim_daily_sales: float | None = None
    reject_reason: str | None = None
    feedback_summary: str | None = None
    claim_note: str | None = None
    review_status: str | None = None
    review_comment: str | None = None

    model_config = {"from_attributes": True}


class AssignmentBoardRow(BaseModel):
    task_id: str
    opportunity_id: str
    batch: str | None = None
    site: str | None = None
    category_level1: str | None = None
    category_level2: str | None = None
    main_sku: str
    main_sku_name: str | None = None
    sub_sku: str
    sub_sku_name: str | None = None
    assignee_name: str | None = None
    task_status: str
    opportunity_status: str
    assigned_at: datetime | None = None


class AssignmentBoardGroup(BaseModel):
    batch: str
    rows: list[AssignmentBoardRow] = Field(default_factory=list)


class AssignmentBoardResponse(BaseModel):
    batches: list[str] = Field(default_factory=list)
    assignees: list[str] = Field(default_factory=list)
    groups: list[AssignmentBoardGroup] = Field(default_factory=list)


class ClaimCreate(BaseModel):
    opportunity_id: str
    salesperson_name: str
    claim_result: str
    claim_daily_sales: float | None = None
    reject_reason: str | None = None
    feedback_summary: str | None = None
    note: str | None = None
    claim_source: str = "assigned_task"
    task_id: str | None = None


class ClaimPoolJoinRequest(BaseModel):
    opportunity_ids: list[str] = Field(min_length=1, max_length=500)
    assignee_name: str | None = None


class ReviewCreate(BaseModel):
    opportunity_id: str
    claim_record_id: str | None = None
    reviewer_name: str
    review_status: str
    review_comment: str | None = None

    model_config = {"extra": "forbid"}

    @field_validator("review_status")
    @classmethod
    def valid_review_status(cls, value: str) -> str:
        allowed = {"approved", "confirmed_not_claim", "returned_for_supplement"}
        if value not in allowed:
            raise ValueError("review_status must be approved, confirmed_not_claim, or returned_for_supplement")
        return value


class BulkReviewCreate(BaseModel):
    opportunity_ids: list[str] = Field(min_length=1, max_length=500)
    reviewer_name: str
    action: str
    review_comment: str | None = None

    model_config = {"extra": "forbid"}

    @field_validator("action")
    @classmethod
    def valid_action(cls, value: str) -> str:
        if value not in {"approve", "reject"}:
            raise ValueError("action must be approve or reject")
        return value

    @field_validator("opportunity_ids")
    @classmethod
    def unique_opportunity_ids(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))


class StockingRequestCreate(BaseModel):
    opportunity_id: str
    claim_record_id: str
    salesperson_name: str | None = None
    daily_sales: float
    country: str | None = None
    warehouse: str | None = None
    reason: str | None = None


class StockingRequestUpdate(BaseModel):
    application_date: date | None = None
    request_type: Literal["initial", "replenishment"] | None = None
    cost_price: float | None = None
    length_cm: float | None = None
    width_cm: float | None = None
    height_cm: float | None = None
    unit_volume: float | None = None
    unit_volume_source: Literal["erp", "manual"] | None = None
    daily_sales: float | None = None
    country: str | None = None
    warehouse: str | None = None
    reason: str | None = None

    model_config = {"extra": "forbid", "allow_inf_nan": False}

    @field_validator("cost_price", "length_cm", "width_cm", "height_cm", "unit_volume", "daily_sales", mode="before")
    @classmethod
    def replace_non_finite_input(cls, value: object) -> object:
        try:
            return "__non_finite__" if value is not None and not math.isfinite(float(value)) else value
        except (TypeError, ValueError):
            return value

    @field_validator("length_cm", "width_cm", "height_cm")
    @classmethod
    def dimensions_must_be_positive(cls, value: float | None) -> float | None:
        if value is not None and value <= 0:
            raise ValueError("dimensions must be greater than zero")
        return value

    @field_validator("request_type")
    @classmethod
    def request_type_must_not_be_null(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("request_type must be initial or replenishment")
        return value


class StockingDecisionUpdate(BaseModel):
    inventory_available: bool
    needs_stocking: bool

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def inventory_and_stocking_are_mutually_exclusive(self) -> "StockingDecisionUpdate":
        if self.inventory_available and self.needs_stocking:
            raise ValueError("inventory_available and needs_stocking cannot both be true")
        return self


class SalesSelfSelectionChildCreate(StockingDecisionUpdate):
    sub_sku: str
    sub_sku_name: str | None = None


class SalesSelfSelectionCreate(BaseModel):
    main_sku: str
    main_sku_name: str | None = None
    country: str
    children: list[SalesSelfSelectionChildCreate] = Field(min_length=1, max_length=500)

    model_config = {"extra": "forbid"}


class VolumePreviewRequest(BaseModel):
    skus: list[str] = Field(min_length=1, max_length=500)

    model_config = {"extra": "forbid"}


class VolumePreviewRead(BaseModel):
    sub_sku: str
    unit_volume: float | None = None
    length_cm: float | None = None
    width_cm: float | None = None
    height_cm: float | None = None
    status: Literal["resolved", "manual_required"]


class StockingRequestRead(BaseModel):
    id: str
    opportunity_id: str
    claim_record_id: str | None
    application_date: date | None
    submitted_at: datetime | None
    request_type: str
    unit_volume_source: str | None
    salesperson_name: str | None
    main_sku: str | None
    sub_sku: str | None
    cost_price: float | None
    length_cm: float | None
    width_cm: float | None
    height_cm: float | None
    unit_volume: float | None
    daily_sales: float | None
    quantity: int
    country: str | None
    warehouse: str | None
    amount: float | None
    volume: float | None
    reason: str | None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class OperatorStockingItemRead(BaseModel):
    opportunity_id: str
    claim_record_id: str
    request_id: str | None = None
    business_period: str | None = None
    country: str | None = None
    source_type: str
    salesperson_name: str
    main_sku: str
    main_sku_name: str | None = None
    sub_sku: str
    sub_sku_name: str | None = None
    inventory_available: bool | None = None
    needs_stocking: bool | None = None
    downstream_status: str
    request: StockingRequestRead | None = None


class StockingExportSelection(BaseModel):
    request_ids: list[str] = Field(min_length=1, max_length=500)

    model_config = {"extra": "forbid"}

    @field_validator("request_ids")
    @classmethod
    def unique_request_ids(cls, value: list[str]) -> list[str]:
        normalized = [request_id.strip() for request_id in value]
        if any(not request_id for request_id in normalized):
            raise ValueError("request_ids must not contain empty values")
        if len(set(normalized)) != len(normalized):
            raise ValueError("request_ids must not contain duplicates")
        return normalized


class AvailableStockingItem(BaseModel):
    opportunity_id: str
    request_id: str
    claim_record_id: str
    business_period: str | None = None
    operation_status: str = "未操作"
    time: datetime | None = None
    application_date: date | None = None
    stocking_type: str = "首次备货"
    selection_source: str
    salesperson_name: str | None
    main_sku: str
    sub_sku: str
    site: str | None
    claim_daily_sales: float
    quantity: int
    stocking_country: str | None = None
    warehouse: str | None = None
    cost_price: float | None = None
    unit_volume: float | None = None
    amount: float | None = None
    volume: float | None = None
    replenishment_reason: str | None = None
    needs_launch_email: str | None = None
    launch_email_status: str | None = None
    review_status: str | None = None
    status: str


class TraceabilityItem(BaseModel):
    opportunity_id: str
    request_id: str | None = None
    claim_record_id: str
    business_period: str | None = None
    traceability_type: str
    operation_status: str
    salesperson_name: str | None = None
    main_sku: str
    sub_sku: str
    site: str | None = None
    claim_result: str | None = None
    claim_daily_sales: float | None = None
    reject_reason: str | None = None
    feedback_summary: str | None = None
    review_status: str | None = None
    review_comment: str | None = None
    source_file: str | None = None
    source_sheet: str | None = None
    source_row: int | None = None


class ExportPeriodSummary(BaseModel):
    business_period: str
    latest_imported_at: datetime | None = None
    stocking_count: int = 0
    traceability_count: int = 0


class ArrivalRecordCreate(BaseModel):
    opportunity_id: str
    claim_record_id: str | None = None
    salesperson_name: str | None = None
    country: str | None = None
    warehouse: str | None = None
    arrived_quantity: int | None = None
    arrived_at: datetime | None = None
    listing_status: str | None = None
    note: str | None = None


class ArrivalRecordRead(ArrivalRecordCreate):
    id: str
    created_at: datetime

    model_config = {"from_attributes": True}


class SecondaryResearchPeerRead(BaseModel):
    claim_record_id: str
    salesperson_name: str | None = None
    claim_daily_sales: float | None = None
    secondary_research_at: datetime | None = None
    secondary_competitor_url: str | None = None
    secondary_conclusion: str | None = None
    product_positioning: str | None = None
    secondary_target_daily_sales: float | None = None
    secondary_selling_points: str | None = None
    secondary_research_submitted_at: datetime | None = None


class SecondaryResearchItemRead(BaseModel):
    claim_record_id: str
    opportunity_id: str
    salesperson_name: str
    claim_daily_sales: float | None = None
    downstream_status: str
    arrival_detected_at: datetime | None = None
    secondary_research_at: datetime | None = None
    secondary_competitor_url: str | None = None
    secondary_conclusion: str | None = None
    product_positioning: str | None = None
    secondary_target_daily_sales: float | None = None
    secondary_selling_points: str | None = None
    secondary_evidence_images: list[dict[str, Any]] = Field(default_factory=list)
    secondary_research_submitted_at: datetime | None = None
    sub_sku: str
    sub_sku_name: str | None = None
    image_url: str | None = None
    reason: str | None = None
    snapshot: dict[str, Any] = Field(default_factory=dict)
    peer_records: list[SecondaryResearchPeerRead] = Field(default_factory=list)


class SecondaryResearchGroupRead(BaseModel):
    key: str
    source_type: str
    business_period: str | None = None
    site: str | None = None
    country: str | None = None
    main_sku: str
    main_sku_name: str | None = None
    salesperson_name: str
    items: list[SecondaryResearchItemRead]


class ProductBoardChildSkuRead(BaseModel):
    opportunity_id: str
    sub_sku: str
    sub_sku_name: str | None = None
    visible_status: str


class ProductBoardResponsibilityRead(BaseModel):
    claim_record_id: str | None = None
    task_id: str | None = None
    opportunity_id: str
    salesperson_name: str | None = None
    sub_sku: str
    claim_daily_sales: float | None = None
    visible_status: str
    arrival_detected_at: datetime | None = None


class ProductBoardGroupRead(BaseModel):
    key: str
    business_period: str | None = None
    site: str | None = None
    country: str | None = None
    main_sku: str
    main_sku_name: str | None = None
    image_url: str | None = None
    child_skus: list[ProductBoardChildSkuRead]
    responsibilities: list[ProductBoardResponsibilityRead]
    summary_tags: list[str] = Field(default_factory=list)


class SecondaryResearchDraftUpdate(BaseModel):
    secondary_research_at: datetime | None = None
    secondary_competitor_url: str | None = None
    secondary_conclusion: str | None = None
    product_positioning: str | None = None
    secondary_target_daily_sales: float | None = None
    secondary_selling_points: str | None = None
    secondary_evidence_images: list[dict[str, Any]] | None = None

    model_config = {"extra": "forbid", "allow_inf_nan": False}

    @field_validator("product_positioning")
    @classmethod
    def valid_product_positioning(cls, value: str | None) -> str | None:
        if value is not None and value not in {"引流款", "利润款", "淘汰款", "稳定款", "清仓款"}:
            raise ValueError("product_positioning must be 引流款, 利润款, 淘汰款, 稳定款, or 清仓款")
        return value

    @field_validator("secondary_target_daily_sales")
    @classmethod
    def valid_target_daily_sales(cls, value: float | None) -> float | None:
        if value is not None and value <= 0:
            raise ValueError("secondary_target_daily_sales must be greater than 0")
        return value


class SecondaryResearchSubmitGroupRequest(BaseModel):
    claim_record_ids: list[str] = Field(min_length=1)


class ManualSecondaryResearchCreate(BaseModel):
    country: str
    site: str | None = None
    main_sku: str
    sub_sku: str
    salesperson_name: str | None = None
    business_period: str | None = None
    main_sku_name: str | None = None
    sub_sku_name: str | None = None
    secondary_competitor_url: str | None = None

    model_config = {"extra": "forbid"}


class PlmArrivalAssignmentRead(BaseModel):
    plm_arrival_item_id: str
    arrival_date: str
    source_file: str | None = None
    source_sheet: str | None = None
    source_row: int | None = None
    country: str | None = None
    warehouse: str | None = None
    main_sku: str | None = None
    sub_sku: str | None = None
    product_name: str | None = None
    plm_salesperson_name: str | None = None
    latest_storage_time: datetime | None = None
    first_listing_time: datetime | None = None
    match_status: str
    existing_opportunity_count: int = 0
    assigned_salesperson_name: str | None = None
    claim_record_id: str | None = None
    opportunity_id: str | None = None
    assignment_hint: str | None = None
    assignment_block_reason: str | None = None
    note: str | None = None


class PlmArrivalAssignmentRequest(BaseModel):
    salesperson_name: str

    model_config = {"extra": "forbid"}


class PlmArrivalAssignmentCloseRequest(BaseModel):
    reason: str

    model_config = {"extra": "forbid"}


class PendingListingTaskRead(BaseModel):
    task_key: str
    source_type: str
    business_period: str | None = None
    country: str | None = None
    site: str | None = None
    main_sku: str
    main_sku_name: str | None = None
    salesperson_name: str
    claim_record_ids: list[str]
    default_first_period_start: date
    requires_confirmation: bool = False
    reusable_listing_ids: list[str] = Field(default_factory=list)


class ListingRecordRead(BaseModel):
    id: str
    task_key: str
    main_sku: str
    main_sku_name: str | None = None
    image_url: str | None = None
    country: str | None = None
    site: str | None = None
    salesperson_name: str
    shop: str
    item: str
    listing_strategy: str
    first_period_start: date | None = None
    business_period: str | None = None
    source_business_periods: list[str] = Field(default_factory=list)
    status: str
    tracking_status: str
    first_round_completed_at: datetime | None = None
    is_shared_item: bool = False
    representative_rule: str | None = None
    representative_sub_sku: str | None = None
    is_history: bool = False
    bound_main_skus: list[str] = Field(default_factory=list)


class ObservationPeriodRead(BaseModel):
    id: str
    listing_record_id: str
    main_sku: str
    main_sku_name: str | None = None
    image_url: str | None = None
    country: str | None = None
    salesperson_name: str
    shop: str
    item: str
    week_number: int
    period_start: date | None = None
    period_end: date | None = None
    record_source: str = "platform"
    metrics_origin: str | None = None
    business_period: str | None = None
    status: str
    tracking_status: str
    order_count: int | None = None
    total_revenue: float | None = None
    gross_profit_amount: float | None = None
    gross_profit_rate: float | None = None
    product_positioning: str | None = None
    default_product_positioning: str | None = None
    optimization_action: str | None = None
    four_week_summary: str | None = None
    first_round_completed_at: datetime | None = None


class ListingWorkbenchRead(BaseModel):
    pending_listing_tasks: list[PendingListingTaskRead]
    available_business_periods: list[str] = Field(default_factory=list)
    listing_records: list[ListingRecordRead]
    period_rows: list[ObservationPeriodRead]


class DashboardCountsRead(BaseModel):
    waiting_listing: int = Field(ge=0)
    waiting_secondary_research: int = Field(ge=0)
    pending_review_periods: int = Field(ge=0)
    pending_claim_reviews: int = Field(ge=0)
    pending_not_claim_reviews: int = Field(ge=0)


class ListingBatchRow(BaseModel):
    shop: str
    item: str
    listing_strategy: str
    first_period_start: str


class ManualListingContext(BaseModel):
    main_sku: str
    main_sku_name: str | None = None
    country: str | None = None
    site: str | None = None
    salesperson_name: str
    business_period: str | None = None


class ListingProductDetailRequest(BaseModel):
    main_sku: str = Field(min_length=1, max_length=128)


class ListingBatchRequest(BaseModel):
    task_key: str
    rows: list[ListingBatchRow] = Field(default_factory=list)
    reuse_listing_ids: list[str] = Field(default_factory=list)
    manual_context: ManualListingContext | None = None


class ListingRecordUpdate(BaseModel):
    shop: str | None = None
    item: str | None = None
    listing_strategy: str | None = None
    first_period_start: str | None = None
    tracking_status: str | None = None
    status: str | None = None
    void_reason: str | None = None

    model_config = {"extra": "forbid"}


class ObservationPeriodCreate(BaseModel):
    period_start: str


class ObservationPeriodReviewRow(BaseModel):
    period_id: str
    product_positioning: str
    optimization_action: str
    four_week_summary: str | None = None


class ObservationPeriodReviewBatchRequest(BaseModel):
    rows: list[ObservationPeriodReviewRow] = Field(min_length=1)


class PlmArrivalItem(BaseModel):
    source_sheet: str | None = None
    source_row: int | None = None
    arrival_type: str
    product_name: str | None = None
    salesperson_name: str
    sub_sku: str | None = None
    main_sku: str | None = None
    country: str | None = None
    warehouse: str | None = None
    latest_storage_time: str | None = None
    first_listing_time: str | None = None
    available_quantity: float | None = None
    real_stock_quantity: float | None = None
    daily_sales: float | None = None


class PlmArrivalSalespersonSummary(BaseModel):
    salesperson_name: str
    new_arrival_count: int
    restock_count: int
    unknown_count: int
    total_count: int


class PlmArrivalPreviewRead(BaseModel):
    date: str
    bloc_name: str
    row_count: int
    new_arrival_count: int
    restock_count: int
    unknown_count: int
    by_salesperson: list[PlmArrivalSalespersonSummary]
    items: list[PlmArrivalItem]


class PlmArrivalProcessRequest(BaseModel):
    date: str
    source_file: str | None = None


class PlmArrivalMatchedResponsibilityRead(BaseModel):
    claim_record_id: str
    opportunity_id: str
    business_period: str | None = None
    salesperson_name: str | None = None
    site: str | None = None
    country: str | None = None
    main_sku: str
    sub_sku: str
    product_name: str | None = None


class PlmArrivalProcessRead(BaseModel):
    batch_id: str
    status: str
    row_count: int
    new_arrival_count: int
    restock_count: int
    unknown_count: int
    matched_count: int
    unmatched_count: int
    arrival_record_count: int
    planned_responsibilities: list[PlmArrivalMatchedResponsibilityRead] = Field(default_factory=list)


class NotificationTestRequest(BaseModel):
    receiver_name: str
    title: str
    dedupe_key: str
    channel: str = "work_notice"


class DingTalkNewProductTodoCardRequest(BaseModel):
    receiver_dingtalk_user_id: str = Field(min_length=1)
    receiver_name: str | None = None
    receiver_role: str
    subject_name: str | None = None
    left_count: int = Field(ge=0)
    right_count: int = Field(ge=0)
    action_url: str = Field(min_length=1)
    out_track_id: str = Field(min_length=1)
    dedupe_key: str | None = None
    card_title: str | None = None
    summary_text: str | None = None
    left_label: str | None = None
    right_label: str | None = None
    tip_text: str | None = None

    @field_validator("receiver_role")
    @classmethod
    def valid_receiver_role(cls, value: str) -> str:
        if value not in {"operator", "supervisor"}:
            raise ValueError("receiver_role must be operator or supervisor")
        return value


class DingTalkCardPreviewRequest(BaseModel):
    receiver_role: str
    subject_name: str | None = None
    left_count: int = Field(ge=0)
    right_count: int = Field(ge=0)
    action_url: str = Field(min_length=1)

    @field_validator("receiver_role")
    @classmethod
    def valid_receiver_role(cls, value: str) -> str:
        if value not in {"operator", "supervisor"}:
            raise ValueError("receiver_role must be operator or supervisor")
        return value


class DingTalkCardPreviewRead(DingTalkCardPreviewRequest):
    skipped: bool
    params: dict[str, str]


class NotificationRead(BaseModel):
    id: str
    dedupe_key: str
    receiver_name: str | None
    channel: str
    message_title: str
    send_status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class RoleMappingCreate(BaseModel):
    name: str
    role: str
    dingtalk_user_id: str | None = None
    group_name: str | None = None
    site: str | None = None
    manager_user_id: str | None = None
    notification_enabled: bool = True


class RoleMappingRead(RoleMappingCreate):
    id: str
    enabled: bool

    model_config = {"from_attributes": True}


class OperatorCategorySelection(BaseModel):
    level1: str
    level2: str | None = None

    @field_validator("level1")
    @classmethod
    def level1_required(cls, value: str) -> str:
        text = str(value).strip()
        if not text:
            raise ValueError("level1 is required")
        return text

    @field_validator("level2", mode="before")
    @classmethod
    def empty_level2_to_none(cls, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None


class CompanyCategoryImportRequest(BaseModel):
    source_file: str
    source_sheet: str = "公司类目"


class CompanyCategoryImportResponse(BaseModel):
    created_count: int
    updated_count: int
    skipped_count: int


class CompanyCategoryRead(BaseModel):
    id: str
    level1: str
    level2: str | None = None
    enabled: bool

    @field_validator("level2", mode="before")
    @classmethod
    def empty_level2_to_none(cls, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    model_config = {"from_attributes": True}


class OperatorAssignmentProfileCreate(BaseModel):
    operator_name: str
    key_site: str | None = None
    key_category1: str | None = None
    key_category2: str | None = None
    key_categories: list[OperatorCategorySelection] = Field(default_factory=list)

    @field_validator("key_categories", mode="before")
    @classmethod
    def empty_key_categories(cls, value: object) -> list[object]:
        return list(value or [])

    @field_validator("key_categories")
    @classmethod
    def key_categories_level1_limit(cls, value: list[OperatorCategorySelection]) -> list[OperatorCategorySelection]:
        level1_values = {item.level1.strip() for item in value if item.level1.strip()}
        if len(level1_values) > 6:
            raise ValueError("最多配置 6 个一级类目组")
        return value
    assignment_priority: int = 0
    display_order: int | None = None
    enabled: bool = True


class OperatorAssignmentProfileUpdate(BaseModel):
    operator_name: str | None = None
    key_site: str | None = None
    key_category1: str | None = None
    key_category2: str | None = None
    key_categories: list[OperatorCategorySelection] | None = None
    assignment_priority: int | None = None
    display_order: int | None = None
    enabled: bool | None = None

    @field_validator("key_categories")
    @classmethod
    def key_categories_level1_limit(cls, value: list[OperatorCategorySelection] | None) -> list[OperatorCategorySelection] | None:
        if value is None:
            return None
        level1_values = {item.level1.strip() for item in value if item.level1.strip()}
        if len(level1_values) > 6:
            raise ValueError("最多配置 6 个一级类目组")
        return value


class OperatorAssignmentProfileRead(OperatorAssignmentProfileCreate):
    id: str

    model_config = {"from_attributes": True}


class DisableRequest(BaseModel):
    disabled: bool
    reason: str | None = None


class MessageResponse(BaseModel):
    message: str
    id: str | None = None


class AssignableOperatorRead(BaseModel):
    id: str
    name: str


class AdminUserRead(UserRead):
    has_password: bool = False


class AdminUserCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    dingtalk_user_id: str | None = None
    password: str | None = Field(default=None, min_length=6)
    role: str = "operator"


class AdminUserUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    dingtalk_user_id: str | None = None
    role: str | None = None
    enabled: bool | None = None


class AdminPasswordResetRequest(BaseModel):
    new_password: str | None = Field(default=None, min_length=6)


class AdminPasswordResetResponse(BaseModel):
    status: str = "ok"
    password: str
    generated: bool


class RoleMappingUpdate(BaseModel):
    name: str | None = None
    role: str | None = None
    dingtalk_user_id: str | None = None
    group_name: str | None = None
    site: str | None = None
    manager_user_id: str | None = None
    enabled: bool | None = None
    notification_enabled: bool | None = None


class ImportBatchPage(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[ImportBatchSummary]


class FeatureSwitchRead(BaseModel):
    name: str
    enabled: bool


class FineBIPullRequest(BaseModel):
    week_label: str
