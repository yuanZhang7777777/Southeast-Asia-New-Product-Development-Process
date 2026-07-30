import type { ProductBoardGroup } from "./api";

export type ProductBoardFilters = {
  query?: string;
  businessPeriod?: string;
  owner?: string;
  status?: string;
  site?: string;
};

export type ProductBoardRow = ProductBoardGroup & {
  childCount: number;
  responsibilityCount: number;
  owners: string[];
  ownersText: string;
  statuses: string[];
};

export const PRODUCT_BOARD_RENDER_STEP = 50;

export const productBoardStatusMeta: Record<string, { label: string; klass: string }> = {
  pending_assignment: { label: "待分配", klass: "amber" },
  open_claim_pool: { label: "财根机会池", klass: "amber" },
  assigned: { label: "待认领", klass: "amber" },
  returned_for_supplement: { label: "待补充", klass: "red" },
  claim_submitted: { label: "待复核认领", klass: "amber" },
  claim_rejected: { label: "待复核不认领", klass: "red" },
  ready_for_stocking: { label: "可备货", klass: "green" },
  waiting_stocking_request: { label: "待填备货申请", klass: "amber" },
  waiting_export: { label: "待导出", klass: "blue" },
  stocking_paused: { label: "暂不推进", klass: "gray" },
  waiting_arrival: { label: "待到货", klass: "blue" },
  waiting_secondary_research: { label: "待二次调研", klass: "amber" },
  waiting_listing: { label: "待刊登", klass: "blue" },
  listing_observation: { label: "刊登观察中", klass: "blue" },
  confirmed_not_claim: { label: "已确认不认领", klass: "gray" },
  disabled: { label: "已停用", klass: "gray" }
};

export function buildProductBoardRows(groups: ProductBoardGroup[]): ProductBoardRow[] {
  return groups.map((group) => {
    const owners = unique(group.responsibilities.map((item) => item.salesperson_name).filter(Boolean) as string[]);
    const statuses = unique([
      ...group.child_skus.map((item) => item.visible_status),
      ...group.responsibilities.map((item) => item.visible_status)
    ].filter(Boolean));
    return {
      ...group,
      childCount: group.child_skus.length,
      responsibilityCount: group.responsibilities.length,
      owners,
      ownersText: owners.join("、") || "-",
      statuses
    };
  });
}

export function filterProductBoardRows(rows: ProductBoardRow[], filters: ProductBoardFilters): ProductBoardRow[] {
  const needle = normalize(filters.query || "");
  return rows
    .map((row) => {
      let responsibilities = row.responsibilities;
      if (filters.owner) responsibilities = responsibilities.filter((item) => item.salesperson_name === filters.owner);
      if (filters.status) responsibilities = responsibilities.filter((item) => item.visible_status === filters.status);
      return { ...row, responsibilities, responsibilityCount: responsibilities.length };
    })
    .filter((row) => {
      if (filters.businessPeriod && row.business_period !== filters.businessPeriod) return false;
      if (filters.site && (row.site || row.country || "") !== filters.site) return false;
      if ((filters.owner || filters.status) && !row.responsibilities.length) return false;
      if (!needle) return true;
      return normalize([
        row.business_period,
        row.site,
        row.country,
        row.main_sku,
        row.main_sku_name,
        row.child_skus.map((item) => `${item.sub_sku} ${item.sub_sku_name || ""}`).join(" "),
        row.responsibilities.map((item) => `${item.salesperson_name || ""} ${productBoardStatusLabel(item.visible_status)}`).join(" ")
      ].join(" ")).includes(needle);
    });
}

export function limitProductBoardRows<T>(rows: T[], limit: number): T[] {
  return rows.slice(0, Math.max(0, limit));
}

export function hasMultipleOwners(group: Pick<ProductBoardGroup, "responsibilities">): boolean {
  return unique(group.responsibilities.map((item) => item.salesperson_name).filter(Boolean) as string[]).length > 1;
}

export function productBoardStatusLabel(status: string) {
  return productBoardStatusMeta[status]?.label || status;
}

export function unique(values: string[]) {
  return Array.from(new Set(values)).sort();
}

function normalize(value: string) {
  return value.toLowerCase().replace(/\s+/g, "");
}
