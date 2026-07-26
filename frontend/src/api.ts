export const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
const AUTH_TOKEN_KEY = "np_flow_auth_token";

export type Opportunity = {
  id: string;
  source_type?: string | null;
  batch?: string | null;
  country?: string | null;
  site?: string | null;
  developer_department?: string | null;
  developer_name?: string | null;
  category_level1?: string | null;
  main_sku: string;
  main_sku_name?: string | null;
  sub_sku: string;
  sub_sku_name?: string | null;
  product_type?: string | null;
  keyword?: string | null;
  image_url?: string | null;
  reason?: string | null;
  current_status: string;
  latest_claim_record_id?: string | null;
  latest_claim_result?: string | null;
  latest_claim_salesperson?: string | null;
  latest_claim_daily_sales?: number | null;
  latest_reject_reason?: string | null;
  latest_feedback_summary?: string | null;
  latest_claim_note?: string | null;
  latest_review_status?: string | null;
  latest_review_comment?: string | null;
  source_file?: string | null;
  source_sheet?: string | null;
  source_row?: number | null;
  snapshot?: Record<string, unknown>;
  created_at: string;
};

export type Task = {
  id: string;
  node_code: string;
  task_type: string;
  opportunity_id?: string | null;
  assignee_name?: string | null;
  assignee_role?: string | null;
  status: string;
  deadline_at?: string | null;
};

export type StockingRequest = {
  id: string;
  opportunity_id: string;
  claim_record_id?: string | null;
  application_date?: string | null;
  submitted_at?: string | null;
  request_type: "initial" | "replenishment";
  unit_volume_source?: "erp" | "manual" | null;
  salesperson_name?: string | null;
  main_sku?: string | null;
  sub_sku?: string | null;
  cost_price?: number | null;
  length_cm?: number | null;
  width_cm?: number | null;
  height_cm?: number | null;
  unit_volume?: number | null;
  daily_sales?: number | null;
  quantity: number;
  country?: string | null;
  warehouse?: string | null;
  amount?: number | null;
  volume?: number | null;
  reason?: string | null;
  status: string;
  created_at: string;
};

export type OperatorStockingItem = {
  opportunity_id: string;
  claim_record_id: string;
  request_id?: string | null;
  business_period?: string | null;
  country: string | null;
  source_type: string;
  salesperson_name: string;
  main_sku: string;
  main_sku_name?: string | null;
  sub_sku: string;
  sub_sku_name?: string | null;
  inventory_available?: boolean | null;
  needs_stocking?: boolean | null;
  downstream_status: string;
  request?: StockingRequest | null;
};

export type StockingRequestUpdate = {
  application_date?: string | null;
  request_type?: "initial" | "replenishment";
  cost_price?: number | null;
  length_cm?: number | null;
  width_cm?: number | null;
  height_cm?: number | null;
  unit_volume?: number | null;
  unit_volume_source?: "erp" | "manual" | null;
  daily_sales?: number | null;
  country?: string | null;
  warehouse?: string | null;
  reason?: string | null;
};

export type SalesSelfSelectionPayload = {
  main_sku: string;
  main_sku_name?: string | null;
  country: string;
  children: Array<{
    sub_sku: string;
    sub_sku_name?: string | null;
    inventory_available: boolean;
    needs_stocking: boolean;
  }>;
};

export type VolumePreviewItem = {
  sub_sku: string;
  unit_volume?: number | null;
  status: "resolved" | "manual_required";
};

export type AvailableStockingItem = {
  opportunity_id: string;
  request_id: string;
  claim_record_id: string;
  business_period?: string | null;
  operation_status: string;
  time?: string | null;
  application_date?: string | null;
  stocking_type: string;
  selection_source: string;
  salesperson_name?: string | null;
  main_sku: string;
  sub_sku: string;
  site?: string | null;
  claim_daily_sales: number;
  quantity: number;
  stocking_country?: string | null;
  warehouse?: string | null;
  cost_price?: number | null;
  unit_volume?: number | null;
  amount?: number | null;
  volume?: number | null;
  replenishment_reason?: string | null;
  needs_launch_email?: string | null;
  launch_email_status?: string | null;
  review_status?: string | null;
  status: string;
};
export type ExportPeriodSummary = {
  business_period: string;
  latest_imported_at?: string | null;
  stocking_count: number;
  traceability_count: number;
};

