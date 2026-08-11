import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  developmentSourceV2Section,
  hasSelection1ColumnLayout,
  historyFieldsByCellSections,
  historyMarketView,
  isHistoricalArchiveItem,
  isHistorySelection1Item,
  selection2HeaderFields,
  snapshotDirectColumnText,
  structuredCompetitorRows
} from "../src/historicalSnapshot.ts";

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
  assert.match(
    appSource,
    /archiveSection \? \(\s*<ArchiveSegmentTable section=\{archiveSection\} \/>\s*\) : historyRows\.length \? \(\s*<ArchiveSegmentTable section=\{\{ businessPeriod: "", rows: historyRows \}\} \/>\s*\) : \(\s*<ColumnRangeTable item=\{activeChild\} columns=\{costParameterColumns\} \/>/
  );
  assert.match(
    appSource,
    /archiveSection \? \(\s*<ArchiveSegmentTable section=\{archiveSection\} \/>\s*\) : historyRows\.length \? \(\s*<ArchiveSegmentTable section=\{\{ businessPeriod: "", rows: historyRows \}\} \/>\s*\) : \(\s*<DetailFieldGrid item=\{activeChild\} specs=\{developmentFieldSpecs\} \/>/
  );
});

const historySelection1NewGenItem = {
  source_type: "history_selection1",
  snapshot: {
    archive_type: "historical_selection1",
    business_period: "开发0623期",
    fields_by_cell: {
      A: { header: "开品周期", group: "开品周期", value: "6.24-6.30" },
      N: { header: "产品规格", group: "开发询价", value: "箱规：42*32*28CM 50pcs" },
      Q: { header: "供应商链接", group: "开发询价", value: "https://detail.1688.com/offer/1" },
      AA: { header: "最低价链接", group: "Shopee菲律宾市场调研", value: "https://shopee.ph/lowest" },
      AB: { header: "售价1(PHP）", group: "Shopee菲律宾市场调研", value: 331 },
      AC: { header: "月销1", group: "Shopee菲律宾市场调研", value: 2 },
      AM: { header: "新晋链接", group: "Shopee菲律宾市场调研", value: "https://shopee.ph/new" },
      AN: { header: "售价3(PHP）", group: "Shopee菲律宾市场调研", value: 429 },
      AO: { header: "月销3", group: "Shopee菲律宾市场调研", value: 499 },
      AP: { header: "参考单销", group: "Shopee菲律宾市场调研", value: 6.68 },
      AX: { header: "稳定期总成本（PHP）", group: "Shopee菲律宾成本", value: 280.6 },
      BP: { header: "总预估单销", group: "汇总", value: 0 },
      BU: { header: "1pc空运头程费", group: "海空判断", value: 3.79 },
      BZ: { header: "采购   核价人", group: "供应链核/报价", value: "核价员A" },
      CA: { header: "核价意见", group: "供应链核/报价", value: "" }
    }
  }
};

const historySelection1OldGenItem = {
  source_type: "history_selection1",
  snapshot: {
    archive_type: "historical_selection1",
    generation: "old",
    fields_by_cell: {
      N: { header: "竞品单价\n（链接1）\n(比索）", group: "竞品单价\n（链接1）\n(比索）", value: 120 },
      O: { header: "竞品月销\n（链接1）", group: "竞品月销\n（链接1）", value: 30 },
      P: { header: "参考定价   （比索）", group: "参考定价   （比索）", value: 130 },
      Q: { header: "国内参考链接", group: "开发询价", value: "https://detail.1688.com/offer/1" },
      R: { header: "供应商名称", group: "开发询价", value: "唐山盈好" },
      S: { header: "备注", group: null, value: "旧世代无分组" }
    }
  }
};

