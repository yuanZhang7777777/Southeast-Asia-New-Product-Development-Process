import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  buildStockingExportPayload,
  groupStockingItems,
  roleStockingLabel,
  stockingDecisionStatus,
  stockingFormVisible,
  stockingQuantity,
  validateStockingDraft
} from "../src/stockingRequests.ts";

const view = readFileSync(new URL("../src/StockingRequestView.tsx", import.meta.url), "utf8");
const app = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const apiSource = readFileSync(new URL("../src/api.ts", import.meta.url), "utf8");
const styles = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");

test("选品1/2已有草稿时不依赖销售自选决策字段展示申请表", () => {
  assert.equal(stockingFormVisible({ source_type: "selection1_developer_claim_feedback", request_id: "r1", needs_stocking: null }), true);
  assert.equal(stockingFormVisible({ source_type: "sales_self_selection", request_id: "r2", needs_stocking: false }), false);
});
test("销售自选三种决策映射到既有后续状态", () => {
  assert.equal(stockingDecisionStatus(false, true), "waiting_stocking_request");
  assert.equal(stockingDecisionStatus(true, false), "waiting_listing");
  assert.equal(stockingDecisionStatus(false, false), "stocking_paused");
});

test("申请校验使用向上取整、允许空仓库并要求合法手填体积", () => {
  assert.equal(stockingQuantity(2.01), 61);
  assert.deepEqual(validateStockingDraft({
    application_date: "2026-07-21",
    request_type: "initial",
    cost_price: 12.5,
    unit_volume: 0.002,
    daily_sales: 2.01,
    country: "PH",
    warehouse: "",
    reason: ""
  }), {});
  assert.equal(validateStockingDraft({
    application_date: "2026-07-21",
    request_type: "initial",
    cost_price: 12.5,
    unit_volume: 0,
    daily_sales: 2.01,
    country: "PH"
  }).unit_volume, "单个体积必须大于 0");
});

test("补货原因按类型必填且销售自选成本价必填", () => {
  assert.equal(validateStockingDraft({
    application_date: "2026-07-21",
    request_type: "replenishment",
    cost_price: 12.5,
    unit_volume: 0.002,
    daily_sales: 2,
    country: "PH",
    reason: ""
  }).reason, "补货时必须填写补货原因");
  assert.equal(validateStockingDraft({
    application_date: "2026-07-21",
    request_type: "initial",
    cost_price: null,
    unit_volume: 0.002,
    daily_sales: 2,
    country: "PH"
  }, true).cost_price, "销售自选必须填写成本价");
});

test("stock 导航按角色显示同一路由的业务名称", () => {
  assert.equal(roleStockingLabel("operator"), "备货申请");
  assert.equal(roleStockingLabel("manager"), "导出中心");
  assert.match(app, /roleStockingLabel\(activeRole\)/);
});

test("运营申请按主 SKU 分组", () => {
  const groups = groupStockingItems([
    { claim_record_id: "c1", main_sku: "MAIN-A", sub_sku: "A-1" },
    { claim_record_id: "c2", main_sku: "MAIN-A", sub_sku: "A-2" },
    { claim_record_id: "c3", main_sku: "MAIN-B", sub_sku: "B-1" }
  ]);
  assert.deepEqual(groups.map((group) => [group.main_sku, group.items.length]), [["MAIN-A", 2], ["MAIN-B", 1]]);
});

test("主管仅提交勾选且去重的申请编号", () => {
  assert.deepEqual(buildStockingExportPayload(["request-b", "request-a", "request-b"]), {
    request_ids: ["request-b", "request-a"]
  });
  assert.throws(() => buildStockingExportPayload([]), /至少选择一条申请/);
  assert.match(apiSource, /availableStockingExport:[\s\S]*method: "POST"[\s\S]*JSON\.stringify\(payload\)/);
});

test("运营界面覆盖销售自选、三分支、体积降级、草稿和提交", () => {
  assert.match(view, /销售自选/);
  assert.match(view, /有库存，不备货/);
  assert.match(view, /无库存，不备货/);
  assert.match(view, /需要备货/);
  assert.match(view, /volumePreview/);
  assert.match(view, /未取得体积，请手填/);
  assert.match(view, /保存草稿/);
  assert.match(view, /提交申请/);
  assert.match(view, /stocking-request-form-grid/);
});

test("主管筛选和选择固定在内部滚动的 16 列表格上方", () => {
  assert.match(view, /stocking-manager-toolbar/);
  assert.match(view, /导出选中/);
  assert.match(view, /全选当前筛选/);
  assert.match(view, /stocking-export-scroll/);
  assert.equal((view.match(/<th>/g) || []).length, 16);
  const scrollRule = styles.match(/\.stocking-export-scroll\s*\{([^}]*)\}/)?.[1] || "";
  assert.match(scrollRule, /overflow:\s*auto/);
  assert.match(scrollRule, /min-width:\s*0/);
});

test("运营刷新不请求主管导出接口", () => {
  const refresh = app.slice(app.indexOf("async function refresh"), app.indexOf("async function loadPlmArrivalPreview"));
  assert.match(refresh, /activeRole === "manager"/);
  assert.match(refresh, /api\.myStockingRequests/);
});
