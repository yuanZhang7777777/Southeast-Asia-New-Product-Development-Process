from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


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
    auth_code: str
    dingtalk_user_id: str | None = None
    name: str = "本地测试用户"


class AuthLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead


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
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class OpportunityImportRequest(BaseModel):
    items: list[OpportunityCreate]


class AssignmentPreviewItem(BaseModel):
    main_sku: str
    sub_sku_count: int
    suggested_assignee: str | None


class AssignmentPreviewRequest(BaseModel):
    opportunity_ids: list[str]
    candidates: list[str]


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


class ReviewCreate(BaseModel):
    opportunity_id: str
    reviewer_name: str
    review_status: str
    review_comment: str | None = None


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


class MessageResponse(BaseModel):
    message: str
    id: str | None = None