test("选品1历史新世代 fields_by_cell 按 R1 分组归入板块且列序稳定", () => {
  assert.equal(isHistorySelection1Item(historySelection1NewGenItem), true);
  const sections = historyFieldsByCellSections(historySelection1NewGenItem);
  assert.ok(sections);
  assert.deepEqual(sections.development.map((field) => field.column), ["N", "Q"]);
  assert.deepEqual(sections.market.map((field) => field.column), ["AA", "AB", "AC", "AM", "AN", "AO"]);
  // AP 参考单销虽被 R1 前向填充打上"市场调研"分组，但按 2026-07 用户口径定价类表头归价格参考。
  assert.deepEqual(sections.pricing.map((field) => field.column), ["AP", "BP"]);
  assert.deepEqual(sections.cost.map((field) => field.column), ["AX", "BZ"]);
  assert.deepEqual(sections.other.map((field) => field.column), ["A", "BU"]);
  // 空值（CA）跳过，数字 0（BP）保留。
  assert.equal(sections.pricing[1].value, "0");
  assert.deepEqual(sections.development[0], { column: "N", label: "产品规格", group: "开发询价", value: "箱规：42*32*28CM 50pcs" });
});

test("选品1标准单层表头按固定列位完整进入四个详情分区", () => {
  const item = {
    source_type: "history_selection1",
    snapshot: {
      archive_type: "historical_selection1",
      source_schema: "selection1_standard_v20260729",
      fields_by_cell: {
        A: { header: "开品周期", group: "开品周期", value: "7.8-7.14" },
        N: { header: "产品规格", group: "产品规格", value: "黑色" },
        Z: { header: "采购链接", group: "采购链接", value: "https://detail.1688.com/offer/1" },
        AA: { header: "最低价链接", group: "最低价链接", value: "https://shopee.ph/lowest" },
        AB: { header: "售价1", group: "售价1", value: 298 },
        AC: { header: "月销1", group: "月销1", value: 543 },
        AP: { header: "参考单销", group: "参考单销", value: 1 },
        AW: { header: "推广期利润率", group: "推广期利润率", value: 0.21 },
        AX: { header: "稳定期总成本", group: "稳定期总成本", value: 260 },
        AY: { header: "包装重量", group: "包装重量", value: 1.2 },
        BZ: { header: "不认领理由", group: "不认领理由", value: "需要资质" },
        CE: { header: "备注", group: "备注", value: "认领证据" }
      }
    }
  };

  const sections = historyFieldsByCellSections(item);
  assert.ok(sections);
  assert.deepEqual(sections.development.map((field) => field.column), ["N", "Z"]);
  assert.deepEqual(sections.market.map((field) => field.column), ["AA", "AB", "AC"]);
  assert.deepEqual(sections.pricing.map((field) => field.column), ["AP", "AW"]);
  assert.deepEqual(sections.cost.map((field) => field.column), ["AX", "AY"]);
  assert.deepEqual(sections.other.map((field) => field.column), ["A"]);
});

test("历史选品3/4按选品1标准列完整分区，认领列只进认领模块", () => {
  const item = {
    source_type: "history_selection34",
    snapshot: {
      archive_type: "historical_selection34",
      fields_by_cell: {
        S: { header: "商品成本-含税（元）", value: 0.6729 },
        U: { header: "长(cm)", value: 18 },
        AA: { header: "最低价链接", value: "https://shopee.vn/lowest" },
        AB: { header: "售价1", value: 24500 },
        AC: { header: "月销1", value: 227 },
        AP: { header: "参考单销", value: 1 },
        AV: { header: "推广期定价", value: 28000 },
        AX: { header: "稳定期总成本（含头程+平台费+基础设施）", value: 12000 },
        CA: { header: "主销售员", value: "江琴" },
        CC: { header: "认领单销", value: 1 }
      }
    }
  };

  assert.equal(isHistorySelection1Item(item), true);
  const sections = historyFieldsByCellSections(item);
  assert.ok(sections);
  assert.deepEqual(sections.development.map((field) => field.column), ["S", "U"]);
  assert.deepEqual(sections.market.map((field) => field.column), ["AA", "AB", "AC"]);
  assert.deepEqual(sections.pricing.map((field) => field.column), ["AP", "AV"]);
  assert.deepEqual(sections.cost.map((field) => field.column), ["AX"]);
  assert.ok(!Object.values(sections).flat().some((field) => ["CA", "CC"].includes(field.column)));
  assert.match(appSource, /fields_by_cell/);
  assert.match(appSource, /activeChild\.source_type === "history_selection34"/);
});

