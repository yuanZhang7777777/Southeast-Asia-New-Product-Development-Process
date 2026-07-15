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

export function normalizeSiteText(value?: string | null) {
  const text = value?.trim();
  if (!text) return "";
  const upper = text.toUpperCase();
  const aliases: Record<string, string> = {
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
  return aliases[text] || aliases[upper] || upper;
}
