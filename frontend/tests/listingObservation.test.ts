import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import type { ListingRecord, ObservationPeriodRow, PendingListingTask } from "../src/api.ts";

import {
  buildListingWorkbenchGroups,
  buildListingTaskContexts,
  createRequestGate,
  defaultNextBusinessPeriodStart,
  filterListingWorkbenchGroups,
  filterObservationRows,
  formatObservationMetric,
  formatPercent,
  hasFetchedMetrics,
  latestPeriodIdsByListing,
  mapReviewServerRowErrors,
  mapServerRowErrors,
  productListingSummary,
  resolveWorkbenchScope,
  summarySalespersonScope,
  sortObservationRows,
  validateObservationReviews,
  validateListingDrafts,
  visibleSelectedPeriodIds
} from "../src/listingObservation.ts";

const listingObservationViewSource = readFileSync(new URL("../src/ListingObservationView.tsx", import.meta.url), "utf8");

test("只有普通运营会被登录身份锁定当前运营", () => {
  const source = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
  assert.match(source, /authSession\?\.operator_name && !canManage/);
});

function pendingTask(patch: Partial<PendingListingTask> = {}): PendingListingTask {
  return {
    task_key: "task-1",
    source_type: "selection1",
    business_period: "2026-07",
    country: "菲律宾",
    site: "PH",
    main_sku: "SKU1",
    main_sku_name: "商品1",
    salesperson_name: "运营甲",
    claim_record_ids: ["claim-1"],
    default_first_period_start: "2026-07-23",
    ...patch
  };
}

function listingRecord(patch: Partial<ListingRecord> = {}): ListingRecord {
  return {
    id: "listing-1",
    task_key: "task-1",
    main_sku: "SKU1",
    main_sku_name: "商品1",
    country: "菲律宾",
    site: "PH",
    salesperson_name: "运营甲",
    shop: "Shopee-PH",
    item: "ITEM-1",
    listing_strategy: "低价切入",
    first_period_start: "2026-07-23",
    status: "active",
    tracking_status: "active",
    first_round_completed_at: null,
    ...patch
  };
}

function observationRow(patch: Partial<ObservationPeriodRow> = {}): ObservationPeriodRow {
  return {
    id: "period-1",
    listing_record_id: "listing-1",
    main_sku: "SKU1",
    main_sku_name: "商品1",
    country: "菲律宾",
    salesperson_name: "运营甲",
    shop: "Shopee-PH",
    item: "ITEM-1",
    week_number: 1,
    period_start: "2026-07-23",
    period_end: "2026-07-29",
    status: "pending_data",
    tracking_status: "active",
    order_count: null,
    total_revenue: null,
    gross_profit_amount: null,
    gross_profit_rate: null,
    product_positioning: null,
    optimization_action: null,
    four_week_summary: null,
    first_round_completed_at: null,
    ...patch
  };
}

test("单表工作台按 task_key 分组且已有作废记录也不再算待刊登", () => {
  const pending = pendingTask({ task_key: "task-pending", main_sku: "SAME", country: "菲律宾" });
  const listed = pendingTask({ task_key: "task-listed", main_sku: "SAME", country: "越南" });
  const listing = listingRecord({
    id: "listing-1",
    task_key: "task-listed",
    main_sku: "SAME",
    country: "越南",
    status: "voided",
    tracking_status: "stopped"
  });
  const period = observationRow({
    id: "period-1",
    listing_record_id: "listing-1",
    main_sku: "SAME",
    country: "越南",
    status: "completed",
    tracking_status: "stopped"
  });

  const groups = buildListingWorkbenchGroups([pending, listed], [listing], [period], "2026-07-23");

  assert.equal(groups.length, 2);
  assert.deepEqual(filterListingWorkbenchGroups(groups, "pending_listing").map((group) => group.context.task_key), ["task-pending"]);
  assert.deepEqual(filterListingWorkbenchGroups(groups, "all").map((group) => group.context.task_key), ["task-pending", "task-listed"]);
  assert.equal(groups.find((group) => group.context.task_key === "task-listed")?.periodRows.length, 1);
});