export type PlmArrivalItem = {
  arrival_type: "new_arrival" | "restock" | "unknown";
  salesperson_name: string;
  sub_sku?: string | null;
  main_sku?: string | null;
  country?: string | null;
  warehouse?: string | null;
  latest_storage_time?: string | null;
  first_listing_time?: string | null;
  available_quantity?: number | null;
  real_stock_quantity?: number | null;
  daily_sales?: number | null;
};

export type PlmArrivalSalespersonSummary = {
  salesperson_name: string;
  new_arrival_count: number;
  restock_count: number;
  unknown_count: number;
  total_count: number;
};

export type PlmArrivalPreview = {
  date: string;
  bloc_name: string;
  row_count: number;
  new_arrival_count: number;
  restock_count: number;
  unknown_count: number;
  by_salesperson: PlmArrivalSalespersonSummary[];
  items: PlmArrivalItem[];
};

export type Selection1ImportResponse = {
  import_batch_id?: string | null;
  source_file: string;
  source_sheet: string;
  business_period?: string | null;
  imported_count: number;
  created_count: number;
  updated_count: number;
  skipped_count: number;
  market_research_count: number;
  prefill_claim_count: number;
  task_count: number;
};

export type Selection2ImportResponse = Selection1ImportResponse;

export type ImportBatchSummary = {
  id: string;
  source_type: string;
  source_file?: string | null;
  source_sheet?: string | null;
  business_period?: string | null;
  imported_by?: string | null;
  imported_at?: string | null;
  created_count: number;
  updated_count: number;
  skipped_count: number;
  status: string;
};

export type ExcelSheetListResponse = {
  sheets: string[];
  default_sheet?: string | null;
};

export type AssignmentPreviewItem = {
  main_sku: string;
  sub_sku_count: number;
  suggested_assignee?: string | null;
  match_reason?: string | null;
  opportunity_ids: string[];
};

export type NotificationLog = {
  id: string;
  dedupe_key: string;
  receiver_name?: string | null;
  channel: string;
  message_title: string;
  send_status: string;
  created_at: string;
};

export type RoleMapping = {
  id: string;
  name: string;
  role: string;
  dingtalk_user_id?: string | null;
  group_name?: string | null;
  site?: string | null;
  manager_user_id?: string | null;
  enabled: boolean;
};

export type AdminUser = {
  id: string;
  dingtalk_user_id?: string | null;
  name: string;
  enabled: boolean;
  has_password: boolean;
};

export type AdminPasswordReset = {
  status: string;
  password: string;
  generated: boolean;
};

export type ImportBatchPage = {
  total: number;
  page: number;
  page_size: number;
  items: ImportBatchSummary[];
};

export type AdminImportBatchFilter = {
  page?: number;
  page_size?: number;
  source_type?: string;
  business_period?: string;
  status?: string;
};

export type FeatureSwitch = {
  name: string;
  enabled: boolean;
};

export type OperatorCategorySelection = {
  level1: string;
  level2?: string | null;
};

export type CompanyCategory = {
  id: string;
  level1: string;
  level2?: string | null;
  enabled: boolean;
};

export type OperatorAssignmentProfile = {
  id: string;
  operator_name: string;
  key_site?: string | null;
  key_category1?: string | null;
  key_category2?: string | null;
  key_categories?: OperatorCategorySelection[] | null;
  assignment_priority: number;
  display_order?: number | null;
  enabled: boolean;
};

export type AuthRole = {
  role: "operator" | "manager" | "super_admin";
  name: string;
};

export type AuthSession = {
  access_token: string;
  token_type: string;
  user: {
    id: string;
    dingtalk_user_id?: string | null;
    name: string;
    enabled: boolean;
  };
  roles: AuthRole[];
  default_role: "operator" | "manager";
  operator_name?: string | null;
};

export type UploadedEvidenceImage = {
  name: string;
  type: string;
  size: number;
  url: string;
};

