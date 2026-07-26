export const SECONDARY_RESEARCH_POSITIONINGS = ["引流款", "利润款", "淘汰款", "稳定款", "清仓款"] as const;
export type SecondaryResearchPositioning = "" | typeof SECONDARY_RESEARCH_POSITIONINGS[number];
export const SECONDARY_RESEARCH_SKIP_LISTING = new Set<SecondaryResearchPositioning>(["淘汰款", "清仓款"]);

export type SecondaryResearchScenario = "pending" | "submitted";
export type SecondaryResearchFilters = { scenario: SecondaryResearchScenario; query?: string; country?: string; businessPeriod?: string; salespersonName?: string };
type SecondaryResearchFilterGroup = {
  country?: string | null; business_period?: string | null; salesperson_name: string; main_sku: string; main_sku_name?: string | null;
  items: readonly { sub_sku: string; sub_sku_name?: string | null; secondary_research_submitted_at?: string | null; downstream_status: string }[];
};
export function filterSecondaryResearchGroups<T extends SecondaryResearchFilterGroup>(groups: readonly T[], filters: SecondaryResearchFilters): T[] {
  const query = filters.query?.trim().toLocaleLowerCase();
  return groups.flatMap((group) => {
    if ((filters.country && group.country !== filters.country) || (filters.businessPeriod && group.business_period !== filters.businessPeriod) || (filters.salespersonName && group.salesperson_name !== filters.salespersonName)) return [];
    const items = group.items.filter((item) => filters.scenario === "submitted"
      ? Boolean(item.secondary_research_submitted_at)
      : !item.secondary_research_submitted_at && item.downstream_status === "waiting_secondary_research");
    if (!items.length || (query && ![group.main_sku, group.main_sku_name, ...items.flatMap((item) => [item.sub_sku, item.sub_sku_name])].some((value) => value?.toLocaleLowerCase().includes(query)))) return [];
    return [{ ...group, items } as T];
  });
}

export function latestSecondaryResearchPeriod<T extends SecondaryResearchFilterGroup>(
  groups: readonly T[],
  scenario: SecondaryResearchScenario,
  filters: Pick<SecondaryResearchFilters, "country" | "salespersonName"> = {}
) {
  const periods = filterSecondaryResearchGroups(groups, { scenario, ...filters })
    .map((group) => group.business_period || "")
    .filter(Boolean)
    .sort();
  return periods[periods.length - 1] || "";
}

export type SecondaryResearchDraft<TImage = Record<string, unknown>> = {
  competitorUrl: string;
  conclusion: string;
  positioning: SecondaryResearchPositioning;
  targetDailySales: string;
  sellingPoints: string;
  evidenceImages: TImage[];
  directlyEdited?: boolean;
};

type SecondaryResearchSource<TImage> = {
  secondary_competitor_url?: string | null;
  secondary_conclusion?: string | null;
  product_positioning?: string | null;
  secondary_target_daily_sales?: number | string | null;
  secondary_selling_points?: string | null;
  secondary_evidence_images?: TImage[] | null;
};

export function createSecondaryResearchDraft<TImage = Record<string, unknown>>(
  source: SecondaryResearchSource<TImage> = {},
  _now = new Date()
): SecondaryResearchDraft<TImage> {
  const hasServerDraft = Boolean(
    source.secondary_competitor_url ||
    source.secondary_conclusion ||
    source.product_positioning ||
    source.secondary_target_daily_sales ||
    source.secondary_selling_points ||
    source.secondary_evidence_images?.length
  );
  return {
    competitorUrl: source.secondary_competitor_url || "",
    conclusion: source.secondary_conclusion || "",
    positioning: (source.product_positioning || "") as SecondaryResearchPositioning,
    targetDailySales: source.secondary_target_daily_sales == null ? "" : String(source.secondary_target_daily_sales),
    sellingPoints: source.secondary_selling_points || "",
    evidenceImages: source.secondary_evidence_images || [],
    directlyEdited: hasServerDraft
  };
}

export function patchSecondaryResearchDraft<TImage>(
  current: Record<string, SecondaryResearchDraft<TImage>>,
  claimRecordId: string,
  patch: Partial<SecondaryResearchDraft<TImage>>
) {
  return {
    ...current,
    [claimRecordId]: {
      ...(current[claimRecordId] || createSecondaryResearchDraft<TImage>()),
      ...patch
    }
  };
}

export function syncSecondaryResearchDraftPatch<TImage>(
  current: Record<string, SecondaryResearchDraft<TImage>>,
  items: readonly { claim_record_id: string }[],
  claimRecordId: string,
  patch: Partial<SecondaryResearchDraft<TImage>>
) {
  const next = patchSecondaryResearchDraft(current, claimRecordId, { ...patch, directlyEdited: true });
  for (const item of items) {
    if (item.claim_record_id === claimRecordId) continue;
    const draft = next[item.claim_record_id] || createSecondaryResearchDraft<TImage>();
    if (draft.directlyEdited) continue;
    const synced = { ...draft };
    for (const key of ["competitorUrl", "conclusion", "positioning", "targetDailySales", "sellingPoints"] as const) {
      if (key in patch) synced[key] = patch[key] as never;
    }
    next[item.claim_record_id] = synced;
  }
  return next;
}

export function incompleteSecondaryResearchItems<TImage>(
  items: readonly { claim_record_id: string; sub_sku: string }[],
  drafts: Record<string, SecondaryResearchDraft<TImage>>
) {
  return items
    .filter((item) => {
      const draft = drafts[item.claim_record_id] || createSecondaryResearchDraft<TImage>();
      const target = Number(draft.targetDailySales);
      return !draft.conclusion.trim() || !draft.positioning || !Number.isFinite(target) || target <= 0 || !draft.sellingPoints.trim();
    })
    .map((item) => item.sub_sku);
}
