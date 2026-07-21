export type StockingRole = "operator" | "manager";
export type StockingRequestType = "initial" | "replenishment";

export type StockingDraft = {
  application_date: string;
  request_type: StockingRequestType;
  cost_price: number | null;
  unit_volume: number | null;
  daily_sales: number | null;
  country: string;
  warehouse?: string;
  reason?: string;
};

export type StockingDraftErrors = Partial<Record<keyof StockingDraft, string>>;

type GroupableStockingItem = {
  claim_record_id: string;
  main_sku: string;
  sub_sku: string;
};

export function roleStockingLabel(role: StockingRole) {
  return role === "operator" ? "备货申请" : "导出中心";
}

export function stockingDecisionStatus(inventoryAvailable: boolean, needsStocking: boolean) {
  if (needsStocking) return "waiting_stocking_request";
  return inventoryAvailable ? "waiting_listing" : "stocking_paused";
}

export function stockingFormVisible(item: { source_type: string; request_id?: string | null; needs_stocking?: boolean | null }) {
  if (!item.request_id) return false;
  return item.source_type !== "sales_self_selection" || item.needs_stocking !== false;
}
export function stockingQuantity(dailySales: number) {
  return Math.ceil(dailySales * 30);
}

export function validateStockingDraft(draft: StockingDraft, salesSelf = false): StockingDraftErrors {
  const errors: StockingDraftErrors = {};
  if (!draft.application_date) errors.application_date = "申请日期必填";
  if (!(Number(draft.cost_price) > 0)) errors.cost_price = salesSelf ? "销售自选必须填写成本价" : "成本价必须大于 0";
  if (!(Number(draft.unit_volume) > 0)) errors.unit_volume = "单个体积必须大于 0";
  if (!(Number(draft.daily_sales) > 0)) errors.daily_sales = "备货单销必须大于 0";
  if (!draft.country.trim()) errors.country = "备货国家必填";
  if (draft.request_type === "replenishment" && !draft.reason?.trim()) errors.reason = "补货时必须填写补货原因";
  return errors;
}

export function groupStockingItems<T extends GroupableStockingItem>(items: readonly T[]) {
  const groups = new Map<string, T[]>();
  for (const item of items) groups.set(item.main_sku, [...(groups.get(item.main_sku) || []), item]);
  return Array.from(groups, ([main_sku, groupedItems]) => ({ main_sku, items: groupedItems }));
}

export function buildStockingExportPayload(requestIds: readonly string[]) {
  const request_ids = Array.from(new Set(requestIds.map((id) => id.trim()).filter(Boolean)));
  if (!request_ids.length) throw new Error("至少选择一条申请");
  return { request_ids };
}

export function stockingStatusLabel(status: string) {
  return ({
    waiting_stocking_request: "待填备货申请",
    waiting_export: "待导出",
    stocking_paused: "暂不推进",
    waiting_listing: "待刊登",
    draft: "草稿",
    submitted: "已提交",
    exported: "已导出"
  } as Record<string, string>)[status] || status;
}