test("现行选品1读取补回的历史字段快照", () => {
  const item = {
    source_type: "selection1_developer_claim_feedback",
    snapshot: { historical_selection1: historySelection1NewGenItem.snapshot }
  };
  assert.equal(isHistorySelection1Item(item), true);
  assert.deepEqual(historyFieldsByCellSections(item)?.development.map((field) => field.column), ["N", "Q"]);
});
test("商品详情把历史认领作为只读来源事实展示", () => {
  const claimPane = appSource.slice(appSource.indexOf('{activeSection === "claim"'), appSource.indexOf('{activeSection === "secondary"'));
  const claimTable = appSource.slice(appSource.indexOf("function ClaimReviewTable"), appSource.indexOf("function DetailFieldGrid"));
  const submissionHelper = appSource.slice(appSource.indexOf("const readOnlyHistoricalSourceTypes"), appSource.indexOf("type SkuEditDraft"));
  const detailView = appSource.slice(appSource.indexOf("function ProductDetailView"), appSource.indexOf("function lockedIdentitySourceColumns"));
  const historicalStatus = appSource.slice(appSource.indexOf("function historicalClaimStatus"), appSource.indexOf("function primaryActionLabel"));

  assert.match(claimPane, /historical_claims/);
  assert.match(claimTable, /来源期/);
  assert.match(claimTable, /来源行/);
  assert.match(claimTable, /<th>备注<\/th>/);
  assert.match(claimTable, /claim\.source_note/);
  assert.match(claimTable, /来源表未提供主管复核/);
  assert.match(submissionHelper, /history_selection2/);
  assert.match(submissionHelper, /history_selection34/);
  assert.match(submissionHelper, /isReadOnlyHistoricalItem\(item\)/);
  assert.match(detailView, /!isReadOnlyHistoricalItem\(activeChild\)/);
  assert.match(detailView, /detailOwnerText\(group\)/);
  assert.match(historicalStatus, /historical_claims/);
  assert.match(historicalStatus, /historical_unclaimed/);
  assert.match(historicalStatus, /source_claimed/);
  assert.match(historicalStatus, /source_not_claimed/);
  assert.doesNotMatch(claimTable, /latest_claim_record_id/);
  assert.doesNotMatch(claimTable, /api\.review/);
});

test("选品1历史旧世代（部分无分组）按竞品/定价/询价关键字归类，无分组落其他", () => {
  const sections = historyFieldsByCellSections(historySelection1OldGenItem);
  assert.ok(sections);
  assert.deepEqual(sections.market.map((field) => field.column), ["N", "O"]);
  assert.deepEqual(sections.pricing.map((field) => field.column), ["P"]);
  assert.deepEqual(sections.development.map((field) => field.column), ["Q", "R"]);
  assert.deepEqual(sections.other.map((field) => field.column), ["S"]);
  assert.deepEqual(sections.cost, []);
});

test("市场调研派生识别 链接/售价/月销 三元组为竞品行，识别不了的留通用列表", () => {
  const sections = historyFieldsByCellSections(historySelection1NewGenItem);
  assert.ok(sections);
  const view = historyMarketView(sections.market);
  assert.deepEqual(view.competitors, [
    { label: "最低价", linkColumn: "AA", priceColumn: "AB", salesColumn: "AC", link: "https://shopee.ph/lowest", price: "331", sales: "2" },
    { label: "新晋", linkColumn: "AM", priceColumn: "AN", salesColumn: "AO", link: "https://shopee.ph/new", price: "429", sales: "499" }
  ]);
  // AP 参考单销已改归价格参考板块，市场调研不再留通用字段。
  assert.deepEqual(view.extras.map((field) => field.column), []);
});

test("旧世代市场调研无链接值时全部走通用标签值列表", () => {
  const sections = historyFieldsByCellSections(historySelection1OldGenItem);
  assert.ok(sections);
  const view = historyMarketView(sections.market);
  assert.deepEqual(view.competitors, []);
  assert.deepEqual(view.extras.map((field) => field.column), ["N", "O"]);
});

