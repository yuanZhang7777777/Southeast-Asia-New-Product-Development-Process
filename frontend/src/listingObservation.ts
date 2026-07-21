import type { ListingRecord, ObservationPeriodRow, PendingListingTask } from "./api";

export const PRODUCT_POSITIONINGS = ["引流款", "利润款", "淘汰款", "稳定款", "清仓款"] as const;
export type ProductPositioning = typeof PRODUCT_POSITIONINGS[number];

export type WorkbenchBusinessStatus =
  | "all"
  | "pending_listing"
  | "pending_review"
  | "first_round_completed"
  | "stopped"
  | "voided";

export type ListingWorkbenchGroup = {
  context: PendingListingTask;
  listings: ListingRecord[];
  periodRows: ObservationPeriodRow[];
  pendingListing: boolean;
};

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

export type ObservationPeriodDisplay = "hidden" | "in_progress" | "data_pending" | "ready";

export function observationPeriodDisplay(
  row: Pick<ObservationPeriodRow, "status" | "period_start" | "period_end">,
  dayText = shanghaiDateText()
): ObservationPeriodDisplay {
  if (dayText < row.period_start) return "hidden";
  if (row.status !== "pending_data") return "ready";
  return dayText <= row.period_end ? "in_progress" : "data_pending";
}

