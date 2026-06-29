const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export type Opportunity = {
  id: string;
  country?: string | null;
  site?: string | null;
  main_sku: string;
  sub_sku: string;
  keyword?: string | null;
  current_status: string;
  source_file?: string | null;
  source_sheet?: string | null;
  source_row?: number | null;
  created_at: string;
};

export type Task = {
  id: string;
  node_code: string;
  task_type: string;
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

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...options.headers },
    ...options
  });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  health: () => request<{ status: string; environment: string }>("/health"),
  opportunities: () => request<Opportunity[]>("/opportunities"),
  importOpportunities: (items: unknown[]) =>
    request<Opportunity[]>("/opportunities/import", { method: "POST", body: JSON.stringify({ items }) }),
  assignmentPreview: (opportunity_ids: string[], candidates: string[]) =>
    request<{ items: { main_sku: string; sub_sku_count: number; suggested_assignee?: string | null }[] }>(
      "/assignments/preview",
      { method: "POST", body: JSON.stringify({ opportunity_ids, candidates }) }
    ),
  assignmentConfirm: (opportunity_ids: string[], assignee_name: string) =>
    request<Task[]>("/assignments/confirm", { method: "POST", body: JSON.stringify({ opportunity_ids, assignee_name }) }),
  tasks: (assigneeName = "") => request<Task[]>(`/tasks/my${assigneeName ? `?assignee_name=${encodeURIComponent(assigneeName)}` : ""}`),
  claim: (payload: unknown) => request<{ message: string; id: string }>("/claims", { method: "POST", body: JSON.stringify(payload) }),
  review: (payload: unknown) => request<{ message: string; id: string }>("/reviews", { method: "POST", body: JSON.stringify(payload) }),
  stocking: () => request<StockingRequest[]>("/stocking/requests"),
  arrival: (payload: unknown) => request<unknown>("/arrival/records", { method: "POST", body: JSON.stringify(payload) }),
  summary: (payload: unknown) => request<unknown>("/summary/four-week", { method: "POST", body: JSON.stringify(payload) }),
  notify: (payload: unknown) => request<NotificationLog>("/notifications/test", { method: "POST", body: JSON.stringify(payload) }),
  notifications: () => request<NotificationLog[]>("/notifications/logs"),
  roleMappings: () => request<RoleMapping[]>("/admin/role-mappings"),
  createRoleMapping: (payload: unknown) =>
    request<RoleMapping>("/admin/role-mappings", { method: "POST", body: JSON.stringify(payload) })
};