test("定价类表头前向填充成市场调研分组时归价格参考，含竞品表头与无分组总结不受影响", () => {
  const item = {
    source_type: "history_selection1",
    snapshot: {
      archive_type: "historical_selection1",
      fields_by_cell: {
        AB: { header: "竞品单价\n（链接1）\n(比索）", group: "Shopee菲律宾市场调研", value: 120 },
        AC: { header: "竞品月销\n（链接1）", group: "Shopee菲律宾市场调研", value: 30 },
        AP: { header: "参考单销", group: "Shopee菲律宾市场调研", value: 6.68 },
        AQ: { header: "推广期定价", group: "Shopee菲律宾市场调研", value: 199 },
        AR: { header: "一次毛利额", group: "Shopee菲律宾市场调研", value: 35.2 },
        AS: { header: "稳定期利润率", group: "Shopee菲律宾市场调研", value: 0.21 },
        AT: { header: "预估单销", group: "Shopee菲律宾市场调研", value: 3.5 },
        BS: { header: "销售反馈总结", group: null, value: "四周销量平稳" }
      }
    }
  };
  const sections = historyFieldsByCellSections(item);
  assert.ok(sections);
  // 财务列（定价/毛利/利润率/单销）按用户口径进价格参考，不再落市场调研通用表。
  assert.deepEqual(sections.pricing.map((field) => field.column), ["AP", "AQ", "AR", "AS", "AT"]);
  // 竞品单价/竞品月销仍留在市场调研，不被定价表头判定误吸。
  assert.deepEqual(sections.market.map((field) => field.column), ["AB", "AC"]);
  // 销售反馈总结等无分组总结类字段落"其他源表字段"。
  assert.deepEqual(sections.other.map((field) => field.column), ["BS"]);
});

test("认领区与总结列不因前向填充分组混进成本参数板块", () => {
  const poisoned = {
    source_type: "history_selection1",
    snapshot: {
      archive_type: "historical_selection1",
      fields_by_cell: {
        BU: { header: "开发是否接受核价结果", group: "开发是否接受核价结果", value: "是" },
        BV: { header: "主销售员", group: "开发是否接受核价结果", value: "陈丽妹" },
        BW: { header: "是否认领", group: "开发是否接受核价结果", value: "是" },
        BX: { header: "认领单销", group: "开发是否接受核价结果", value: 0.5 },
        BY: { header: "不认领理由", group: "开发是否接受核价结果", value: "利润太低" },
        BZ: { header: "总结", group: "开发是否接受核价结果", value: "四周复盘总结" }
      }
    }
  };
  const sections = historyFieldsByCellSections(poisoned);
  assert.ok(sections);
  // 真正的核价字段留在成本参数；认领区被排除；总结落"其他"。
  assert.deepEqual(sections.cost.map((field) => field.column), ["BU"]);
  assert.deepEqual(sections.other.map((field) => field.column), ["BZ"]);
  const all = Object.values(sections).flat().map((field) => field.label);
  assert.ok(!all.includes("主销售员") && !all.includes("是否认领") && !all.includes("认领单销") && !all.includes("不认领理由"));
});

test("非选品1历史来源不产生 fields_by_cell 派生数据", () => {
  assert.equal(historyFieldsByCellSections(selection1Item), null);
  assert.equal(historyFieldsByCellSections(archiveMarketItem), null);
  assert.equal(historyFieldsByCellSections({ source_type: "history_selection1", snapshot: {} }), null);
});

const selection2Item = {
  source_type: "selection2_caigen_claim_feedback",
  snapshot: {
    headers_by_column: {
      H: ["进价"],
      L: ["海运"],
      Q: ["销售成本（比索）"],
      T: ["推广期SP利润率"],
      U: ["稳定期SP利润率"],
      X: ["审核"],
      Y: ["低价高消链接"],
      Z: ["低价高消链接数据"],
      AA: ["最新低价链接"],
      AB: ["最低价链接"],
      AL: ["开发表格认领情况--主销售员"],
      AM: ["是否认领"],
      AN: ["认领单销"]
    },
    cells: {
      H: 12.2,
      L: 1.2,
      Q: 125.57,
      T: -3.7,
      U: 0.1046,
      X: "竟对月销400左右",
      Y: "https://shopee.ph/cheap-hot",
      AA: "https://shopee.ph/newest-low",
      AL: "陆伟豪",
      AM: "是",
      AN: 0.5
    }
  }
};

