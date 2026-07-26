type SnapshotItem = {
  source_type?: string | null;
  snapshot?: Record<string, unknown> | null;
};

export type StructuredCompetitorRow = {
  label: string;
  linkColumn: string;
  priceColumn: string;
  salesColumn: string;
  link: string;
  price: string;
  sales: string;
};

const competitorKindLabels: Record<string, string> = {
  lowest_price: "最低价",
  most_orders: "月销最高",
  second_orders: "月销次高",
  third_orders: "月销第三高",
  new_arrival: "新晋"
};

const marketSourceColumns: Record<string, readonly [string, string, string]> = {
  lowest_price: ["R", "S", "T"],
  most_orders: ["U", "V", "W"],
  new_arrival: ["X", "Y", "Z"]
};

export function isHistoricalArchiveItem(item: SnapshotItem) {
  return item.source_type === "historical_market_monitor_archive" || snapshotOf(item).archive_type === "historical_market_monitor";
}

export function structuredCompetitorRows(item: SnapshotItem): StructuredCompetitorRow[] {
  const snapshot = snapshotOf(item);
  const market = isRecord(snapshot.market_source) ? snapshot.market_source : {};
  const marketRows = competitorEntryRows(market.competitors, true);
  if (marketRows.length) return marketRows;
  const development = isRecord(snapshot.development_source) ? snapshot.development_source : {};
  return competitorEntryRows(development.competitors, false);
}

export function snapshotDirectColumnText(item: SnapshotItem, column: string) {
  const snapshot = snapshotOf(item);
  const fields = isRecord(snapshot.fields_by_column) ? snapshot.fields_by_column : {};
  const cells = isRecord(snapshot.cells) ? snapshot.cells : {};
  return valueText(fields[column]) || valueText(cells[column]);
}

export type DevelopmentSourceV2Row = {
  column: string;
  label: string;
  value: string;
};

export type DevelopmentSourceV2Section = {
  businessPeriod: string;
  rows: DevelopmentSourceV2Row[];
};

export function developmentSourceV2Section(item: SnapshotItem, keywords: readonly string[]): DevelopmentSourceV2Section | null {
  if (!isHistoricalArchiveItem(item)) return null;
  const source = snapshotOf(item).development_source_v2;
  if (!isRecord(source)) return null;
  const segments = isRecord(source.segments) ? source.segments : {};
  const rows: DevelopmentSourceV2Row[] = [];
  for (const [segmentName, entries] of Object.entries(segments)) {
    if (!keywords.some((keyword) => segmentName.includes(keyword)) || !Array.isArray(entries)) continue;
    for (const entry of entries.filter(isRecord)) {
      const value = valueText(entry.value);
      if (!value) continue;
      rows.push({ column: valueText(entry.column), label: valueText(entry.label), value });
    }
  }
  if (!rows.length) return null;
  return { businessPeriod: valueText(source.business_period), rows };
}

function competitorEntryRows(value: unknown, fromMarketSource: boolean): StructuredCompetitorRow[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter(isRecord)
    .map((entry) => {
      const kind = typeof entry.kind === "string" ? entry.kind : "";
      const columns = fromMarketSource ? marketSourceColumns[kind] : undefined;
      return {
        label: competitorKindLabels[kind] || kind || "-",
        linkColumn: columns?.[0] || "—",
        priceColumn: columns?.[1] || "—",
        salesColumn: columns?.[2] || "—",
        link: valueText(entry.url),
        price: valueText(entry.price),
        sales: valueText(entry.monthly_sales)
      };
    })
    .filter((row) => row.link || row.price || row.sales);
}

function snapshotOf(item: SnapshotItem): Record<string, unknown> {
  return isRecord(item.snapshot) ? item.snapshot : {};
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function valueText(value: unknown) {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value.trim();
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
}
