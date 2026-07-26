import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { developmentSourceV2Section, isHistoricalArchiveItem, snapshotDirectColumnText, structuredCompetitorRows } from "../src/historicalSnapshot.ts";

const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");

const archiveMarketItem = {
  source_type: "historical_market_monitor_archive",
  snapshot: {
    archive_type: "historical_market_monitor",
    market_source: {
      competitors: [
        { kind: "lowest_price", url: "https://shopee.ph/item-1", price: 199, monthly_sales: 320 },
        { kind: "most_orders", url: "https://shopee.ph/item-2", price: 259, monthly_sales: 980 },
        { kind: "new_arrival", url: "https://shopee.ph/item-3", price: null, monthly_sales: 45 }
      ]
    }
  }
};

const archiveDevelopmentItem = {
  source_type: "historical_market_monitor_archive",
  snapshot: {
    archive_type: "historical_market_monitor",
    market_source: { competitors: [] },
    development_source: {
      pricing_snapshot: { stable_price: 155, stable_margin: 0.31 },
      competitors: [
        { kind: "lowest_price", url: "https://dev.example/1", price: 100, monthly_sales: 10 },
        { kind: "most_orders", url: "https://dev.example/2", price: 110, monthly_sales: 90 },
        { kind: "second_orders", url: "https://dev.example/3", price: 120, monthly_sales: 80 },
        { kind: "third_orders", url: "https://dev.example/4", price: 130, monthly_sales: 70 },
        { kind: "new_arrival", url: "https://dev.example/5", price: 140, monthly_sales: 5 }
      ]
    }
  }
};

const selection1Item = {
  source_type: "selection1_market_monitor",
  snapshot: {
    cells: { AQ: "12.5", AR: "88" },
    fields_by_column: { AQ: "13.5" },
    fields_by_header: { 最低价链接: "https://shopee.ph/legacy" },
    headers_by_column: { Z: ["最低价链接"] }
  }
};

test("档案商品优先输出 market_source 三组竞品并标注 R/S/T、U/V/W、X/Y/Z 列位", () => {
  assert.deepEqual(structuredCompetitorRows(archiveMarketItem), [
    { label: "最低价", linkColumn: "R", priceColumn: "S", salesColumn: "T", link: "https://shopee.ph/item-1", price: "199", sales: "320" },
    { label: "月销最高", linkColumn: "U", priceColumn: "V", salesColumn: "W", link: "https://shopee.ph/item-2", price: "259", sales: "980" },
    { label: "新晋", linkColumn: "X", priceColumn: "Y", salesColumn: "Z", link: "https://shopee.ph/item-3", price: "", sales: "45" }
  ]);
});

test("market_source 竞品为空时回落 development_source 五组且列位显示 —", () => {
  const rows = structuredCompetitorRows(archiveDevelopmentItem);
  assert.deepEqual(
    rows.map((row) => row.label),
    ["最低价", "月销最高", "月销次高", "月销第三高", "新晋"]
  );
  assert.ok(rows.every((row) => row.linkColumn === "—" && row.priceColumn === "—" && row.salesColumn === "—"));
  assert.equal(rows[2].link, "https://dev.example/3");
  assert.equal(rows[2].price, "120");
  assert.equal(rows[2].sales, "80");
});

test("选品1 商品结构化竞品为空，仍走原有表头别名路径", () => {
  assert.deepEqual(structuredCompetitorRows(selection1Item), []);
  assert.equal(isHistoricalArchiveItem(selection1Item), false);
  assert.match(appSource, /const structured = structuredCompetitorRows\(item\);\s*\n\s*if \(structured\.length\) return structured;\s*\n\s*return competitorSpecs/);
});