test("选品2 不具备选品1列布局，Z-AN/AO-AX/AQ-BR 列位兜底一律禁用", () => {
  assert.equal(hasSelection1ColumnLayout(selection2Item), false);
  assert.equal(hasSelection1ColumnLayout({ source_type: "selection1_developer_claim_feedback" }), true);
  assert.equal(hasSelection1ColumnLayout({ source_type: "history_selection1" }), false);
  // detailFieldValue 的列位兜底按 source_type 限定；ColumnRangeTable 同样只对选品1列布局出行。
  assert.match(appSource, /if \(hasSelection1ColumnLayout\(item\)\) return snapshotColumnText\(item, fallbackColumn\);\s*\n\s*return historicalDevelopmentColumnText\(item, fallbackColumn\);/);
  assert.match(appSource, /const rows = !hasSelection1ColumnLayout\(props\.item\)\s*\n\s*\? \[\]/);
  assert.match(appSource, /hasSelection1ColumnLayout\(activeChild\) && costParameterColumns\.some/);
});

test("选品2 市场调研按真实表头取 低价高消/最新低价/最低价链接，认领区 AL-AN 绝不出现在竞品行", () => {
  const rows = selection2HeaderFields(selection2Item, "market");
  assert.deepEqual(rows.map((row) => row.column), ["X", "Y", "AA"]);
  assert.deepEqual(rows[1], { column: "Y", label: "低价高消链接", group: "", value: "https://shopee.ph/cheap-hot" });
  // AL=人名 / AM=是 / AN=0.5 的认领区单元格不进入市场调研板块。
  const values = rows.map((row) => row.value);
  assert.ok(!values.includes("陆伟豪"));
  assert.ok(!values.includes("是"));
  assert.ok(!values.includes("0.5"));
  assert.ok(!rows.some((row) => ["AL", "AM", "AN"].includes(row.column)));
});

test("选品2 价格参考/成本参数按真实表头取 H~U 的进价/定价/利润率与费用列", () => {
  const pricing = selection2HeaderFields(selection2Item, "pricing");
  assert.deepEqual(pricing.map((row) => [row.column, row.label]), [
    ["H", "进价"],
    ["Q", "销售成本（比索）"],
    ["T", "推广期SP利润率"],
    ["U", "稳定期SP利润率"]
  ]);
  const cost = selection2HeaderFields(selection2Item, "cost");
  assert.deepEqual(cost.map((row) => [row.column, row.label]), [["L", "海运"]]);
  // 非选品2 来源不产生表头派生。
  assert.deepEqual(selection2HeaderFields(selection1Item, "market"), []);
  assert.deepEqual(selection2HeaderFields(historySelection1NewGenItem, "market"), []);
});

test("商品详情各板块以既有数据优先、fields_by_cell 派生补位并标注选品1历史", () => {
  assert.match(appSource, /const historySections = historyFieldsByCellSections\(activeChild\);/);
  assert.match(appSource, /historyRows\.length > 0 && <span className="tag">选品1历史<\/span>/);
  assert.match(appSource, /historyMarket && <span className="tag">选品1历史<\/span>/);
  // 选品2 直接按自己的五个语义分块展示，不再进入选品1列位兜底。
  assert.match(appSource, /selection2HeaderFields\(activeChild, "core"\)/);
  assert.match(appSource, /selection2HeaderFields\(activeChild, "market"\)/);
  assert.match(appSource, /selection2HeaderFields\(activeChild, "pricing"\)/);
  assert.match(appSource, /selection2HeaderFields\(activeChild, "cost"\)/);
  assert.match(appSource, /selection2HeaderFields\(activeChild, "valuation"\)/);
  assert.match(appSource, /其他源表字段（\{historySections\.other\.length\}）<span className="tag">选品1历史<\/span>/);
  // 历史选品3/4必须优先走按真实列段生成的选品1式板块；其它来源仍以结构化/表头数据优先。
  assert.match(appSource, /isSelection34Archive \|\| !detailFieldRows\(activeChild, developmentFieldSpecs\)\.length/);
  assert.match(appSource, /isSelection34Archive \|\| !competitorRows\(activeChild\)\.length/);
  assert.match(appSource, /isSelection34Archive \|\| !pricingRows\(activeChild\)\.length/);
  assert.match(appSource, /!archiveSection && !hasColumnRows \? historySections\?\.cost \?\? \[\] : \[\]/);
});