export type SecondaryResearchPeer = {
  claim_record_id: string;
  salesperson_name?: string | null;
  secondary_research_at?: string | null;
  secondary_competitor_url?: string | null;
  secondary_conclusion?: string | null;
  product_positioning?: string | null;
  secondary_target_daily_sales?: number | null;
  secondary_selling_points?: string | null;
  secondary_research_submitted_at?: string | null;
};

export type SecondaryResearchItem = {
  claim_record_id: string;
  opportunity_id: string;
  salesperson_name: string;
  downstream_status: string;
  arrival_detected_at?: string | null;
  secondary_research_at?: string | null;
  secondary_competitor_url?: string | null;
  secondary_conclusion?: string | null;
  product_positioning?: string | null;
  secondary_target_daily_sales?: number | null;
  secondary_selling_points?: string | null;
  secondary_evidence_images: UploadedEvidenceImage[];
  secondary_research_submitted_at?: string | null;
  sub_sku: string;
  sub_sku_name?: string | null;
  image_url?: string | null;
  reason?: string | null;
  snapshot: Record<string, unknown>;
  peer_records: SecondaryResearchPeer[];
};

export type SecondaryResearchGroup = {
  key: string;
  source_type: string;
  business_period?: string | null;
  site?: string | null;
  country?: string | null;
  main_sku: string;
  main_sku_name?: string | null;
  salesperson_name: string;
  items: SecondaryResearchItem[];
};

export type ProductBoardChildSku = {
  opportunity_id: string;
  sub_sku: string;
  sub_sku_name?: string | null;
  visible_status: string;
};

export type ProductBoardResponsibility = {
  claim_record_id?: string | null;
  task_id?: string | null;
  opportunity_id: string;
  salesperson_name?: string | null;
  sub_sku: string;
  claim_daily_sales?: number | null;
  visible_status: string;
  arrival_detected_at?: string | null;
};

export type ProductBoardGroup = {
  key: string;
  business_period?: string | null;
  site?: string | null;
  country?: string | null;
  main_sku: string;
  main_sku_name?: string | null;
  image_url?: string | null;
  child_skus: ProductBoardChildSku[];
  responsibilities: ProductBoardResponsibility[];
  summary_tags: string[];
};

export type ProductBoardFilter = {
  owner?: string;
  business_period?: string;
  visible_status?: string;
  arrival_date_from?: string;
  arrival_date_to?: string;
  site?: string;
  query?: string;
};

export type DashboardCounts = {
  waiting_listing: number;
  waiting_secondary_research: number;
  pending_review_periods: number;
};

export type ListingWorkbenchView = "pending_listing" | "pending_data" | "pending_review" | "first_round_completed" | "all";
export type ObservationPeriodStatus = "pending_data" | "pending_review" | "completed";
export type ListingTrackingStatus = "active" | "stopped";
export type ProductPositioning = "引流款" | "利润款" | "淘汰款" | "稳定款" | "清仓款";

export type PendingListingTask = {
  task_key: string;
  source_type: string;
  business_period?: string | null;
  country?: string | null;
  site?: string | null;
  main_sku: string;
  main_sku_name?: string | null;
  salesperson_name: string;
  claim_record_ids: string[];
  default_first_period_start: string;
  requires_confirmation: boolean;
  reusable_listing_ids: string[];
};

export type ListingRecord = {
  id: string;
  task_key: string;
  main_sku: string;
  main_sku_name?: string | null;
  country?: string | null;
  site?: string | null;
  salesperson_name: string;
  shop: string;
  item: string;
  listing_strategy: string;
  first_period_start: string;
  business_period?: string | null;
  source_business_periods: string[];
  status: "active" | "voided";
  tracking_status: ListingTrackingStatus;
  first_round_completed_at?: string | null;
  is_shared_item?: boolean;
  is_history?: boolean;
  bound_main_skus?: string[];
};

export type ObservationPeriodRow = {
  id: string;
  listing_record_id: string;
  main_sku: string;
  main_sku_name?: string | null;
  country?: string | null;
  salesperson_name: string;
  shop: string;
  item: string;
  week_number: number;
  period_start: string;
  period_end: string;
  business_period?: string | null;
  status: ObservationPeriodStatus;
  tracking_status: ListingTrackingStatus;
  order_count?: number | null;
  total_revenue?: number | null;
  gross_profit_amount?: number | null;
  gross_profit_rate?: number | null;
  product_positioning?: ProductPositioning | null;
  default_product_positioning?: ProductPositioning | null;
  optimization_action?: string | null;
  four_week_summary?: string | null;
  first_round_completed_at?: string | null;
};

