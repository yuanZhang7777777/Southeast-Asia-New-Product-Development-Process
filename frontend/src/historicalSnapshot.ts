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

export type HistoryCellField = {
  column: string;
  label: string;
  group: string;
  value: string;
};

export type HistoryCellSectionKey = "development" | "market" | "pricing" | "cost" | "other";

export type HistoryCellSections = Record<HistoryCellSectionKey, HistoryCellField[]>;

export function isHistorySelection1Item(item: SnapshotItem) {
  return item.source_type === "history_selection1" || snapshotOf(item).archive_type === "historical_selection1";
}

// 列位兜底（Z-AN 竞品、AO-AX 定价、AQ-BR 成本等）只对真正是选品1列布局的来源成立；
// 选品2 等其它布局的同列位含义完全不同（如 AL-AN 是认领区），必须按真实表头取数。
export function hasSelection1ColumnLayout(item: SnapshotItem) {
  return item.source_type === "selection1_developer_claim_feedback";
}

export function isSelection2Item(item: SnapshotItem) {
  return item.source_type === "selection2_caigen_claim_feedback";
}

export type Selection2SectionKey = "market" | "pricing" | "cost";

const selection2SectionKeywords: Record<Selection2SectionKey, readonly string[]> = {
  market: ["低价高消", "最新低价", "最低价链接"],
  pricing: ["进价", "SP上家", "SP上架", "定价", "销售成本", "利润额", "利润率"],
  cost: ["海运", "操作费", "费率", "进货运费"]
};

// 选品2 按自己的真实表头（headers_by_column）挑出板块相关字段；非选品2 来源返回空。
export function selection2HeaderFields(item: SnapshotItem, section: Selection2SectionKey): HistoryCellField[] {
  if (!isSelection2Item(item)) return [];
  const snapshot = snapshotOf(item);
  const headersByColumn = isRecord(snapshot.headers_by_column) ? snapshot.headers_by_column : {};
  const fieldsByColumn = isRecord(snapshot.fields_by_column) ? snapshot.fields_by_column : {};
  const cells = isRecord(snapshot.cells) ? snapshot.cells : {};
  const keywords = selection2SectionKeywords[section];
  const rows: HistoryCellField[] = [];
  const columns = Object.keys(headersByColumn).sort((left, right) => columnNumber(left) - columnNumber(right));
  for (const column of columns) {
    const label = headerText(headersByColumn[column]);
    if (!label || !keywords.some((keyword) => label.includes(keyword))) continue;
    const value = valueText(fieldsByColumn[column]) || valueText(cells[column]);
    if (!value) continue;
    rows.push({ column, label, group: "", value });
  }
  return rows;
}

function headerText(value: unknown) {
  if (Array.isArray(value)) return value.map(valueText).filter(Boolean).join(" / ");
  return valueText(value);
}

// 选品1历史档案：把 fields_by_cell（{列字母: {header, group, value}}）按 R1 分组名归入详情板块。
// 旧世代（generation=old）行分组可能缺失，缺失或未识别分组落入 other（基础信息底部折叠区）。
export function historyFieldsByCellSections(item: SnapshotItem): HistoryCellSections | null {
  if (!isHistorySelection1Item(item)) return null;
  const cells = snapshotOf(item).fields_by_cell;
  if (!isRecord(cells)) return null;
  const sections: HistoryCellSections = { development: [], market: [], pricing: [], cost: [], other: [] };
  const columns = Object.keys(cells).sort((left, right) => columnNumber(left) - columnNumber(right));
  for (const column of columns) {
    const cell = cells[column];
    if (!isRecord(cell)) continue;
    const value = valueText(cell.value);
    if (!value) continue;
    const group = valueText(cell.group);
    const label = valueText(cell.header) || group || column;
    const section = historyFieldSection(label, group);
    if (section === null) continue;
    sections[section].push({ column, label, group, value });
  }
  if (!Object.values(sections).some((rows) => rows.length)) return null;
  return sections;
}

// R1 分组是合并单元格前向填充，认领区/总结列常被打上邻组名（如"开发是否接受核价结果"）——
// 这两类按表头先行排除，其余仍按分组归类。
function historyFieldSection(label: string, group: string): HistoryCellSectionKey | null {
  // 认领区字段不进通用板块：由认领事实回填生成真正的认领记录，在"认领与复核"展示。
  if (/主销售员|是否认领|认领单销|不认领理由|不认领原因/.test(label)) return null;
  if (/总结|复盘/.test(label)) return "other";
  // 定价/毛利/利润率/单销等财务表头即使被 R1 前向填充打上"市场调研"分组也归价格参考
  // （2026-07 用户口径）；含"竞品"的表头（竞品单价/竞品月销）不受影响，仍走分组判定。
  if (!label.includes("竞品") && /定价|毛利|利润率|单销/.test(label)) return "pricing";
  if (!group) return "other";
  if (group.includes("询价")) return "development";
  if (group.includes("调研") || group.includes("竞品")) return "market";
  if (group.includes("定价") || group.includes("利润") || group.includes("汇总")) return "pricing";
  if (group.includes("核") || group.includes("成本")) return "cost";
  return "other";
}

export type HistoryMarketView = {
  competitors: StructuredCompetitorRow[];
  extras: HistoryCellField[];
};

// 市场调研字段里按顺序识别 链接(URL 值)→售价→月销 三元组渲染竞品行；识别不了的字段留在 extras 走通用标签值列表。
export function historyMarketView(fields: HistoryCellField[]): HistoryMarketView {
  const competitors: StructuredCompetitorRow[] = [];
  const extras: HistoryCellField[] = [];
  let current: StructuredCompetitorRow | null = null;
  for (const field of fields) {
    if (/^https?:\/\//i.test(field.value)) {
      current = {
        label: historyCompetitorLabel(field.label, field.column),
        linkColumn: field.column,
        priceColumn: "—",
        salesColumn: "—",
        link: field.value,
        price: "",
        sales: ""
      };
      competitors.push(current);
      continue;
    }
    if (current && !current.price && /售价|单价/.test(field.label)) {
      current.price = field.value;
      current.priceColumn = field.column;
      continue;
    }
    if (current && !current.sales && /月销/.test(field.label)) {
      current.sales = field.value;
      current.salesColumn = field.column;
      continue;
    }
    current = null;
    extras.push(field);
  }
  return { competitors, extras };
}

function historyCompetitorLabel(label: string, column: string) {
  return label.replace(/链接\d*/g, "").trim() || column;
}

function columnNumber(column: string) {
  return column.split("").reduce((total, char) => total * 26 + char.charCodeAt(0) - 64, 0);
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
