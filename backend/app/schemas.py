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
    name: str = "本地测试用户"


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
    latest_claim_result: str | None = None
    latest_claim_salesperson: str | None = None
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
    image_url: str | None = None
    edit_reason: str

    model_config = {"extra": "forbid"}


class Selection1ImportRequest(BaseModel):
    source_file: str | None = None
    source_sheet: str = "开发0623期"
    max_rows: int | None = None


class Selection1ImportResponse(BaseModel):
    import_batch_id: str | None = None
    source_file: str
    source_sheet: str
    imported_count: int
    created_count: int
    updated_count: int
    skipped_count: int
    market_research_count: int
    prefill_claim_count: int
    task_count: int


class Selection2ImportRequest(Selection1ImportRequest):
    source_sheet: str = "5.26期"


class Selection2ImportResponse(Selection1ImportResponse):
    pass


class ExcelSheetListResponse(BaseModel):
    sheets: list[str]
    default_sheet: str | None = None


class ImportBatchSummary(BaseModel):
    id: str
    source_type: str
    source_file: str | None
    source_sheet: str | None
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
    warehouse: str | None = None
    arrived_quantity: int | None = None
    arrived_at: datetime | None = None
    listing_status: str | None = None
    note: str | None = None


class ArrivalRecordRead(ArrivalRecordCreate):
    id: str
    created_at: datetime

    model_config = {"from_attributes": True}


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
    enabled: bool = True


class OperatorAssignmentProfileUpdate(BaseModel):
    operator_name: str | None = None
    key_site: str | None = None
    key_category1: str | None = None
    key_category2: str | None = None
    enabled: bool | None = None


class OperatorAssignmentProfileRead(OperatorAssignmentProfileCreate):
    id: str

    model_config = {"from_attributes": True}


class MessageResponse(BaseModel):
    message: str
    id: str | None = None