export type ListingWorkbenchResponse = {
  pending_listing_tasks: PendingListingTask[];
  available_business_periods?: string[];
  listing_records: ListingRecord[];
  period_rows: ObservationPeriodRow[];
};

export type ListingWorkbenchFilter = {
  view?: ListingWorkbenchView;
  query?: string;
  period_start?: string;
  country?: string;
  shop?: string;
  salesperson_name?: string;
  status?: ObservationPeriodStatus | "";
  week_number?: number | "";
  product_positioning?: ProductPositioning | "";
  tracking_status?: ListingTrackingStatus | "";
  only_my_tasks?: boolean;
  include_history?: boolean;
  business_period?: string;
};

export type ManualListingContext = {
  main_sku: string;
  main_sku_name?: string | null;
  country?: string | null;
  site?: string | null;
  salesperson_name: string;
  business_period?: string | null;
};

export type ListingBatchPayload = {
  task_key: string;
  rows: Array<{ shop: string; item: string; listing_strategy: string; first_period_start: string }>;
  reuse_listing_ids?: string[];
  manual_context?: ManualListingContext;
};

export type PeriodReviewBatchPayload = {
  rows: Array<{
    period_id: string;
    product_positioning: ProductPositioning;
    optimization_action: string;
    four_week_summary?: string | null;
  }>;
};

export function getAuthToken() {
  return localStorage.getItem(AUTH_TOKEN_KEY) || "";
}

export function setAuthToken(token: string) {
  if (token) localStorage.setItem(AUTH_TOKEN_KEY, token);
  else localStorage.removeItem(AUTH_TOKEN_KEY);
}

export class ApiAuthError extends Error {}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const isFormData = options.body instanceof FormData;
  const headers: Record<string, string> = {};
  if (!isFormData) headers["Content-Type"] = "application/json";
  const token = getAuthToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { ...headers, ...(options.headers as Record<string, string> | undefined) },
    ...options
  });
  if (!response.ok) {
    const message = await response.text();
    if (response.status === 401 || response.status === 403) {
      throw new ApiAuthError(message || `${response.status} ${response.statusText}`);
    }
    throw new Error(message || `${response.status} ${response.statusText}`);
  }
  const text = await response.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

async function download(path: string, fallbackName: string, options: RequestInit = {}): Promise<void> {
  const token = getAuthToken();
  const headers: Record<string, string> = options.body ? { "Content-Type": "application/json" } : {};
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!response.ok) {
    const message = await response.text();
    if (response.status === 401 || response.status === 403) {
      throw new ApiAuthError(message || `${response.status} ${response.statusText}`);
    }
    throw new Error(message || `${response.status} ${response.statusText}`);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filenameFromDisposition(response.headers.get("Content-Disposition"), fallbackName);
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function filenameFromDisposition(disposition: string | null, fallbackName: string) {
  const encoded = disposition?.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  if (!encoded) return fallbackName;
  try {
    return decodeURIComponent(encoded);
  } catch {
    return fallbackName;
  }
}

type PeriodFilter = { business_period?: string; source_sheet?: string; import_batch_id?: string };

function query(params: Record<string, string | number | boolean | null | undefined> = {}) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
  }
  const value = search.toString();
  return value ? `?${value}` : "";
}

function secondaryResearchQuery(
  salespersonName: string,
  businessPeriod: string,
  downstreamStatus = "waiting_secondary_research"
) {
  const search = new URLSearchParams();
  if (salespersonName) search.set("salesperson_name", salespersonName);
  if (businessPeriod) search.set("business_period", businessPeriod);
  search.set("downstream_status", downstreamStatus);
  const value = search.toString();
  return value ? `?${value}` : "";
}

function productBoardQuery(params: ProductBoardFilter = {}) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value) search.set(key, value);
  }
  const value = search.toString();
  return value ? `?${value}` : "";
}