export function expectedObservationMetricsDate(periodEnd: string) {
  const [year, month, day] = periodEnd.split("-").map(Number);
  const value = new Date(Date.UTC(year, month - 1, day));
  value.setUTCDate(value.getUTCDate() + 1);
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

export function buildListingWorkbenchGroups(
  tasks: readonly PendingListingTask[],
  listings: readonly ListingRecord[],
  periodRows: readonly ObservationPeriodRow[],
  defaultFirstPeriodStart: string
): ListingWorkbenchGroup[] {
  const reusableListingIds = new Set(tasks.flatMap((task) => task.reusable_listing_ids));
  const contexts = buildListingTaskContexts(
    tasks,
    listings.filter((listing) => !reusableListingIds.has(listing.id)),
    defaultFirstPeriodStart
  ) as PendingListingTask[];
  return contexts.flatMap((context) => {
    const reusableIds = new Set(context.reusable_listing_ids || []);
    const groupListings = listings.filter((listing) =>
      reusableIds.has(listing.id)
      || (listing.task_key === context.task_key && !reusableListingIds.has(listing.id))
    );
    if (!context.requires_confirmation && !groupListings.length) return [];
    const listingIds = new Set(groupListings.map((listing) => listing.id));
    return [{
      context,
      listings: groupListings,
      periodRows: periodRows.filter((row) => listingIds.has(row.listing_record_id)),
      pendingListing: Boolean(context.requires_confirmation)
    }];
  });
}

export function filterListingWorkbenchGroups(
  groups: readonly ListingWorkbenchGroup[],
  status: WorkbenchBusinessStatus
): ListingWorkbenchGroup[] {
  const visible = groups.flatMap((group) => {
    if (status === "pending_listing") return group.pendingListing ? [{ ...group, periodRows: [] }] : [];
    if (status === "all") return [group];
    const listingById = new Map(group.listings.map((listing) => [listing.id, listing]));
    if (status === "pending_review") {
      const visibleListingIds = new Set(group.periodRows.flatMap((row) => {
        const listing = listingById.get(row.listing_record_id);
        return listing?.status === "active" && row.status === "pending_review" ? [listing.id] : [];
      }));
      const periodRows = group.periodRows.filter((row) => visibleListingIds.has(row.listing_record_id));
      return periodRows.length ? [{
        ...group,
        listings: group.listings.filter((listing) => visibleListingIds.has(listing.id)),
        periodRows
      }] : [];
    }
    const periodRows = group.periodRows.filter((row) => {
      const listing = listingById.get(row.listing_record_id);
      if (!listing) return false;
      if (status === "first_round_completed") return Boolean(listing.first_round_completed_at);
      if (status === "stopped") return listing.status === "active" && listing.tracking_status === "stopped";
      return listing.status === "voided";
    });
    const visibleListingIds = new Set(periodRows.map((row) => row.listing_record_id));
    const visibleListings = group.listings.filter((listing) => visibleListingIds.has(listing.id));
    return periodRows.length ? [{ ...group, listings: visibleListings, periodRows }] : [];
  });
  return visible.sort((left, right) => {
    const priority = (group: ListingWorkbenchGroup) => {
      if (group.pendingListing) return 0;
      const listingById = new Map(group.listings.map((listing) => [listing.id, listing]));
      return group.periodRows.some((row) => {
        const listing = listingById.get(row.listing_record_id);
        return listing?.status === "active" && row.status === "pending_review";
      }) ? 1 : 2;
    };
    return priority(left) - priority(right)
      || left.context.main_sku.localeCompare(right.context.main_sku)
      || left.context.salesperson_name.localeCompare(right.context.salesperson_name);
  });
}

export function canEditObservationPeriod(
  row: Pick<ObservationPeriodRow, "status">,
  listing?: Pick<ListingRecord, "status">
) {
  return listing?.status === "active" && row.status !== "pending_data";
}

export function createObservationReviewDraft(row: ObservationPeriodRow): ObservationReviewDraft {
  return {
    period_id: row.id,
    week_number: row.week_number,
    product_positioning: row.product_positioning || row.default_product_positioning || "",
    optimization_action: row.optimization_action || "",
    four_week_summary: row.four_week_summary || ""
  };
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
  operatorName: string
) {
  if (canManage && role === "operator") {
    return operatorName ? { salesperson_name: operatorName } : null;
  }
  return {};
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

export function productListingSummaryByBusinessPeriod(
  data: { listing_records: readonly ListingRecord[]; period_rows: readonly ObservationPeriodRow[] },
  mainSku: string,
  country?: string | null,
  currentBusinessPeriod?: string | null
) {
  const summary = productListingSummary(data, mainSku, country);
  const periodsFor = (listing: ListingRecord): Array<string | null> => {
    const sourcePeriods = listing.source_business_periods.filter(Boolean);
    return sourcePeriods.length ? sourcePeriods : [listing.business_period || null];
  };
  const businessPeriods = [...new Set(summary.listings.flatMap(periodsFor))]
    .sort((left, right) => Number(right === currentBusinessPeriod) - Number(left === currentBusinessPeriod));
  return businessPeriods.map((businessPeriod) => {
    const listings = summary.listings.filter((listing) => periodsFor(listing).includes(businessPeriod));
    const listingIds = new Set(listings.map((listing) => listing.id));
    return {
      business_period: businessPeriod,
      listings,
      periods: summary.periods.filter((period) => listingIds.has(period.listing_record_id))
    };
  });
}

export function saveListingDrafts(
  storage: Storage,
  userId: string,
  taskKey: string,
  drafts: readonly ListingDraft[]
) {
  saveDraft(storage, listingDraftKey(userId, taskKey), drafts);
}

export function restoreListingDrafts(
  storage: Storage,
  userId: string,
  taskKey: string,
  fallback: readonly ListingDraft[],
  ignoreStored = false
): ListingDraft[] {
  if (ignoreStored) return [...fallback];
  return restoreDraft(storage, listingDraftKey(userId, taskKey), isListingDrafts) || [...fallback];
}

export function clearListingDrafts(storage: Storage, userId: string, taskKey: string) {
  clearDraft(storage, listingDraftKey(userId, taskKey));
}

export function saveObservationReviewDraft(
  storage: Storage,
  userId: string,
  periodId: string,
  draft: ObservationReviewDraft
) {
  saveDraft(storage, observationReviewDraftKey(userId, periodId), draft);
}

export function restoreObservationReviewDraft(
  storage: Storage,
  userId: string,
  row: ObservationPeriodRow,
  ignoreStored = false
): ObservationReviewDraft {
  if (ignoreStored) return createObservationReviewDraft(row);
  return restoreDraft(
    storage,
    observationReviewDraftKey(userId, row.id),
    (value): value is ObservationReviewDraft => isObservationReviewDraft(value)
      && value.period_id === row.id
      && value.week_number === row.week_number
  )
    || createObservationReviewDraft(row);
}

export function clearObservationReviewDraft(storage: Storage, userId: string, periodId: string) {
  clearDraft(storage, observationReviewDraftKey(userId, periodId));
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

function listingDraftKey(userId: string, taskKey: string) {
  return `listing-observation:v1:${userId}:listing:${taskKey}`;
}

function observationReviewDraftKey(userId: string, periodId: string) {
  return `listing-observation:v1:${userId}:period:${periodId}`;
}

function saveDraft(storage: Storage, key: string, data: unknown) {
  try {
    storage.setItem(key, JSON.stringify({ version: 1, data }));
  } catch {
    // Browsers may disable or exhaust Storage; the in-memory draft still works.
  }
}

function restoreDraft<T>(storage: Storage, key: string, validate: (value: unknown) => value is T): T | null {
  try {
    const raw = storage.getItem(key);
    if (raw === null) return null;
    const value: unknown = JSON.parse(raw);
    if (isRecord(value) && value.version === 1 && validate(value.data)) return value.data;
  } catch {
    // Invalid or unavailable Storage falls back to server data below.
  }
  clearDraft(storage, key);
  return null;
}

function clearDraft(storage: Storage, key: string) {
  try {
    storage.removeItem(key);
  } catch {
    // Storage cleanup must not block the page.
  }
}

function isListingDrafts(value: unknown): value is ListingDraft[] {
  return Array.isArray(value) && value.every((draft) => isRecord(draft)
    && typeof draft.shop === "string"
    && typeof draft.item === "string"
    && typeof draft.listing_strategy === "string"
    && typeof draft.first_period_start === "string");
}

function isObservationReviewDraft(value: unknown): value is ObservationReviewDraft {
  return isRecord(value)
    && typeof value.period_id === "string"
    && typeof value.week_number === "number"
    && (value.product_positioning === "" || PRODUCT_POSITIONINGS.includes(value.product_positioning as ProductPositioning))
    && typeof value.optimization_action === "string"
    && typeof value.four_week_summary === "string";
}

function shanghaiDateText() {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit"
  }).format(new Date());
}