test("业务状态只返回可处理待复盘或对应里程碑记录", () => {
  const groups = buildListingWorkbenchGroups(
    [pendingTask({ task_key: "task-listed", main_sku: "SKU1" })],
    [
      listingRecord({ id: "active", task_key: "task-listed", main_sku: "SKU1" }),
      listingRecord({ id: "stopped", task_key: "task-listed", main_sku: "SKU1", tracking_status: "stopped", first_round_completed_at: "2026-08-20T10:00:00+08:00" }),
      listingRecord({ id: "voided", task_key: "task-listed", main_sku: "SKU1", status: "voided", tracking_status: "stopped", first_round_completed_at: "2026-08-20T10:00:00+08:00" })
    ],
    [
      observationRow({ id: "review", listing_record_id: "active", main_sku: "SKU1", status: "pending_review" }),
      observationRow({ id: "stopped-period", listing_record_id: "stopped", main_sku: "SKU1", status: "completed", tracking_status: "stopped", first_round_completed_at: "2026-08-20T10:00:00+08:00" }),
      observationRow({ id: "voided-period", listing_record_id: "voided", main_sku: "SKU1", status: "completed", tracking_status: "stopped", first_round_completed_at: "2026-08-20T10:00:00+08:00" })
    ],
    "2026-07-23"
  );

  assert.deepEqual(filterListingWorkbenchGroups(groups, "pending_review")[0].periodRows.map((row) => row.id), ["review"]);
  assert.deepEqual(filterListingWorkbenchGroups(groups, "stopped")[0].periodRows.map((row) => row.id), ["stopped-period"]);
  assert.deepEqual(filterListingWorkbenchGroups(groups, "voided")[0].periodRows.map((row) => row.id), ["voided-period"]);
  assert.deepEqual(filterListingWorkbenchGroups(groups, "first_round_completed")[0].periodRows.map((row) => row.id), ["stopped-period", "voided-period"]);
  assert.deepEqual(filterListingWorkbenchGroups(groups, "voided")[0].listings.map((listing) => listing.id), ["voided"]);
});

test("主管默认全量而主管运营视角按所选运营查询", () => {
  assert.deepEqual(resolveWorkbenchScope("manager", true, ""), {});
  assert.deepEqual(resolveWorkbenchScope("operator", true, "运营甲"), { salesperson_name: "运营甲" });
  assert.equal(resolveWorkbenchScope("operator", true, ""), null);
  assert.deepEqual(resolveWorkbenchScope("operator", false, "伪造运营"), {});
});

test("主管运营视角未选运营时页面在请求前清空并短路", () => {
  const loadWorkbenchSource = listingObservationViewSource.match(/async function loadWorkbench\(\) \{[\s\S]*?\n  \}\n\n  useEffect/)?.[0] || "";
  assert.match(loadWorkbenchSource, /const scope = resolveWorkbenchScope\(props\.role, props\.canManage, props\.operatorName\);/);
  assert.match(loadWorkbenchSource, /if \(!scope\) \{[\s\S]*?setData\(EMPTY_DATA\);[\s\S]*?setSelectedPeriods\(\[\]\);[\s\S]*?setLoading\(false\);[\s\S]*?return;[\s\S]*?\}/);
  assert.ok(loadWorkbenchSource.indexOf("if (!scope)") < loadWorkbenchSource.indexOf("api.listingWorkbench"));
  assert.match(listingObservationViewSource, /请先选择运营/);
});

test("刊登观察页面使用单表和业务状态筛选且不暴露内部待取数", () => {
  assert.doesNotMatch(listingObservationViewSource, /const TABS/);
  assert.doesNotMatch(listingObservationViewSource, /listing-tabs/);
  assert.doesNotMatch(listingObservationViewSource, /只看待我处理/);
  assert.doesNotMatch(listingObservationViewSource, /待取数/);
  assert.match(listingObservationViewSource, /业务状态/);
  assert.match(listingObservationViewSource, /观察中/);
  assert.match(listingObservationViewSource, /新增店铺 \+ Item/);
});

test("刊登观察只读汇总的待数据周期四项指标统一显示短横线", () => {
  const summarySource = listingObservationViewSource.match(/export function ListingObservationSummary[\s\S]*?function PendingListingTasks/)?.[0] || "";
  assert.match(summarySource, /\{period\.status === "pending_data" \? "-" : formatObservationMetric\(period\.order_count\)\}/);
  assert.match(summarySource, /\{period\.status === "pending_data" \? "-" : formatObservationMetric\(period\.total_revenue\)\}/);
  assert.match(summarySource, /\{period\.status === "pending_data" \? "-" : formatObservationMetric\(period\.gross_profit_amount\)\}/);
  assert.match(summarySource, /\{period\.status === "pending_data" \? "-" : formatPercent\(period\.gross_profit_rate\)\}/);
});

test("刊登记录的店铺、Item、刊登策略和第一周周期全部必填", () => {
  const errors = validateListingDrafts([
    { shop: " ", item: "", listing_strategy: "\n", first_period_start: "" }
  ]);

  assert.deepEqual(errors, [{
    shop: "请填写店铺",
    item: "请填写 Item",
    listing_strategy: "请填写刊登策略",
    first_period_start: "请选择第一周起始周期"
  }]);
});

