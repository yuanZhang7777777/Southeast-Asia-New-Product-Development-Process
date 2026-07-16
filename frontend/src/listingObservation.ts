export const PRODUCT_POSITIONINGS = ["引流款", "利润款", "淘汰款", "稳定款", "清仓款"] as const;
export type ProductPositioning = typeof PRODUCT_POSITIONINGS[number];

export type ListingDraft = {
  shop: string;
  item: string;
  listing_strategy: string;
  first_period_start: string;
};

export type ListingDraftErrors = Partial<Record<keyof ListingDraft, string>>;

export type ObservationReviewDraft = {
  period_id: string;
  week_number: number;
  product_positioning: ProductPositioning | "";
  optimization_action: string;
  four_week_summary: string;
};

export type ObservationReviewErrors = Partial<Record<"period_id" | "product_positioning" | "optimization_action" | "four_week_summary", string>>;

export type ObservationFilterRow = {
  main_sku: string;
  main_sku_name?: string | null;
  country?: string | null;
  salesperson_name: string;
  shop: string;
  item: string;
  week_number: number;
  period_start: string;
  status: string;
  tracking_status: string;
  product_positioning?: string | null;
};

export type ObservationFilters = {
  query?: string;
  country?: string;
  salesperson_name?: string;
  shop?: string;
  period_start?: string;
  status?: string;
  week_number?: number | "";
  product_positioning?: string;
  tracking_status?: string;
};

export function defaultNextBusinessPeriodStart(dayText = shanghaiDateText()) {
  const [year, month, day] = dayText.split("-").map(Number);
  const value = new Date(Date.UTC(year, month - 1, day));
  const daysSinceThursday = (value.getUTCDay() - 4 + 7) % 7;
  value.setUTCDate(value.getUTCDate() - daysSinceThursday + 7);
  return value.toISOString().slice(0, 10);
}

export function buildListingTaskContexts<
  TTask extends {
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
  },
  TListing extends {
    task_key: string;
    country?: string | null;
    site?: string | null;
    main_sku: string;
    main_sku_name?: string | null;
    salesperson_name: string;
  }
>(tasks: readonly TTask[], listings: readonly TListing[], defaultFirstPeriodStart: string) {
  const contexts = new Map<string, TTask | {
    task_key: string;
    source_type: string;
    business_period: null;
    country?: string | null;
    site?: string | null;
    main_sku: string;
    main_sku_name?: string | null;
    salesperson_name: string;
    claim_record_ids: never[];
    default_first_period_start: string;
  }>();
  for (const task of tasks) contexts.set(task.task_key, task);
  for (const listing of listings) {
    if (contexts.has(listing.task_key)) continue;
    contexts.set(listing.task_key, {
      task_key: listing.task_key,
      source_type: "",
      business_period: null,
      country: listing.country,
      site: listing.site,
      main_sku: listing.main_sku,
      main_sku_name: listing.main_sku_name,
      salesperson_name: listing.salesperson_name,
      claim_record_ids: [],
      default_first_period_start: defaultFirstPeriodStart
    });
  }
  return Array.from(contexts.values()).sort((left, right) =>
    `${left.main_sku}|${left.country || ""}|${left.salesperson_name}`.localeCompare(
      `${right.main_sku}|${right.country || ""}|${right.salesperson_name}`
    )
  );
}

export function validateListingDrafts(rows: readonly ListingDraft[]): ListingDraftErrors[] {
  const errors = rows.map((row) => ({
    ...(!row.shop.trim() && { shop: "请填写店铺" }),
    ...(!row.item.trim() && { item: "请填写 Item" }),
    ...(!row.listing_strategy.trim() && { listing_strategy: "请填写刊登策略" }),
    ...(!row.first_period_start && { first_period_start: "请选择第一周起始周期" })
  }));
  const counts = new Map<string, number>();
  for (const row of rows) {
    const item = row.item.trim();
    if (item) counts.set(item, (counts.get(item) || 0) + 1);
  }
  rows.forEach((row, index) => {
    if ((counts.get(row.item.trim()) || 0) > 1) errors[index].item = "Item 在本批次中重复";
  });
  return errors;
}

export function validateObservationReviews(rows: readonly ObservationReviewDraft[]): Record<string, ObservationReviewErrors> {
  const result: Record<string, ObservationReviewErrors> = {};
  for (const row of rows) {
    const errors: ObservationReviewErrors = {
      ...(!row.product_positioning && { product_positioning: "请选择产品定位" }),
      ...(!row.optimization_action.trim() && { optimization_action: "请填写优化操作" }),
      ...(row.week_number === 4 && !row.four_week_summary.trim() && { four_week_summary: "请填写四周总结" })
    };
    if (Object.keys(errors).length) result[row.period_id] = errors;
  }
  return result;
}

export function filterObservationRows<T extends ObservationFilterRow>(rows: readonly T[], filters: ObservationFilters): T[] {
  const query = filters.query?.trim().toLocaleLowerCase();
  return rows.filter((row) => {
    if (query && ![row.main_sku, row.main_sku_name, row.item].some((value) => value?.toLocaleLowerCase().includes(query))) return false;
    if (filters.country && row.country !== filters.country) return false;
    if (filters.salesperson_name && row.salesperson_name !== filters.salesperson_name) return false;
    if (filters.shop && !row.shop.includes(filters.shop.trim())) return false;
    if (filters.period_start && row.period_start !== filters.period_start) return false;
    if (filters.status && row.status !== filters.status) return false;
    if (filters.week_number && (filters.week_number === 5 ? row.week_number < 5 : row.week_number !== filters.week_number)) return false;
    if (filters.product_positioning && row.product_positioning !== filters.product_positioning) return false;
    if (filters.tracking_status && row.tracking_status !== filters.tracking_status) return false;
    return true;
  });
}

