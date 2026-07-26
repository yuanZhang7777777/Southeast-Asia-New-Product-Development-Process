import type { DashboardCounts } from "./api";

export type HomeStats = {
  assigned: number;
  returned: number;
  selfClaimPool: number;
  ready: number;
  sourceTodo: number;
  pendingAssign: number;
  pendingReview: number;
};

export type HomeMetricView = "source" | "pool" | "assign" | "claim" | "review" | "stock" | "research" | "listing";

export type ListingWorkbenchPreset = {
  scenario: "listing" | "observation";
  businessStatus: "pending_listing" | "pending_review";
  status: "" | "pending_review";
};

export type SecondaryResearchPreset = {
  scenario: "pending";
  periodFilter: "__all__";
};

export type HomeMetricItem = {
  label: string;
  value: number;
  view: HomeMetricView;
  listingPreset?: ListingWorkbenchPreset;
  researchPreset?: SecondaryResearchPreset;
};

export const EMPTY_DASHBOARD_COUNTS: DashboardCounts = {
  waiting_listing: 0,
  waiting_secondary_research: 0,
  pending_review_periods: 0
};

const RESEARCH_PRESET: SecondaryResearchPreset = { scenario: "pending", periodFilter: "__all__" };
const LISTING_TASK_PRESET: ListingWorkbenchPreset = { scenario: "listing", businessStatus: "pending_listing", status: "" };
const PENDING_REVIEW_PRESET: ListingWorkbenchPreset = { scenario: "observation", businessStatus: "pending_review", status: "pending_review" };

export function roleHomeMetrics(
  role: "operator" | "manager",
  stats: HomeStats,
  counts: DashboardCounts
): HomeMetricItem[] {
  const downstream: HomeMetricItem[] = [
    { label: "待二次调研", value: counts.waiting_secondary_research, view: "research", researchPreset: RESEARCH_PRESET },
    { label: "待刊登", value: counts.waiting_listing, view: "listing", listingPreset: LISTING_TASK_PRESET },
    { label: "待复盘", value: counts.pending_review_periods, view: "listing", listingPreset: PENDING_REVIEW_PRESET }
  ];
  if (role === "operator") {
    return [
      { label: "待认领", value: stats.assigned, view: "claim" },
      { label: "待补充", value: stats.returned, view: "claim" },
      { label: "可自认领", value: stats.selfClaimPool, view: "pool" },
      { label: "已通过", value: stats.ready, view: "stock" },
      ...downstream
    ];
  }
  return [
    { label: "待导入", value: stats.sourceTodo, view: "source" },
    { label: "待分配", value: stats.pendingAssign, view: "assign" },
    { label: "待复核", value: stats.pendingReview, view: "review" },
    { label: "可导出", value: stats.ready, view: "stock" },
    ...downstream
  ];
}
