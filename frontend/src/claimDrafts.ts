export type ClaimDraftState<TImage = unknown> = {
  mode: "claim" | "reject";
  claimDailySales: string;
  rejectReason: string;
  researchConclusion: string;
  evidenceImages: TImage[];
};

type ClaimSubmissionSource = {
  current_status: string;
  latest_claim_result?: string | null;
  latest_claim_daily_sales?: number | null;
  latest_reject_reason?: string | null;
  latest_feedback_summary?: string | null;
  latest_claim_note?: string | null;
};

export type ClaimEvidenceImage = {
  name: string;
  type: string;
  size: number;
  url?: string;
  previewUrl?: string;
};

export type ClaimSubmissionState = "pending" | "dirty" | "submitted";

export const REJECT_REASON_OPTIONS = [
  "稳定期利润率过低",
  "产品生命周期过短",
  "市场需求量过小",
  "调研数据不真实",
  "侵权/违规风险过高",
  "产品需认证资质",
  "抛货/重货/易碎品",
  "系统已有同款",
  "竞对销量差",
  "之前卖过类似款无销量",
  "市场竞对过多，优势不明显",
  "系统类似款成本更低",
  "近期销量下跌",
  "属性价差超5倍",
  "老链接垄断，同类型产品市场竞争大"
] as const;

export function parseRejectReason(value: string) {
  const parts = value.split("；").map((part) => part.trim()).filter(Boolean);
  const options = new Set<string>(REJECT_REASON_OPTIONS);
  return {
    selected: REJECT_REASON_OPTIONS.filter((option) => parts.includes(option)),
    custom: parts.filter((part) => !options.has(part)).join("；")
  };
}

export function formatRejectReason(selected: readonly string[], custom: string) {
  const selectedSet = new Set(selected);
  return [...REJECT_REASON_OPTIONS.filter((option) => selectedSet.has(option)), custom.trim()]
    .filter(Boolean)
    .join("；");
}

export function createClaimDraft<TImage = unknown>(): ClaimDraftState<TImage> {
  return { mode: "claim", claimDailySales: "", rejectReason: "", researchConclusion: "", evidenceImages: [] };
}

export function createClaimDraftFromLatest<TImage = unknown>(item: {
  latest_claim_result?: string | null;
  latest_claim_daily_sales?: number | null;
  latest_reject_reason?: string | null;
  latest_feedback_summary?: string | null;
}): ClaimDraftState<TImage> {
  return {
    mode: item.latest_claim_result === "reject" ? "reject" : "claim",
    claimDailySales: item.latest_claim_daily_sales == null ? "" : String(item.latest_claim_daily_sales),
    rejectReason: item.latest_reject_reason || "",
    researchConclusion: item.latest_feedback_summary || "",
    evidenceImages: []
  };
}

export function parseClaimEvidenceImages(note?: string | null): ClaimEvidenceImage[] {
  if (!note) return [];
  try {
    const parsed = JSON.parse(note) as { evidence_images?: unknown };
    if (!Array.isArray(parsed.evidence_images)) return [];
    return parsed.evidence_images
      .filter((image): image is Record<string, unknown> => Boolean(image) && typeof image === "object")
      .map((image) => ({
        name: typeof image.name === "string" && image.name ? image.name : "图片附件",
        type: typeof image.type === "string" ? image.type : "",
        size: typeof image.size === "number" ? image.size : 0,
        ...(typeof image.url === "string" && image.url ? { url: image.url } : {}),
        ...(typeof image.previewUrl === "string" && image.previewUrl ? { previewUrl: image.previewUrl } : {})
      }));
  } catch {
    return [];
  }
}