export function formatPercent(value?: number | null) {
  return value === null || value === undefined ? "-" : `${(value * 100).toFixed(2)}%`;
}

export function formatObservationMetric(value?: number | null) {
  return value === null || value === undefined
    ? "周数据未获取"
    : value.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
}

export function mapReviewServerRowErrors(
  error: unknown,
  rows: readonly ObservationReviewDraft[]
): Record<string, ObservationReviewErrors> {
  const source = parseError(error);
  const detail = isRecord(source.detail) ? source.detail : source;
  const rowErrors = Array.isArray(detail.row_errors) ? detail.row_errors : [];
  const result: Record<string, ObservationReviewErrors> = {};
  for (const entry of rowErrors) {
    if (!isRecord(entry) || typeof entry.row_index !== "number" || typeof entry.field !== "string" || typeof entry.message !== "string") continue;
    const periodId = rows[entry.row_index]?.period_id;
    if (!periodId || !["period_id", "product_positioning", "optimization_action", "four_week_summary"].includes(entry.field)) continue;
    result[periodId] = { ...result[periodId], [entry.field]: entry.message };
  }
  return result;
}

export function latestPeriodIdsByListing(rows: readonly { id: string; listing_record_id: string; week_number: number }[]) {
  const latest: Record<string, { id: string; week: number }> = {};
  for (const row of rows) {
    if (!latest[row.listing_record_id] || row.week_number > latest[row.listing_record_id].week) {
      latest[row.listing_record_id] = { id: row.id, week: row.week_number };
    }
  }
  return Object.fromEntries(Object.entries(latest).map(([listingId, row]) => [listingId, row.id]));
}

export function resolveWorkbenchScope(
  role: "operator" | "manager",
  canManage: boolean,
  operatorName: string,
  onlyMyTasks: boolean
) {
  if (!canManage) return { only_my_tasks: true };
  if (role === "operator" && operatorName) return { salesperson_name: operatorName, only_my_tasks: false };
  return { only_my_tasks: onlyMyTasks };
}

export function summarySalespersonScope(
  role: "operator" | "manager",
  canManage: boolean,
  operatorName: string
) {
  return canManage && role === "operator" && operatorName ? operatorName : undefined;
}

export function createRequestGate() {
  let latest = 0;
  return {
    start: () => ++latest,
    isCurrent: (requestId: number) => requestId === latest
  };
}

export function visibleSelectedPeriodIds(selectedIds: readonly string[], visibleRows: readonly { id: string }[]) {
  const visible = new Set(visibleRows.map((row) => row.id));
  return selectedIds.filter((id) => visible.has(id));
}

export function sortObservationRows<T extends {
  main_sku: string;
  country?: string | null;
  salesperson_name: string;
  item: string;
  week_number: number;
  period_start: string;
}>(rows: readonly T[]): T[] {
  return [...rows].sort((left, right) => {
    const leftGroup = `${left.main_sku}|${left.country || ""}|${left.salesperson_name}|${left.item}`;
    const rightGroup = `${right.main_sku}|${right.country || ""}|${right.salesperson_name}|${right.item}`;
    return leftGroup.localeCompare(rightGroup) || left.week_number - right.week_number || left.period_start.localeCompare(right.period_start);
  });
}

export function hasFetchedMetrics(rows: readonly { status: string }[]) {
  return rows.some((row) => row.status !== "pending_data");
}

export function productListingSummary<
  TListing extends { id: string; main_sku: string; country?: string | null },
  TPeriod extends { listing_record_id: string }
>(
  data: { listing_records: readonly TListing[]; period_rows: readonly TPeriod[] },
  mainSku: string,
  country?: string | null
) {
  const listings = data.listing_records.filter((listing) =>
    listing.main_sku === mainSku && (!country || listing.country === country)
  );
  const listingIds = new Set(listings.map((listing) => listing.id));
  return { listings, periods: data.period_rows.filter((period) => listingIds.has(period.listing_record_id)) };
}

export function mapServerRowErrors(error: unknown): Record<number, ListingDraftErrors> {
  const source = parseError(error);
  const detail = isRecord(source.detail) ? source.detail : source;
  const rowErrors = Array.isArray(detail.row_errors) ? detail.row_errors : [];
  const result: Record<number, ListingDraftErrors> = {};
  for (const entry of rowErrors) {
    if (!isRecord(entry) || typeof entry.row_index !== "number" || typeof entry.field !== "string" || typeof entry.message !== "string") continue;
    if (!["shop", "item", "listing_strategy", "first_period_start"].includes(entry.field)) continue;
    result[entry.row_index] = { ...result[entry.row_index], [entry.field]: entry.message };
  }
  return result;
}

function parseError(error: unknown): Record<string, unknown> {
  if (isRecord(error)) {
    if (error instanceof Error) {
      try {
        const parsed = JSON.parse(error.message);
        return isRecord(parsed) ? parsed : {};
      } catch {
        return {};
      }
    }
    return error;
  }
  return {};
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function shanghaiDateText() {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit"
  }).format(new Date());
}