test("Item 去除首尾空白后批内重复时两行都标错", () => {
  const errors = validateListingDrafts([
    { shop: "Shopee-A", item: " ITEM-1 ", listing_strategy: "低价切入", first_period_start: "2026-07-16" },
    { shop: "Shopee-B", item: "ITEM-1", listing_strategy: "广告测试", first_period_start: "2026-07-23" }
  ]);

  assert.equal(errors[0].item, "Item 在本批次中重复");
  assert.equal(errors[1].item, "Item 在本批次中重复");
});

test("周期明细支持关键词与周期状态等条件组合筛选", () => {
  const rows = [
    {
      id: "period-1",
      listing_record_id: "listing-1",
      main_sku: "MAIN-A",
      main_sku_name: "蓝牙耳机",
      country: "菲律宾",
      salesperson_name: "运营甲",
      shop: "Shopee-PH",
      item: "ITEM-1",
      week_number: 1,
      period_start: "2026-07-16",
      period_end: "2026-07-22",
      status: "pending_review",
      tracking_status: "active",
      product_positioning: "利润款"
    },
    {
      id: "period-2",
      listing_record_id: "listing-2",
      main_sku: "MAIN-B",
      main_sku_name: "收纳盒",
      country: "越南",
      salesperson_name: "运营乙",
      shop: "Shopee-VN",
      item: "ITEM-2",
      week_number: 2,
      period_start: "2026-07-16",
      period_end: "2026-07-22",
      status: "pending_data",
      tracking_status: "stopped",
      product_positioning: "清仓款"
    }
  ] as const;

  const filtered = filterObservationRows(rows, {
    query: "耳机",
    country: "菲律宾",
    salesperson_name: "运营甲",
    shop: "Shopee-PH",
    period_start: "2026-07-16",
    status: "pending_review",
    week_number: 1,
    product_positioning: "利润款",
    tracking_status: "active"
  });

  assert.deepEqual(filtered.map((row) => row.id), ["period-1"]);
});

test("一次毛利率按百分比展示", () => {
  assert.equal(formatPercent(0.12345), "12.35%");
  assert.equal(formatPercent(0), "0.00%");
  assert.equal(formatPercent(null), "-");
});

test("周数据未获取与真实 0 使用不同文案", () => {
  assert.equal(formatObservationMetric(null), "周数据未获取");
  assert.equal(formatObservationMetric(undefined), "周数据未获取");
  assert.equal(formatObservationMetric(0), "0");
});

test("服务端结构化行错误映射回对应输入行", () => {
  const error = new Error(JSON.stringify({
    detail: {
      row_errors: [
        { row_index: 1, field: "item", message: "Item 已存在" },
        { row_index: 1, field: "shop", message: "请填写店铺" }
      ]
    }
  }));

  assert.deepEqual(mapServerRowErrors(error), {
    1: { item: "Item 已存在", shop: "请填写店铺" }
  });
});

test("周期复盘要求定位和优化操作且第 4 周要求总结", () => {
  const errors = validateObservationReviews([
    { period_id: "period-1", week_number: 1, product_positioning: "", optimization_action: " ", four_week_summary: "" },
    { period_id: "period-4", week_number: 4, product_positioning: "利润款", optimization_action: "优化标题", four_week_summary: " " }
  ]);

  assert.deepEqual(errors, {
    "period-1": { product_positioning: "请选择产品定位", optimization_action: "请填写优化操作" },
    "period-4": { four_week_summary: "请填写四周总结" }
  });
});

test("新增后续周期默认下一业务周期且不会沿用过期日期", () => {
  assert.equal(defaultNextBusinessPeriodStart("2026-07-16"), "2026-07-23");
  assert.equal(defaultNextBusinessPeriodStart("2026-07-22"), "2026-07-23");
});

test("周次筛选选择第 5 周及以后时包含所有后续周期", () => {
  const base = {
    listing_record_id: "listing-1",
    main_sku: "MAIN-A",
    salesperson_name: "运营甲",
    shop: "Shopee-PH",
    item: "ITEM-1",
    period_start: "2026-07-16",
    status: "completed",
    tracking_status: "active"
  };
  const rows = [
    { ...base, id: "period-4", week_number: 4 },
    { ...base, id: "period-5", week_number: 5 },
    { ...base, id: "period-6", week_number: 6 }
  ];

  assert.deepEqual(filterObservationRows(rows, { week_number: 5 }).map((row) => row.id), ["period-5", "period-6"]);
});