test("成本参数取值只读 fields_by_column 与 cells，不吃 development_source 兜底", () => {
  assert.equal(snapshotDirectColumnText(selection1Item, "AQ"), "13.5");
  assert.equal(snapshotDirectColumnText(selection1Item, "AR"), "88");
  assert.equal(snapshotDirectColumnText(archiveDevelopmentItem, "AQ"), "");
  const tableStart = appSource.indexOf("function ColumnRangeTable");
  const tableEnd = appSource.indexOf("function CompetitorTable", tableStart);
  const columnRangeTable = appSource.slice(tableStart, tableEnd);
  assert.ok(tableStart >= 0 && tableEnd > tableStart);
  assert.match(columnRangeTable, /snapshotDirectColumnText\(props\.item, column\)/);
  assert.doesNotMatch(columnRangeTable, /snapshotColumnText/);
  assert.match(appSource, /return snapshotColumnText\(item, fallbackColumn\);/);
});

test("档案来源空态文案与选品1 空态文案区分", () => {
  assert.equal(isHistoricalArchiveItem(archiveMarketItem), true);
  assert.equal(isHistoricalArchiveItem({ snapshot: { archive_type: "historical_market_monitor" } }), true);
  assert.match(appSource, /isHistoricalArchiveItem\(props\.item\) \? "来源无此字段：市场监控源无成本参数（AQ-BR）列位" : "暂无成本参数字段。"/);
  assert.match(appSource, /isHistoricalArchiveItem\(props\.item\) \? "市场监控源 R~Z 上游为空" : "源表 Z:AN 暂无竞品链接、售价或月销。"/);
});

const archiveV2Item = {
  source_type: "historical_market_monitor_archive",
  snapshot: {
    archive_type: "historical_market_monitor",
    development_source_v2: {
      business_period: "开发0602期",
      segments: {
        开发询价: [
          { column: "M", label: "产品规格", value: "60x40x30cm" },
          { column: "N", label: "询价结果", value: "12.5" },
          { column: "O", label: "备注", value: "" }
        ],
        成本参数: [
          { column: "AQ", label: "采购成本", value: "8.8" },
          { column: "AR", label: "头程运费", value: "1.2" }
        ],
        "价格/毛利": [{ column: "AO", label: "售价", value: "19.9" }]
      }
    }
  }
};

test("档案 development_source_v2 按分组名关键字输出列/字段/值行与期数", () => {
  const cost = developmentSourceV2Section(archiveV2Item, ["成本"]);
  assert.equal(cost?.businessPeriod, "开发0602期");
  assert.deepEqual(cost?.rows, [
    { column: "AQ", label: "采购成本", value: "8.8" },
    { column: "AR", label: "头程运费", value: "1.2" }
  ]);

  const development = developmentSourceV2Section(archiveV2Item, ["询价", "规格"]);
  assert.deepEqual(development?.rows.map((row) => row.label), ["产品规格", "询价结果"]);
  assert.equal(development?.businessPeriod, "开发0602期");
});

test("无 development_source_v2 或非档案来源回落现有路径", () => {
  assert.equal(developmentSourceV2Section(selection1Item, ["成本"]), null);
  assert.equal(developmentSourceV2Section(archiveMarketItem, ["成本"]), null);
  assert.equal(developmentSourceV2Section(archiveV2Item, ["市场"]), null);
});

test("商品详情成本参数与开发询价模块接入 v2 段并标注三国表来源", () => {
  assert.match(appSource, /developmentSourceV2Section\(activeChild, \["成本"\]\)/);
  assert.match(appSource, /developmentSourceV2Section\(activeChild, \["询价", "规格"\]\)/);
  assert.match(appSource, /三国表·\{archiveSection\.businessPeriod\}/);
  assert.match(appSource, /archiveSection \? \(\s*<ArchiveSegmentTable section=\{archiveSection\} \/>\s*\) : \(\s*<ColumnRangeTable item=\{activeChild\} columns=\{costParameterColumns\} \/>/);
  assert.match(appSource, /archiveSection \? \(\s*<ArchiveSegmentTable section=\{archiveSection\} \/>\s*\) : \(\s*<DetailFieldGrid item=\{activeChild\} specs=\{developmentFieldSpecs\} \/>/);
});