const readonlyHistoricalSelection2Item = {
  source_type: "history_selection2",
  snapshot: {
    archive_type: "historical_selection2",
    headers_by_cell: {
      G: "\u8fdb\u4ef7",
      H: "Shopee\u7a33\u5b9a\u671f\u5b9a\u4ef7",
      AF: "\u4f4e\u4ef7\u9ad8\u6d88\u94fe\u63a5"
    },
    raw_cells_by_cell: {
      G: 20,
      H: 427,
      AF: "https://shopee.ph/cheap-hot"
    }
  }
};

test("read-only selection2 uses its native semantic headers", () => {
  assert.deepEqual(selection2HeaderFields(readonlyHistoricalSelection2Item, "pricing"), [
    { column: "G", label: "\u8fdb\u4ef7", group: "", value: "20" },
    { column: "H", label: "Shopee\u7a33\u5b9a\u671f\u5b9a\u4ef7", group: "", value: "427" }
  ]);
  assert.deepEqual(selection2HeaderFields(readonlyHistoricalSelection2Item, "market"), [
    { column: "AF", label: "\u4f4e\u4ef7\u9ad8\u6d88\u94fe\u63a5", group: "", value: "https://shopee.ph/cheap-hot" }
  ]);
});

const standardSelection2Item = {
  source_type: "selection2_caigen_claim_feedback",
  snapshot: {
    headers_by_column: {
      A: ["SPU"],
      B: ["SKU"],
      C: ["首单备货数量"],
      D: ["产品名称"],
      E: ["产品规格属性（材质、大小、颜色）"],
      G: ["进价"],
      K: ["海运"],
      P: ["销售成本（比索）"],
      S: ["推广期SP利润率"],
      U: ["长(箱)"],
      Z: ["体积(单)"],
      AB: ["高价高消链接"],
      AC: ["进货链接"],
      AF: ["低价高消链接"],
      AI: ["是否贴标包装及下单备注"],
      AJ: ["首单备货金额"],
      AK: ["首单备货体积"],
      AL: ["供应链核价后采购链接"],
      AN: ["核价意见"],
      AO: ["核价人"],
      AP: ["核价时间"]
    },
    cells: {
      A: "CG-MAIN",
      B: "CG-SUB",
      C: 100,
      D: "测试商品",
      E: "蓝色",
      G: 20,
      K: 1.5,
      P: 120,
      S: 0.15,
      U: 50,
      Z: 0.001,
      AB: "https://shopee.ph/high",
      AC: "https://detail.1688.com/offer/1.html",
      AF: "https://shopee.ph/low",
      AI: "贴标",
      AJ: 2000,
      AK: 0.1,
      AL: "https://detail.1688.com/offer/2.html",
      AN: "价格可接受",
      AO: "核价A",
      AP: "2026-07-30"
    }
  }
};

test("选品2标准 A:AP 按五个业务分块展示且字段不跨块", () => {
  assert.deepEqual(selection2HeaderFields(standardSelection2Item, "core").map((row) => row.column), ["A", "B", "C", "D", "E"]);
  assert.deepEqual(selection2HeaderFields(standardSelection2Item, "pricing").map((row) => row.column), ["G", "P", "S"]);
  assert.deepEqual(selection2HeaderFields(standardSelection2Item, "cost").map((row) => row.column), ["K", "U", "Z", "AI"]);
  assert.deepEqual(selection2HeaderFields(standardSelection2Item, "market").map((row) => row.column), ["AB", "AC", "AF"]);
  assert.deepEqual(selection2HeaderFields(standardSelection2Item, "valuation").map((row) => row.column), ["AJ", "AK", "AL", "AN", "AO", "AP"]);
});

test("商品详情为选品2切换五个专属分块名称", () => {
  assert.match(appSource, /const selection2DetailSections/);
  assert.match(appSource, /定价与利润/);
  assert.match(appSource, /成本与包装/);
  assert.match(appSource, /市场与采购/);
  assert.match(appSource, /核价与首单/);
});
