export type OpportunityGroupItem = {
  source_type?: string | null;
  batch?: string | null;
  site?: string | null;
  country?: string | null;
  main_sku: string;
};

export function groupByBusinessIdentity<T extends OpportunityGroupItem>(items: readonly T[]) {
  const groups = new Map<string, T[]>();
  for (const item of items) {
    const key = [
      item.source_type || "",
      item.batch || "",
      normalizeSiteText(item.site || item.country),
      item.main_sku
    ].join("|");
    const group = groups.get(key) || [];
    group.push(item);
    groups.set(key, group);
  }
  return Array.from(groups, ([key, groupItems]) => ({ key, items: groupItems }));
}

// 别名表提到模块级：normalizeSiteText 在大列表匹配里按行调用，避免每次调用重建对象。
const siteAliases: Record<string, string> = {
  菲律宾: "PH",
  菲: "PH",
  PH: "PH",
  泰国: "TH",
  泰: "TH",
  TH: "TH",
  越南: "VN",
  越: "VN",
  VN: "VN",
  马来西亚: "MY",
  马来: "MY",
  MY: "MY",
  新加坡: "SG",
  SG: "SG",
  印度尼西亚: "ID",
  印尼: "ID",
  ID: "ID"
};

export function normalizeSiteText(value?: string | null) {
  const text = value?.trim();
  if (!text) return "";
  const upper = text.toUpperCase();
  return siteAliases[text] || siteAliases[upper] || upper;
}