test("每个 Item 的操作入口只认完整数据中的最大周次", () => {
  assert.deepEqual(latestPeriodIdsByListing([
    { id: "period-1", listing_record_id: "listing-a", week_number: 1 },
    { id: "period-4", listing_record_id: "listing-a", week_number: 4 },
    { id: "period-b2", listing_record_id: "listing-b", week_number: 2 }
  ]), { "listing-a": "period-4", "listing-b": "period-b2" });
});

test("已有刊登记录可重建同一主 SKU 的新增上下文", () => {
  const contexts = buildListingTaskContexts([], [{
    id: "listing-1",
    task_key: "source|period|PH|MAIN-A|运营甲",
    main_sku: "MAIN-A",
    main_sku_name: "商品 A",
    country: "菲律宾",
    site: "PH",
    salesperson_name: "运营甲"
  }], "2026-07-23");

  assert.deepEqual(contexts, [{
    task_key: "source|period|PH|MAIN-A|运营甲",
    source_type: "",
    business_period: null,
    country: "菲律宾",
    site: "PH",
    main_sku: "MAIN-A",
    main_sku_name: "商品 A",
    salesperson_name: "运营甲",
    claim_record_ids: [],
    default_first_period_start: "2026-07-23"
  }]);
});

test("周期复盘服务端行错误按提交顺序映射回周期", () => {
  const error = new Error(JSON.stringify({ detail: { row_errors: [
    { row_index: 1, field: "optimization_action", message: "请填写优化操作" },
    { row_index: 1, field: "period_id", message: "周数据尚未就绪" }
  ] } }));
  const rows = [
    { period_id: "period-1", week_number: 1, product_positioning: "利润款" as const, optimization_action: "标题优化", four_week_summary: "" },
    { period_id: "period-2", week_number: 2, product_positioning: "利润款" as const, optimization_action: "", four_week_summary: "" }
  ];

  assert.deepEqual(mapReviewServerRowErrors(error, rows), {
    "period-2": { optimization_action: "请填写优化操作", period_id: "周数据尚未就绪" }
  });
});

test("商品详情汇总只在主管切到运营视角时传销售员范围", () => {
  assert.equal(summarySalespersonScope("manager", true, ""), undefined);
  assert.equal(summarySalespersonScope("operator", true, "运营甲"), "运营甲");
  assert.equal(summarySalespersonScope("operator", false, "伪造运营"), undefined);
});

test("请求门只接受最后一次请求结果", () => {
  const gate = createRequestGate();
  const first = gate.start();
  const second = gate.start();

  assert.equal(gate.isCurrent(first), false);
  assert.equal(gate.isCurrent(second), true);
});

test("选择数量和提交范围只保留当前可见周期", () => {
  assert.deepEqual(visibleSelectedPeriodIds(["period-1", "period-2"], [{ id: "period-2" }]), ["period-2"]);
});

test("周期行按主 SKU 国家负责人连续分组并稳定按 Item 周次排序", () => {
  const rows = [
    { id: "a2", main_sku: "MAIN-A", country: "PH", salesperson_name: "运营甲", item: "ITEM-A", week_number: 2, period_start: "2026-07-23" },
    { id: "b1", main_sku: "MAIN-B", country: "PH", salesperson_name: "运营甲", item: "ITEM-B", week_number: 1, period_start: "2026-07-16" },
    { id: "a1", main_sku: "MAIN-A", country: "PH", salesperson_name: "运营甲", item: "ITEM-A", week_number: 1, period_start: "2026-07-16" }
  ];

  assert.deepEqual(sortObservationRows(rows).map((row) => row.id), ["a1", "a2", "b1"]);
});

test("出现已取数周期后锁定店铺 Item 和起始周期", () => {
  assert.equal(hasFetchedMetrics([{ status: "pending_data" }]), false);
  assert.equal(hasFetchedMetrics([{ status: "pending_review" }]), true);
  assert.equal(hasFetchedMetrics([{ status: "completed" }]), true);
});

test("商品详情只读汇总严格匹配主 SKU 和国家", () => {
  const data = {
    pending_listing_tasks: [],
    listing_records: [
      { id: "listing-a", main_sku: "MAIN-A", country: "PH" },
      { id: "listing-a-vn", main_sku: "MAIN-A", country: "VN" },
      { id: "listing-ab", main_sku: "MAIN-AB", country: "PH" }
    ],
    period_rows: [
      { id: "period-a", listing_record_id: "listing-a" },
      { id: "period-vn", listing_record_id: "listing-a-vn" },
      { id: "period-ab", listing_record_id: "listing-ab" }
    ]
  };

  assert.deepEqual(productListingSummary(data, "MAIN-A", "PH"), {
    listings: [data.listing_records[0]],
    periods: [data.period_rows[0]]
  });
});