export function claimSubmissionState<TImage = unknown>(
  item: ClaimSubmissionSource,
  draft?: ClaimDraftState<TImage>
): ClaimSubmissionState {
  const submitted = ["claim_submitted", "claim_rejected"].includes(item.current_status) && Boolean(item.latest_claim_result);
  if (!draft) return submitted ? "submitted" : "pending";

  const saved = createClaimDraftFromLatest<TImage>(item);
  const dailySales = draft.claimDailySales.trim();
  const savedDailySales = saved.claimDailySales.trim();
  const sameDailySales =
    dailySales === savedDailySales ||
    (dailySales !== "" && savedDailySales !== "" && Number(dailySales) === Number(savedDailySales));
  const savedEvidence = parseClaimEvidenceImages(item.latest_claim_note).map(evidenceImageKey);
  const draftEvidence = draft.evidenceImages.map(evidenceImageKey);
  const changed =
    draft.mode !== saved.mode ||
    !sameDailySales ||
    draft.rejectReason.trim() !== saved.rejectReason.trim() ||
    draft.researchConclusion.trim() !== saved.researchConclusion.trim() ||
    JSON.stringify(draftEvidence) !== JSON.stringify(savedEvidence);
  return changed ? "dirty" : submitted ? "submitted" : "pending";
}

function evidenceImageKey(image: unknown) {
  if (!image || typeof image !== "object") return "";
  const value = image as Record<string, unknown>;
  return JSON.stringify([
    typeof value.name === "string" ? value.name : "",
    typeof value.type === "string" ? value.type : "",
    typeof value.size === "number" ? value.size : 0,
    typeof value.url === "string" ? value.url : typeof value.previewUrl === "string" ? value.previewUrl : ""
  ]);
}

export function patchClaimDraftGroup<TImage>(
  current: Record<string, ClaimDraftState<TImage>>,
  itemId: string,
  patch: Partial<ClaimDraftState<TImage>>,
  siblingIds: readonly string[] = [],
  syncReject = false,
  syncClaimDailySales = false
) {
  const previousSource = current[itemId] || createClaimDraft<TImage>();
  const nextSource = { ...previousSource, ...patch };
  const next = { ...current, [itemId]: nextSource };
  const shouldSyncReject =
    syncReject &&
    nextSource.mode === "reject" &&
    (patch.mode !== undefined || patch.rejectReason !== undefined || patch.researchConclusion !== undefined);
  const shouldSyncClaim = syncClaimDailySales && nextSource.mode === "claim" && patch.claimDailySales !== undefined;
  if (!shouldSyncReject && !shouldSyncClaim) return next;

  for (const siblingId of siblingIds) {
    if (siblingId === itemId) continue;
    const siblingDraft = current[siblingId];
    if (shouldSyncReject && canSyncRejectDraft(siblingDraft, previousSource)) {
      next[siblingId] = {
        ...(siblingDraft || createClaimDraft<TImage>()),
        mode: "reject",
        claimDailySales: "",
        rejectReason: nextSource.rejectReason,
        researchConclusion: nextSource.researchConclusion
      };
    } else if (shouldSyncClaim && canSyncClaimDraft(siblingDraft, previousSource)) {
      next[siblingId] = {
        ...(siblingDraft || createClaimDraft<TImage>()),
        mode: "claim",
        claimDailySales: nextSource.claimDailySales,
        rejectReason: ""
      };
    }
  }
  return next;
}

function canSyncClaimDraft<TImage>(draft: ClaimDraftState<TImage> | undefined, previousSource: ClaimDraftState<TImage>) {
  if (!draft) return true;
  return (
    draft.mode === "claim" &&
    !draft.rejectReason &&
    !draft.researchConclusion &&
    !draft.evidenceImages.length &&
    (!draft.claimDailySales || draft.claimDailySales === previousSource.claimDailySales)
  );
}

function canSyncRejectDraft<TImage>(draft: ClaimDraftState<TImage> | undefined, previousSource: ClaimDraftState<TImage>) {
  if (!draft) return true;
  if (
    draft.mode === "claim" &&
    !draft.claimDailySales &&
    !draft.rejectReason &&
    !draft.researchConclusion &&
    !draft.evidenceImages.length
  ) {
    return true;
  }
  return (
    draft.mode === "reject" &&
    !draft.claimDailySales &&
    !draft.evidenceImages.length &&
    draft.rejectReason === previousSource.rejectReason &&
    draft.researchConclusion === previousSource.researchConclusion
  );
}
