export const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
const AUTH_TOKEN_KEY = "np_flow_auth_token";

export type Opportunity = {
  id: string;
  source_type?: string | null;
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
  latest_claim_result?: string | null;
  latest_claim_salesperson?: string | null;
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
  salesperson_name?: string | null;
  main_sku?: string | null;
  sub_sku?: string | null;
  daily_sales?: number | null;
  quantity: number;
  country?: string | null;
  warehouse?: string | null;
  status: string;
  created_at: string;
};

export type AvailableStockingItem = {
  opportunity_id: string;
  claim_record_id: string;
  operation_status: string;
  time: string;
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
  replenishment_reason?: string | null;
  needs_launch_email?: string | null;
  launch_email_status?: string | null;
  review_status?: string | null;
};

export type Selection1ImportResponse = {
  import_batch_id?: string | null;
  source_file: string;
  source_sheet: string;
  imported_count: number;
  created_count: number;
  updated_count: number;
  skipped_count: number;
  market_research_count: number;
  prefill_claim_count: number;
  task_count: number;
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

export type OperatorAssignmentProfile = {
  id: string;
  operator_name: string;
  key_site?: string | null;
  key_category1?: string | null;
  key_category2?: string | null;
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

async function download(path: string, fallbackName: string): Promise<void> {
  const token = getAuthToken();
  const response = await fetch(`${API_BASE}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {}
  });
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

type PeriodFilter = { source_sheet?: string; import_batch_id?: string };

function query(params: PeriodFilter = {}) {
  const search = new URLSearchParams();
  if (params.source_sheet) search.set("source_sheet", params.source_sheet);
  if (params.import_batch_id) search.set("import_batch_id", params.import_batch_id);
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
  opportunities: (limit = 5000, filter?: PeriodFilter) =>
    request<Opportunity[]>(`/opportunities?limit=${limit}${query(filter).replace("?", "&")}`),
  updateOpportunity: (id: string, payload: unknown) =>
    request<Opportunity>(`/opportunities/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  importOpportunities: (items: unknown[]) =>
    request<Opportunity[]>("/opportunities/import", { method: "POST", body: JSON.stringify({ items }) }),
  opportunitiesExport: (filter?: PeriodFilter) =>
    download(`/opportunities/export${query(filter)}`, "source-opportunities.xlsx"),
  importSelection1: (source_sheet = "开发0623期", source_file?: string) =>
    request<Selection1ImportResponse>("/opportunities/import/selection1", {
      method: "POST",
      body: JSON.stringify({ source_sheet, source_file: source_file || undefined })
    }),
  importSelection1File: (source_sheet: string, file: File) => {
    const form = new FormData();
    form.append("source_sheet", source_sheet);
    form.append("file", file);
    return request<Selection1ImportResponse>("/opportunities/import/selection1/upload", { method: "POST", body: form });
  },
  excelSheets: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<ExcelSheetListResponse>("/opportunities/excel-sheets/upload", { method: "POST", body: form });
  },
  importSelection2: (source_sheet = "5.26期", source_file?: string) =>
    request<Selection1ImportResponse>("/opportunities/import/selection2", {
      method: "POST",
      body: JSON.stringify({ source_sheet, source_file: source_file || undefined })
    }),
  importSelection2File: (source_sheet: string, file: File) => {
    const form = new FormData();
    form.append("source_sheet", source_sheet);
    form.append("file", file);
    return request<Selection1ImportResponse>("/opportunities/import/selection2/upload", { method: "POST", body: form });
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
  review: (payload: unknown) => request<{ message: string; id: string }>("/reviews", { method: "POST", body: JSON.stringify(payload) }),
  stocking: () => request<StockingRequest[]>("/stocking/requests"),
  availableStocking: (filter?: PeriodFilter) => request<AvailableStockingItem[]>(`/stocking/available-list${query(filter)}`),
  availableStockingExport: (filter?: PeriodFilter) => download(`/stocking/available-list/export${query(filter)}`, "海外仓备货申请表.xlsx"),
  traceabilityExport: (filter?: PeriodFilter) => download(`/stocking/traceability/export${query(filter)}`, "新品中央字段导出.xlsx"),
  arrival: (payload: unknown) => request<unknown>("/arrival/records", { method: "POST", body: JSON.stringify(payload) }),
  summary: (payload: unknown) => request<unknown>("/summary/four-week", { method: "POST", body: JSON.stringify(payload) }),
  notify: (payload: unknown) => request<NotificationLog>("/notifications/test", { method: "POST", body: JSON.stringify(payload) }),
  notifications: () => request<NotificationLog[]>("/notifications/logs"),
  roleMappings: () => request<RoleMapping[]>("/admin/role-mappings"),
  createRoleMapping: (payload: unknown) =>
    request<RoleMapping>("/admin/role-mappings", { method: "POST", body: JSON.stringify(payload) }),
  operatorProfiles: () => request<OperatorAssignmentProfile[]>("/admin/operator-profiles"),
  createOperatorProfile: (payload: unknown) =>
    request<OperatorAssignmentProfile>("/admin/operator-profiles", { method: "POST", body: JSON.stringify(payload) }),
  updateOperatorProfile: (id: string, payload: unknown) =>
    request<OperatorAssignmentProfile>(`/admin/operator-profiles/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteOperatorProfile: (id: string) => request<void>(`/admin/operator-profiles/${id}`, { method: "DELETE" })
};
