export type AssignmentFilter = {
  query?: string;
  site?: string;
  category?: string;
  operator?: string;
};

export type AssignmentFilterItem = {
  main_sku: string;
  suggested_assignee?: string | null;
  opportunity_ids: string[];
};

export type AssignmentFilterOpportunity = {
  id: string;
  main_sku: string;
  sub_sku: string;
  main_sku_name?: string | null;
  sub_sku_name?: string | null;
  site?: string | null;
  country?: string | null;
  category_level1?: string | null;
};

export type AssignmentFilterGroup<T extends AssignmentFilterOpportunity = AssignmentFilterOpportunity> = {
  items: T[];
};

export type SortableOperatorProfile = {
  id: string;
  operator_name: string;
  key_site?: string | null;
  display_order?: number | null;
};

export function assignmentFilterItemKey(item: AssignmentFilterItem) {
  return item.opportunity_ids.length ? [...item.opportunity_ids].sort().join("|") : item.main_sku;
}

export function filterAssignmentItems<
  TItem extends AssignmentFilterItem,
  TOpportunity extends AssignmentFilterOpportunity
>(
  items: readonly TItem[],
  groups: readonly AssignmentFilterGroup<TOpportunity>[],
  drafts: Record<string, string>,
  filter: AssignmentFilter
): TItem[] {
  const tokens = (filter.query || "").trim().split(/\s+/).map(normalize).filter(Boolean);
  return items.filter((item) => {
    const group = groups.find((entry) => entry.items.some((opportunity) => item.opportunity_ids.includes(opportunity.id)));
    const opportunities = group?.items || [];
    if (filter.site && !opportunities.some((opportunity) => normalizeSiteText(opportunity.site || opportunity.country) === normalizeSiteText(filter.site))) return false;
    if (filter.category && !opportunities.some((opportunity) => (opportunity.category_level1 || "").trim() === filter.category)) return false;
    const selectedOperator = drafts[assignmentFilterItemKey(item)];
    if (filter.operator && ![item.suggested_assignee, selectedOperator].includes(filter.operator)) return false;
    if (!tokens.length) return true;
    const haystack = normalize([
      item.main_sku,
      ...opportunities.flatMap((opportunity) => [
        opportunity.main_sku,
        opportunity.sub_sku,
        opportunity.main_sku_name,
        opportunity.sub_sku_name
      ])
    ].filter(Boolean).join(" "));
    return tokens.some((token) => haystack.includes(token));
  });
}

export function sortOperatorProfiles<T extends SortableOperatorProfile>(profiles: readonly T[]): T[] {
  return [...profiles].sort((left, right) => {
    const site = normalizeSiteText(left.key_site).localeCompare(normalizeSiteText(right.key_site), "zh-CN");
    if (site) return site;
    const order = (left.display_order ?? Number.MAX_SAFE_INTEGER) - (right.display_order ?? Number.MAX_SAFE_INTEGER);
    return order || left.operator_name.localeCompare(right.operator_name, "zh-CN");
  });
}

export function groupOperatorProfilesBySite<T extends SortableOperatorProfile>(profiles: readonly T[]) {
  const groups = new Map<string, T[]>();
  for (const profile of sortOperatorProfiles(profiles)) {
    const site = normalizeSiteText(profile.key_site) || "未配置站点";
    groups.set(site, [...(groups.get(site) || []), profile]);
  }
  return Array.from(groups, ([site, items]) => ({ site, items }));
}

export function moveOperatorWithinSite<T extends SortableOperatorProfile>(profiles: readonly T[], profileId: string, delta: -1 | 1): T[] {
  const target = profiles.find((profile) => profile.id === profileId);
  if (!target) return [...profiles];
  const site = normalizeSiteText(target.key_site);
  const group = sortOperatorProfiles(profiles.filter((profile) => normalizeSiteText(profile.key_site) === site));
  const index = group.findIndex((profile) => profile.id === profileId);
  const nextIndex = index + delta;
  if (index < 0 || nextIndex < 0 || nextIndex >= group.length) return [...profiles];
  [group[index], group[nextIndex]] = [group[nextIndex], group[index]];
  const orderById = new Map(group.map((profile, groupIndex) => [profile.id, groupIndex + 1]));
  return profiles.map((profile) => ({ ...profile, display_order: orderById.get(profile.id) ?? profile.display_order }));
}

function normalize(value: string) {
  return value.toLowerCase().replace(/\s+/g, "");
}

function normalizeSiteText(value?: string | null) {
  const text = value?.trim();
  if (!text) return "";
  const upper = text.toUpperCase();
  const aliases: Record<string, string> = {
    菲律宾: "PH",
    菲: "PH",
    泰国: "TH",
    泰: "TH",
    越南: "VN",
    越: "VN",
    马来西亚: "MY",
    马来: "MY",
    新加坡: "SG",
    印度尼西亚: "ID",
    印尼: "ID"
  };
  return aliases[text] || aliases[upper] || upper;
}
