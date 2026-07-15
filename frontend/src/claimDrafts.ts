export type ClaimDraftState<TImage = unknown> = {
  mode: "claim" | "reject";
  claimDailySales: string;
  rejectReason: string;
  researchConclusion: string;
  evidenceImages: TImage[];
};

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
