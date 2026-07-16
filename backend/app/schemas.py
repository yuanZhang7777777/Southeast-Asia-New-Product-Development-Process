from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


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


class OpportunityCreate(BaseModel):
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
    keyword: str | None = None
    image_url: str | None = None
    main_sku_name: str | None = None
    main_sku: str
    sub_sku_name: str | None = None
    sub_sku: str
    product_type: str | None = None
    reason: str | None = None
    snapshot: dict[str, Any] = Field(default_factory=dict)


class OpportunityRead(OpportunityCreate):
    id: str
    current_status: str
    latest_claim_record_id: str | None = None
    latest_claim_result: str | None = None
    latest_claim_salesperson: str | None = None
    latest_claim_daily_sales: float | None = None
    latest_reject_reason: str | None = None
    latest_feedback_summary: str | None = None
    latest_claim_note: str | None = None
    latest_review_status: str | None = None
    latest_review_comment: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


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

    model_config = {"from_attributes": True}


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
    salesperson_name: str | None = None
    daily_sales: float
    country: str | None = None
    warehouse: str | None = None
    reason: str | None = None


class StockingRequestRead(BaseModel):
    id: str
    opportunity_id: str
    salesperson_name: str | None
    main_sku: str | None
    sub_sku: str | None
    daily_sales: float | None
    quantity: int
    country: str | None
    warehouse: str | None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AvailableStockingItem(BaseModel):
    opportunity_id: str
    claim_record_id: str
    operation_status: str = "未操作"
    time: datetime
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
    replenishment_reason: str | None = None
    needs_launch_email: str | None = None
    launch_email_status: str | None = None
    review_status: str | None = None


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
    secondary_research_at: datetime | None = None
    secondary_competitor_url: str | None = None
    secondary_conclusion: str | None = None
    product_positioning: str | None = None
    secondary_research_submitted_at: datetime | None = None


class SecondaryResearchItemRead(BaseModel):
    claim_record_id: str
    opportunity_id: str
    salesperson_name: str
    downstream_status: str
    arrival_detected_at: datetime | None = None
    secondary_research_at: datetime | None = None
    secondary_competitor_url: str | None = None
    secondary_conclusion: str | None = None
    product_positioning: str | None = None
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
    secondary_evidence_images: list[dict[str, Any]] | None = None

    model_config = {"extra": "forbid"}

    @field_validator("product_positioning")
    @classmethod
    def valid_product_positioning(cls, value: str | None) -> str | None:
        if value is not None and value not in {"引流款", "利润款", "淘汰款"}:
            raise ValueError("product_positioning must be 引流款, 利润款, or 淘汰款")
        return value


class SecondaryResearchSubmitGroupRequest(BaseModel):
    claim_record_ids: list[str] = Field(min_length=1)


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


class FourWeekSummaryCreate(BaseModel):
    opportunity_id: str
    summary_user: str | None = None
    achieved: bool | None = None
    out_of_stock_impact: str | None = None
    conclusion: str | None = None
    next_action: str | None = None


class FourWeekSummaryRead(FourWeekSummaryCreate):
    id: str
    created_at: datetime

    model_config = {"from_attributes": True}


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


class RoleMappingRead(RoleMappingCreate):
    id: str
    enabled: bool

    model_config = {"from_attributes": True}


class OperatorAssignmentProfileCreate(BaseModel):
    operator_name: str
    key_site: str | None = None
    key_category1: str | None = None
    key_category2: str | None = None
    assignment_priority: int = 0
    display_order: int | None = None
    enabled: bool = True


class OperatorAssignmentProfileUpdate(BaseModel):
    operator_name: str | None = None
    key_site: str | None = None
    key_category1: str | None = None
    key_category2: str | None = None
    assignment_priority: int | None = None
    display_order: int | None = None
    enabled: bool | None = None


class OperatorAssignmentProfileRead(OperatorAssignmentProfileCreate):
    id: str

    model_config = {"from_attributes": True}


class DisableRequest(BaseModel):
    disabled: bool
    reason: str | None = None


class MessageResponse(BaseModel):
    message: str
    id: str | None = None
