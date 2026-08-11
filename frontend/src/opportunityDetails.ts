// 商品列表接口不再返回 snapshot（源表快照重载字段），详情视图按需 GET /opportunities/{id} 补齐。
// 这里是补齐逻辑的纯函数部分：挑出待取明细的行、把已取到的快照重新贴回新一轮列表数据。

export type OpportunityDetailRow = {
  id: string;
  snapshot?: Record<string, unknown>;
  historical_claims?: unknown[];
};

export type OpportunityDetailCacheEntry = {
  snapshot?: Record<string, unknown>;
  historical_claims?: unknown[];
};

type OpportunityDetailCacheValue = OpportunityDetailCacheEntry | Record<string, unknown>;

export function opportunityDetailCacheEntry(detail: OpportunityDetailRow): OpportunityDetailCacheEntry {
  return {
    snapshot: detail.snapshot || {},
    historical_claims: detail.historical_claims
  };
}

function normalizeCacheEntry(cached: OpportunityDetailCacheValue | undefined): OpportunityDetailCacheEntry | undefined {
  if (!cached) return undefined;
  if ("snapshot" in cached || "historical_claims" in cached) return cached as OpportunityDetailCacheEntry;
  return { snapshot: cached };
}

export function idsNeedingDetail<T extends OpportunityDetailRow>(
  items: readonly T[],
  pending: ReadonlySet<string>,
  cache: ReadonlyMap<string, OpportunityDetailCacheValue>
): string[] {
  return items
    .filter((item) => item.snapshot === undefined && normalizeCacheEntry(cache.get(item.id))?.snapshot === undefined && !pending.has(item.id))
    .map((item) => item.id);
}

export function attachCachedSnapshots<T extends OpportunityDetailRow>(
  items: readonly T[],
  cache: ReadonlyMap<string, OpportunityDetailCacheValue>
): T[] {
  return items.map((item) => {
    const cached = normalizeCacheEntry(cache.get(item.id));
    if (!cached) return item;
    const patch: Partial<OpportunityDetailRow> = {};
    if (item.snapshot === undefined && cached.snapshot !== undefined) patch.snapshot = cached.snapshot;
    if (cached.historical_claims !== undefined) patch.historical_claims = cached.historical_claims;
    return Object.keys(patch).length ? { ...item, ...patch } : item;
  });
}

export function hasFullDetail(item: OpportunityDetailRow | null | undefined): boolean {
  return Boolean(item && item.snapshot !== undefined);
}
