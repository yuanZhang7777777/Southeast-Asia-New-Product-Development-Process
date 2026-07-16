export const SECONDARY_RESEARCH_POSITIONINGS = ["引流款", "利润款", "淘汰款", "稳定款", "清仓款"] as const;
export type SecondaryResearchPositioning = "" | typeof SECONDARY_RESEARCH_POSITIONINGS[number];
export const SECONDARY_RESEARCH_SKIP_LISTING = new Set<SecondaryResearchPositioning>(["淘汰款", "清仓款"]);

export type SecondaryResearchDraft<TImage = Record<string, unknown>> = {
  researchedAt: string;
  competitorUrl: string;
  conclusion: string;
  positioning: SecondaryResearchPositioning;
  evidenceImages: TImage[];
  directlyEdited?: boolean;
};

type SecondaryResearchSource<TImage> = {
  secondary_research_at?: string | null;
  secondary_competitor_url?: string | null;
  secondary_conclusion?: string | null;
  product_positioning?: string | null;
  secondary_evidence_images?: TImage[] | null;
};

export function createSecondaryResearchDraft<TImage = Record<string, unknown>>(
  source: SecondaryResearchSource<TImage> = {},
  now = new Date()
): SecondaryResearchDraft<TImage> {
  const hasServerDraft = Boolean(
    source.secondary_research_at ||
    source.secondary_competitor_url ||
    source.secondary_conclusion ||
    source.product_positioning ||
    source.secondary_evidence_images?.length
  );
  return {
    researchedAt: source.secondary_research_at?.slice(0, 16) || localDateTimeValue(now),
    competitorUrl: source.secondary_competitor_url || "",
    conclusion: source.secondary_conclusion || "",
    positioning: (source.product_positioning || "") as SecondaryResearchPositioning,
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
    for (const key of ["researchedAt", "competitorUrl", "conclusion", "positioning"] as const) {
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
      return !draft.conclusion.trim() || !draft.positioning;
    })
    .map((item) => item.sub_sku);
}

function localDateTimeValue(value: Date) {
  const offset = value.getTimezoneOffset() * 60000;
  return new Date(value.getTime() - offset).toISOString().slice(0, 16);
}
