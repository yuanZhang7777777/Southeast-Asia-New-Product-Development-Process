export type OperatorClaimFilter = {
  businessPeriod?: string;
  status?: "pending" | "claimed_pending_review" | "rejected_pending_review" | "returned" | "";
};

export type OperatorClaimFilterRow = {
  batch?: string | null;
  source_sheet?: string | null;
  created_at: string;
  current_status: string;
};

export const operatorClaimStatusOptions = [
  { value: "pending", label: "待填写" },
  { value: "claimed_pending_review", label: "已认领待复核" },
  { value: "rejected_pending_review", label: "不认领待复核" },
  { value: "returned", label: "退回补充" }
] as const;

export function businessPeriodsByNewest<T extends OperatorClaimFilterRow>(rows: readonly T[]) {
  const newest = new Map<string, number>();
  for (const row of rows) {
    const period = businessPeriodOf(row);
    if (!period) continue;
    newest.set(period, Math.max(newest.get(period) || 0, Date.parse(row.created_at) || 0));
  }
  return Array.from(newest).sort((left, right) => right[1] - left[1]).map(([period]) => period);
}

export function latestBusinessPeriod<T extends OperatorClaimFilterRow>(rows: readonly T[]) {
  return businessPeriodsByNewest(rows)[0] || "";
}

export function filterOperatorClaimRows<T extends OperatorClaimFilterRow>(rows: readonly T[], filter: OperatorClaimFilter): T[] {
  return rows.filter((row) => {
    if (filter.businessPeriod && businessPeriodOf(row) !== filter.businessPeriod) return false;
    if (!filter.status) return true;
    return claimStatusKey(row.current_status) === filter.status;
  });
}

function businessPeriodOf(row: OperatorClaimFilterRow) {
  return (row.batch || row.source_sheet || "").trim();
}

function claimStatusKey(status: string): OperatorClaimFilter["status"] {
  if (status === "claim_submitted") return "claimed_pending_review";
  if (status === "claim_rejected") return "rejected_pending_review";
  if (status === "returned_for_supplement") return "returned";
  if (status === "assigned" || status === "open_claim_pool") return "pending";
  return "";
}
