type DetailGroup = { key: string; items: { id: string }[] };

export function adjacentDetailTarget(
  groups: DetailGroup[],
  currentGroupKey: string,
  currentChildId: string,
  delta: -1 | 1
): { groupKey: string; childId: string } | null {
  const sequence = groups.flatMap((group) => group.items.map((item) => ({ groupKey: group.key, childId: item.id })));
  const currentIndex = sequence.findIndex(
    (item) => item.groupKey === currentGroupKey && item.childId === currentChildId
  );
  return currentIndex < 0 ? null : sequence[currentIndex + delta] || null;
}
