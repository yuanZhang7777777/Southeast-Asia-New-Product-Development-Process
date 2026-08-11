import type { RoleMapping } from "./api";

export type AdminSectionKey = "users" | "batches" | "switches";

export const ADMIN_SECTIONS: { key: AdminSectionKey; label: string }[] = [
  { key: "users", label: "用户管理" },
  { key: "batches", label: "导入批次" },
  { key: "switches", label: "系统开关" }
];

const ROLE_LABELS: Record<string, string> = {
  operator: "运营",
  manager: "主管",
  super_admin: "超级管理员"
};

const ROLE_OPTION_VALUES = ["operator", "manager", "super_admin"];

export function roleLabel(role: string) {
  return ROLE_LABELS[role] || role;
}

export function roleOptions(currentRole: string): { value: string; label: string }[] {
  const values = [...ROLE_OPTION_VALUES];
  if (currentRole && !values.includes(currentRole)) values.push(currentRole);
  return values.map((value) => ({ value, label: roleLabel(value) }));
}

export function mappingsForUser(userName: string, mappings: RoleMapping[]): RoleMapping[] {
  const name = userName.trim();
  if (!name) return [];
  return mappings.filter((mapping) => mapping.name.trim() === name);
}

export function validateResetPasswordInput(value: string) {
  const text = value.trim();
  if (!text) return "";
  return text.length >= 6 ? "" : "密码至少 6 位；留空则自动生成初始密码";
}

export function featureSwitchMeta(enabled: boolean): { label: string; klass: "green" | "gray" } {
  return enabled ? { label: "开", klass: "green" } : { label: "关", klass: "gray" };
}

export const BATCH_SOURCE_TYPE_OPTIONS: { value: string; label: string }[] = [
  { value: "selection1_developer_claim_feedback", label: "选品1 开发反馈表" },
  { value: "selection2_caigen_claim_feedback", label: "选品2 财根反馈表" },
  { value: "historical_market_monitor_archive", label: "历史市场监控档案" },
  { value: "history_finebi", label: "历史 FineBI 刊登" }
];

export function batchSourceTypeLabel(value?: string | null) {
  if (!value) return "-";
  return BATCH_SOURCE_TYPE_OPTIONS.find((option) => option.value === value)?.label || value;
}

export const BATCH_STATUS_OPTIONS: { value: string; label: string }[] = [
  { value: "running", label: "进行中" },
  { value: "completed", label: "已完成" },
  { value: "disabled", label: "已停用" }
];

export function batchStatusMeta(status: string): { label: string; klass: string } {
  const option = BATCH_STATUS_OPTIONS.find((item) => item.value === status);
  if (!option) return { label: status, klass: "gray" };
  if (status === "completed") return { label: option.label, klass: "green" };
  if (status === "running") return { label: option.label, klass: "blue" };
  return { label: option.label, klass: "gray" };
}

export function adminBatchPageCount(total: number, pageSize: number) {
  return Math.max(1, Math.ceil(total / Math.max(1, pageSize)));
}
