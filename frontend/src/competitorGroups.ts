const groups = [
  { key: "lowest", label: "最低价", aliases: ["最低价"], columns: ["Z", "AA", "AB"] },
  { key: "most-orders", label: "月销最高", aliases: ["月销最高", "Most orders", "most_orders"], columns: ["AC", "AD", "AE"] },
  { key: "second", label: "月销次高", aliases: ["月销次高"], columns: ["AF", "AG", "AH"] },
  { key: "third", label: "月销第三高", aliases: ["月销第三高"], columns: ["AI", "AJ", "AK"] },
  { key: "new", label: "新晋", aliases: ["新晋"], columns: ["AL", "AM", "AN"] }
] as const;

export type CompetitorGroup = { key: string; label: string };

export function competitorGroupForColumn(column: string): CompetitorGroup | undefined {
  const group = groups.find((item) => (item.columns as readonly string[]).includes(column.toUpperCase()));
  return group ? { key: group.key, label: group.label } : undefined;
}

export function competitorGroupForLabel(label: string): CompetitorGroup | undefined {
  const normalized = label.trim().toLowerCase();
  const group = groups.find((item) => item.aliases.some((alias) => alias.toLowerCase() === normalized));
  return group ? { key: group.key, label: group.label } : undefined;
}
