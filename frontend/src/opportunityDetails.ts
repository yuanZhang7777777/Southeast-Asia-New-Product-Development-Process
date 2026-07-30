// 商品列表接口不再返回 snapshot（源表快照重载字段），详情视图按需 GET /opportunities/{id} 补齐。
// 这里是补齐逻辑的纯函数部分：挑出待取明细的行、把已取到的快照重新贴回新一轮列表数据。

export type OpportunityDetailRow = {
  id: string;
  snapshot?: Record<string, unknown>;
};

export function idsNeedingDetail<T extends OpportunityDetailRow>(
  items: readonly T[],
  pending: ReadonlySet<string>,
  cache: ReadonlyMap<string, Record<string, unknown>>
): string[] {
  return items
    .filter((item) => item.snapshot === undefined && !cache.has(item.id) && !pending.has(item.id))
    .map((item) => item.id);
}

export function attachCachedSnapshots<T extends OpportunityDetailRow>(
  items: readonly T[],
  cache: ReadonlyMap<string, Record<string, unknown>>
): T[] {
  return items.map((item) => {
    if (item.snapshot !== undefined) return item;
    const snapshot = cache.get(item.id);
    return snapshot ? { ...item, snapshot } : item;
  });
}

export function hasFullDetail(item: OpportunityDetailRow | null | undefined): boolean {
  return Boolean(item && item.snapshot !== undefined);
}