function listingWorkbenchQuery(params: ListingWorkbenchFilter = {}) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
  }
  const value = search.toString();
  return value ? `?${value}` : "";
}

export const api = {
  health: () => request<{ status: string; environment: string }>("/health"),
  login: (payload: { name: string; password: string }) =>
    request<AuthSession>("/auth/login", { method: "POST", body: JSON.stringify(payload) }),
  dingtalkLogin: (payload: { auth_code?: string; dingtalk_user_id?: string; name?: string }) =>
    request<AuthSession>("/auth/dingtalk/login", { method: "POST", body: JSON.stringify(payload) }),
  me: () => request<AuthSession>("/auth/me"),
  changePassword: (payload: { old_password: string; new_password: string }) =>
    request<{ status: string }>("/auth/password", { method: "POST", body: JSON.stringify(payload) }),
  opportunities: (limit = 5000, filter?: PeriodFilter, includeDisabled = false) =>
    request<Opportunity[]>(`/opportunities?limit=${limit}${query(filter).replace("?", "&")}${includeDisabled ? "&include_disabled=true" : ""}`),
  updateOpportunity: (id: string, payload: unknown) =>
    request<Opportunity>(`/opportunities/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  disableOpportunity: (id: string, payload: { disabled: boolean; reason?: string | null }) =>
    request<{ message: string; id?: string | null }>(`/opportunities/${id}/disable`, { method: "POST", body: JSON.stringify(payload) }),
  disableOpportunityGroup: (id: string, payload: { disabled: boolean; reason?: string | null }) =>
    request<{ message: string; id?: string | null }>(`/opportunities/${id}/disable-group`, { method: "POST", body: JSON.stringify(payload) }),
  importBatches: () => request<ImportBatchSummary[]>("/opportunities/import-batches"),
  disableImportBatch: (id: string, payload: { disabled: boolean; reason?: string | null }) =>
    request<{ message: string; id?: string | null }>(`/opportunities/import-batches/${id}/disable`, { method: "POST", body: JSON.stringify(payload) }),
  importOpportunities: (items: unknown[]) =>
    request<Opportunity[]>("/opportunities/import", { method: "POST", body: JSON.stringify({ items }) }),
  opportunitiesExport: (filter?: PeriodFilter) =>
    download(`/opportunities/export${query(filter)}`, "source-opportunities.xlsx"),
  importSelection1: (source_sheet = "开发0623期", business_period?: string, source_file?: string) =>
    request<Selection1ImportResponse>("/opportunities/import/selection1", {
      method: "POST",
      body: JSON.stringify({ source_sheet, business_period: business_period || undefined, source_file: source_file || undefined })
    }),
  importSelection1File: (source_sheet: string, business_period: string, file: File) => {
    const form = new FormData();
    form.append("source_sheet", source_sheet);
    form.append("business_period", business_period);
    form.append("file", file);
    return request<Selection1ImportResponse>("/opportunities/import/selection1/upload", { method: "POST", body: form });
  },
  excelSheets: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<ExcelSheetListResponse>("/opportunities/excel-sheets/upload", { method: "POST", body: form });
  },
  importSelection2: (source_sheet = "5.26期", source_file?: string) =>
    request<Selection2ImportResponse>("/opportunities/import/selection2", {
      method: "POST",
      body: JSON.stringify({ source_sheet, source_file: source_file || undefined })
    }),
  importSelection2File: (source_sheet: string, file: File) => {
    const form = new FormData();
    form.append("source_sheet", source_sheet);
    form.append("file", file);
    return request<Selection2ImportResponse>("/opportunities/import/selection2/upload", { method: "POST", body: form });
  },
  assignmentPreview: (opportunity_ids: string[], candidates: string[]) =>
    request<{ items: AssignmentPreviewItem[] }>("/assignments/preview", {
      method: "POST",
      body: JSON.stringify({ opportunity_ids, candidates })
    }),
  assignmentConfirm: (opportunity_ids: string[], assignee_name: string) =>
    request<Task[]>("/assignments/confirm", { method: "POST", body: JSON.stringify({ opportunity_ids, assignee_name }) }),
  tasks: (assigneeName = "") => request<Task[]>(`/tasks/my${assigneeName ? `?assignee_name=${encodeURIComponent(assigneeName)}` : ""}`),
  claim: (payload: unknown) => request<{ message: string; id: string }>("/claims", { method: "POST", body: JSON.stringify(payload) }),
  uploadClaimEvidence: (opportunityId: string, file: File) => {
    const form = new FormData();
    form.append("opportunity_id", opportunityId);
    form.append("file", file);
    return request<UploadedEvidenceImage>("/claims/evidence-images", { method: "POST", body: form });
  },
  secondaryResearch: (salespersonName = "", businessPeriod = "", downstreamStatus = "waiting_secondary_research") =>
    request<SecondaryResearchGroup[]>(
      `/secondary-research${secondaryResearchQuery(salespersonName, businessPeriod, downstreamStatus)}`
    ),
  secondaryResearchExport: (filter?: { scenario?: string; salesperson_name?: string; business_period?: string; country?: string; query?: string }) =>
    download(`/secondary-research/export${query(filter)}`, "二次调研导出.xlsx"),
  productBoard: (filter?: ProductBoardFilter) => request<ProductBoardGroup[]>(`/product-board${productBoardQuery(filter)}`),
  dashboardCounts: (salespersonName = "") =>
    request<DashboardCounts>(`/dashboard/counts${query({ salesperson_name: salespersonName })}`),
  updateSecondaryResearch: (claimRecordId: string, salespersonName: string, payload: unknown) =>
    request<SecondaryResearchItem>(
      `/secondary-research/${claimRecordId}?salesperson_name=${encodeURIComponent(salespersonName)}`,
      { method: "PATCH", body: JSON.stringify(payload) }
    ),
  correctSecondaryResearch: (claimRecordId: string, salespersonName: string, payload: unknown) =>
    request<SecondaryResearchItem>(
      `/secondary-research/${claimRecordId}/correction?salesperson_name=${encodeURIComponent(salespersonName)}`,
      { method: "PATCH", body: JSON.stringify(payload) }
    ),
  submitSecondaryResearchGroup: (salespersonName: string, claimRecordIds: string[]) =>
    request<SecondaryResearchItem[]>(
      `/secondary-research/submit-group?salesperson_name=${encodeURIComponent(salespersonName)}`,
      { method: "POST", body: JSON.stringify({ claim_record_ids: claimRecordIds }) }
    ),
  review: (payload: unknown) => request<{ message: string; id: string }>("/reviews", { method: "POST", body: JSON.stringify(payload) }),
  bulkReview: (payload: unknown) => request<{ message: string; id: string }>("/reviews/bulk", { method: "POST", body: JSON.stringify(payload) }),
  stocking: () => request<StockingRequest[]>("/stocking/requests"),
  myStockingRequests: () => request<OperatorStockingItem[]>("/stocking/my-requests"),
  createSalesSelfSelection: (payload: SalesSelfSelectionPayload) =>
    request<OperatorStockingItem[]>("/stocking/self-selections", { method: "POST", body: JSON.stringify(payload) }),
  updateStockingRequest: (requestId: string, payload: StockingRequestUpdate) =>
    request<StockingRequest>(`/stocking/requests/${requestId}`, { method: "PUT", body: JSON.stringify(payload) }),
  submitStockingRequest: (requestId: string) =>
    request<StockingRequest>(`/stocking/requests/${requestId}/submit`, { method: "POST" }),
  updateStockingDecision: (claimRecordId: string, payload: { inventory_available: boolean; needs_stocking: boolean }) =>
    request<OperatorStockingItem>(`/stocking/decisions/${claimRecordId}`, { method: "POST", body: JSON.stringify(payload) }),
  volumePreview: (skus: string[]) =>
    request<VolumePreviewItem[]>("/stocking/volume-preview", { method: "POST", body: JSON.stringify({ skus }) }),
  availableStocking: (filter?: PeriodFilter) => request<AvailableStockingItem[]>(`/stocking/available-list${query(filter)}`),
  exportPeriods: () => request<ExportPeriodSummary[]>("/stocking/export-periods"),
  availableStockingExport: (payload: { request_ids: string[] }) =>
    download("/stocking/available-list/export", "海外仓备货申请表.xlsx", { method: "POST", body: JSON.stringify(payload) }),
  traceabilityExport: (filter?: PeriodFilter) => download(`/stocking/traceability/export${query(filter)}`, "新品中央字段导出.xlsx"),
  arrival: (payload: unknown) => request<unknown>("/arrival/records", { method: "POST", body: JSON.stringify(payload) }),
  plmArrivalPreview: (date: string) => request<PlmArrivalPreview>(`/arrival/plm-preview?date=${encodeURIComponent(date)}`),
  listingWorkbench: (filters: ListingWorkbenchFilter = {}) =>
    request<ListingWorkbenchResponse>(`/listing-workbench${listingWorkbenchQuery(filters)}`),
  listingSummary: (mainSku: string, country?: string | null, salespersonName?: string) => {
    const search = new URLSearchParams({ main_sku: mainSku });
    if (country) search.set("country", country);
    if (salespersonName) search.set("salesperson_name", salespersonName);
    return request<ListingWorkbenchResponse>(`/listing-workbench/summary?${search.toString()}`);
  },
  createListingsBatch: (payload: ListingBatchPayload) =>
    request<ListingRecord[]>("/listing-workbench/listings/batch", { method: "POST", body: JSON.stringify(payload) }),
  updateListing: (id: string, payload: unknown) =>
    request<ListingRecord>(`/listing-workbench/listings/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  addListingPeriod: (id: string, payload: { period_start: string }) =>
    request<ObservationPeriodRow>(`/listing-workbench/listings/${id}/periods`, { method: "POST", body: JSON.stringify(payload) }),
  reviewListingPeriods: (payload: PeriodReviewBatchPayload) =>
    request<ObservationPeriodRow[]>("/listing-workbench/periods/review-batch", { method: "POST", body: JSON.stringify(payload) }),
  notify: (payload: unknown) => request<NotificationLog>("/notifications/test", { method: "POST", body: JSON.stringify(payload) }),
  notifications: () => request<NotificationLog[]>("/notifications/logs"),
  roleMappings: () => request<RoleMapping[]>("/admin/role-mappings"),
  createRoleMapping: (payload: unknown) =>
    request<RoleMapping>("/admin/role-mappings", { method: "POST", body: JSON.stringify(payload) }),
  companyCategories: () => request<CompanyCategory[]>("/admin/company-categories"),
  operatorProfiles: () => request<OperatorAssignmentProfile[]>("/admin/operator-profiles"),
  createOperatorProfile: (payload: unknown) =>
    request<OperatorAssignmentProfile>("/admin/operator-profiles", { method: "POST", body: JSON.stringify(payload) }),
  updateOperatorProfile: (id: string, payload: unknown) =>
    request<OperatorAssignmentProfile>(`/admin/operator-profiles/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteOperatorProfile: (id: string) => request<void>(`/admin/operator-profiles/${id}`, { method: "DELETE" }),
  adminUsers: () => request<AdminUser[]>("/admin/users"),
  adminSetUserEnabled: (id: string, enabled: boolean) =>
    request<{ id: string; name: string; enabled: boolean }>(`/admin/users/${id}`, { method: "PATCH", body: JSON.stringify({ enabled }) }),
  adminResetUserPassword: (id: string, newPassword?: string) =>
    request<AdminPasswordReset>(`/admin/users/${id}/reset-password`, {
      method: "POST",
      body: JSON.stringify({ new_password: newPassword || null })
    }),
  updateRoleMapping: (id: string, payload: { role?: string; enabled?: boolean }) =>
    request<RoleMapping>(`/admin/role-mappings/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  adminImportBatches: (filter: AdminImportBatchFilter = {}) =>
    request<ImportBatchPage>(`/admin/import-batches${query(filter)}`),
  adminDisableImportBatch: (id: string, payload: { disabled: boolean; reason?: string | null }) =>
    request<{ message: string; id?: string | null }>(`/admin/import-batches/${id}/disable`, { method: "POST", body: JSON.stringify(payload) }),
  adminFeatureSwitches: () => request<FeatureSwitch[]>("/admin/feature-switches")
};
