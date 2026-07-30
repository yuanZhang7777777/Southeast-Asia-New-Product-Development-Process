export type StockingRole = "operator" | "manager";
export type StockingRequestType = "initial" | "replenishment";

export type StockingDraft = {
  application_date: string;
  request_type: StockingRequestType;
  cost_price: number | null;
  length_cm?: number | null;
  width_cm?: number | null;
  height_cm?: number | null;
  unit_volume: number | null;
  unit_volume_source?: "erp" | "manual" | null;
  daily_sales: number | null;
  country: string;
  warehouse?: string;
  reason?: string;
};

export type StockingDraftErrors = Partial<Record<keyof StockingDraft, string>>;

export type StockingAutosaveState = "saving" | "saved" | "dirty" | "error";

export class StockingDraftSaveQueue<TPayload> {
  private versions = new Map<string, number>();
  private savedVersions = new Map<string, number>();
  private queuedVersions = new Map<string, number>();
  private queues = new Map<string, Promise<boolean>>();

  markDirty(requestId: string) {
    const version = (this.versions.get(requestId) || 0) + 1;
    this.versions.set(requestId, version);
    return version;
  }

  isDirty(requestId: string) {
    return (this.versions.get(requestId) || 0) > (this.savedVersions.get(requestId) || 0);
  }

  enqueue(
    requestId: string,
    payload: TPayload,
    save: (payload: TPayload) => Promise<unknown>,
    onState?: (state: StockingAutosaveState) => void
  ): Promise<boolean> {
    const version = this.versions.get(requestId) || 0;
    const savedVersion = this.savedVersions.get(requestId) || 0;
    const queuedVersion = this.queuedVersions.get(requestId) || 0;
    if (version <= savedVersion) return Promise.resolve(false);
    if (version <= queuedVersion) return this.queues.get(requestId) || Promise.resolve(false);

    this.queuedVersions.set(requestId, version);
    const previous = this.queues.get(requestId) || Promise.resolve(false);
    const job = previous.catch(() => false).then(async () => {
      onState?.("saving");
      try {
        await save(payload);
        this.savedVersions.set(requestId, Math.max(this.savedVersions.get(requestId) || 0, version));
        onState?.(this.isDirty(requestId) ? "dirty" : "saved");
        return true;
      } catch (error) {
        if ((this.queuedVersions.get(requestId) || 0) === version) {
          this.queuedVersions.set(requestId, this.savedVersions.get(requestId) || 0);
        }
        onState?.((this.versions.get(requestId) || 0) === version ? "error" : "dirty");
        throw error;
      }
    });
    const tracked = job.finally(() => {
      if (this.queues.get(requestId) === tracked) this.queues.delete(requestId);
    });
    this.queues.set(requestId, tracked);
    return tracked;
  }
}

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

export function buildStockingDraftUpdate(draft: StockingDraft) {
  const optionalNumber = (value: number | null) => value !== null && Number.isFinite(value) ? value : null;
  const lengthCm = optionalNumber(draft.length_cm ?? null);
  const widthCm = optionalNumber(draft.width_cm ?? null);
  const heightCm = optionalNumber(draft.height_cm ?? null);
  const unitVolume = stockingUnitVolume(lengthCm, widthCm, heightCm) ?? optionalNumber(draft.unit_volume);
  return {
    application_date: draft.application_date || null,
    request_type: draft.request_type,
    cost_price: optionalNumber(draft.cost_price),
    length_cm: lengthCm,
    width_cm: widthCm,
    height_cm: heightCm,
    unit_volume: unitVolume,
    unit_volume_source: unitVolume === null ? null : draft.unit_volume_source || "manual",
    daily_sales: optionalNumber(draft.daily_sales),
    country: draft.country.trim() || null,
    warehouse: draft.warehouse?.trim() || null,
    reason: draft.reason?.trim() || null
  };
}

export function stockingUnitVolume(lengthCm: number | null, widthCm: number | null, heightCm: number | null) {
  const dimensions = [lengthCm, widthCm, heightCm];
  if (!dimensions.every((value) => value !== null && Number.isFinite(value) && value > 0)) return null;
  const volume = Number(lengthCm) * Number(widthCm) * Number(heightCm) / 1_000_000;
  return Math.round(volume * 1_000_000_000_000) / 1_000_000_000_000;
}

export function operatorStockingCountry(item: { country?: string | null }) {
  return item.country?.trim() || "";
}

export function visibleStockingRequestIds(
  selectedIds: readonly string[],
  visibleRows: readonly { request_id: string }[]
) {
  const visible = new Set(visibleRows.map((row) => row.request_id));
  return Array.from(new Set(selectedIds.filter((id) => visible.has(id))));
}

export function groupStockingItems<T extends GroupableStockingItem>(items: readonly T[]) {
  const groups = new Map<string, T[]>();
  for (const item of items) groups.set(item.main_sku, [...(groups.get(item.main_sku) || []), item]);
  return Array.from(groups, ([main_sku, groupedItems]) => ({
    main_sku,
    items: [...groupedItems].sort((left, right) => left.sub_sku.localeCompare(right.sub_sku, "zh-CN", { numeric: true }))
  })).sort((left, right) => left.main_sku.localeCompare(right.main_sku, "zh-CN", { numeric: true }));
}

export function buildStockingExportPayload(requestIds: readonly string[]) {
  const request_ids = Array.from(new Set(requestIds.map((id) => id.trim()).filter(Boolean)));
  if (!request_ids.length) throw new Error("至少选择一条申请");
  return { request_ids };
}

export function stockingSourceLabel(source: string) {
  if (source === "sales_self_selection") return "销售自选";
  if (source === "selection1" || source === "selection1_developer_claim_feedback") return "选品1";
  if (source === "selection2_caigen_claim_feedback") return "选品2/财根";
  return source;
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
