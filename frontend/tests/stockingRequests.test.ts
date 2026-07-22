import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  buildStockingDraftUpdate,
  buildStockingExportPayload,
  groupStockingItems,
  operatorStockingCountry,
  roleStockingLabel,
  stockingDecisionStatus,
  stockingFormVisible,
  stockingQuantity,
  stockingSourceLabel,
  stockingUnitVolume,
  StockingDraftSaveQueue,
  visibleStockingRequestIds,
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

test("不完整申请和 ERP 体积查询失败仍可保存为部分草稿", () => {
  assert.deepEqual(buildStockingDraftUpdate({
    application_date: "",
    request_type: "initial",
    cost_price: 12.5,
    unit_volume: null,
    daily_sales: null,
    country: " ",
    warehouse: "",
    reason: ""
  }), {
    application_date: null,
    request_type: "initial",
    cost_price: 12.5,
    length_cm: null,
    width_cm: null,
    height_cm: null,
    unit_volume: null,
    unit_volume_source: null,
    daily_sales: null,
    country: null,
    warehouse: null,
    reason: null
  });
  assert.match(view, /submit \? payloadFor\([^)]*\) : buildStockingDraftUpdate\(draft\)/);
});

test("unit volume provenance follows ERP lookup and manual edits", () => {
  assert.equal(buildStockingDraftUpdate({
    application_date: "2026-07-21",
    request_type: "initial",
    cost_price: 12.5,
    unit_volume: 0.002,
    unit_volume_source: "erp",
    daily_sales: 2,
    country: "PH"
  }).unit_volume_source, "erp");
  assert.equal(buildStockingDraftUpdate({
    application_date: "2026-07-21",
    request_type: "initial",
    cost_price: 12.5,
    unit_volume: 0.003,
    unit_volume_source: "manual",
    daily_sales: 2,
    country: "PH"
  }).unit_volume_source, "manual");
  assert.equal(buildStockingDraftUpdate({
    application_date: "2026-07-21",
    request_type: "initial",
    cost_price: 12.5,
    unit_volume: null,
    unit_volume_source: "erp",
    daily_sales: 2,
    country: "PH"
  }).unit_volume_source, null);
  assert.match(view, /preview\?\.status === "resolved" \? "erp" : null/);
  assert.match(view, /unit_volume_source: unitVolume === null \? null : "manual"/);
});
test("无申请分支使用机会国家筛选并作为新草稿默认国家", () => {
  assert.equal(operatorStockingCountry({ country: " PH ", request: null }), "PH");
  assert.equal(operatorStockingCountry({ country: "TH", request: { country: "VN" } }), "TH");
  assert.match(view, /operatorStockingCountry\(item\) !== filters\.country/);
  assert.match(view, /country: item\.request\?\.country \|\| operatorStockingCountry\(item\)/);
});

test("stock 导航按角色显示同一路由的业务名称", () => {
  assert.equal(roleStockingLabel("operator"), "备货申请");
  assert.equal(roleStockingLabel("manager"), "导出中心");
  assert.match(app, /roleStockingLabel\(activeRole\)/);
});

test("运营申请按主 SKU 分组", () => {
  const groups = groupStockingItems([
    { claim_record_id: "c3", main_sku: "MAIN-B", sub_sku: "B-1" },
    { claim_record_id: "c2", main_sku: "MAIN-A", sub_sku: "A-2" },
    { claim_record_id: "c1", main_sku: "MAIN-A", sub_sku: "A-1" }
  ]);
  assert.deepEqual(groups.map((group) => [group.main_sku, group.items.length]), [["MAIN-A", 2], ["MAIN-B", 1]]);
  assert.deepEqual(groups[0].items.map((item) => item.sub_sku), ["A-1", "A-2"]);
});

test("运营可填写厘米长宽高并自动换算单个体积", () => {
  assert.equal(stockingUnitVolume(20, 10, 5), 0.001);
  assert.equal(stockingUnitVolume(20, null, 5), null);
  assert.equal(stockingUnitVolume(0, 10, 5), null);

  assert.deepEqual(buildStockingDraftUpdate({
    application_date: "2026-07-22",
    request_type: "initial",
    cost_price: 10,
    length_cm: 20,
    width_cm: 10,
    height_cm: 5,
    unit_volume: 0.001,
    unit_volume_source: "manual",
    daily_sales: 2,
    country: "泰国"
  }), {
    application_date: "2026-07-22",
    request_type: "initial",
    cost_price: 10,
    length_cm: 20,
    width_cm: 10,
    height_cm: 5,
    unit_volume: 0.001,
    unit_volume_source: "manual",
    daily_sales: 2,
    country: "泰国",
    warehouse: null,
    reason: null
  });
});

test("备货草稿离开输入框自动保存且体积只读展示", () => {
  assert.match(view, /autoSaveRequest/);
  assert.match(view, /onBlur=.*autoSaveRequest\(item\)/);
  assert.match(view, /长（cm）/);
  assert.match(view, /宽（cm）/);
  assert.match(view, /高（cm）/);
  assert.match(view, /单个体积（自动）/);
  assert.match(view, /readOnly/);
});

test("自动保存跳过未修改草稿并按申请串行保存最新版本", async () => {
  const queue = new StockingDraftSaveQueue<number>();
  const started: number[] = [];
  const states: string[] = [];
  const resolvers: Array<() => void> = [];
  const save = async (payload: number) => {
    started.push(payload);
    await new Promise<void>((resolve) => resolvers.push(resolve));
  };

  assert.equal(await queue.enqueue("request-a", 0, save), false);
  queue.markDirty("request-a");
  const first = queue.enqueue("request-a", 1, save, (state) => states.push(state));
  await new Promise((resolve) => setTimeout(resolve, 0));
  queue.markDirty("request-a");
  const second = queue.enqueue("request-a", 2, save, (state) => states.push(state));
  await new Promise((resolve) => setTimeout(resolve, 0));

  assert.deepEqual(started, [1]);
  resolvers.shift()?.();
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.deepEqual(started, [1, 2]);
  resolvers.shift()?.();
  assert.equal(await first, true);
  assert.equal(await second, true);
  assert.equal(queue.isDirty("request-a"), false);
  assert.deepEqual(states, ["saving", "dirty", "saving", "saved"]);
  assert.match(view, /saveQueue\.markDirty\(requestId\)/);
  assert.match(view, /saveQueue\.enqueue\(/);
});

test("备货条目上下排列，左侧信息不会被表单高度撑出大块空白", () => {
  const cardRules = styles.match(/\.stocking-item-card\s*\{([^}]*)\}/g) || [];
  const cardRule = cardRules.at(-1) || "";
  const contextRule = styles.match(/\.stocking-item-context\s*\{([^}]*)\}/)?.[1] || "";
  assert.match(cardRule, /display:\s*block/);
  assert.doesNotMatch(cardRule, /grid-template-columns/);
  assert.match(contextRule, /border-bottom/);
});

test("主管仅提交勾选且去重的申请编号", () => {
  assert.deepEqual(buildStockingExportPayload(["request-b", "request-a", "request-b"]), {
    request_ids: ["request-b", "request-a"]
  });
  assert.throws(() => buildStockingExportPayload([]), /至少选择一条申请/);
  assert.match(apiSource, /availableStockingExport:[\s\S]*method: "POST"[\s\S]*JSON\.stringify\(payload\)/);
});

test("主管导出选择只保留当前可见且仍可导出的申请", () => {
  const visibleRows = [{ request_id: "request-a" }, { request_id: "request-c" }];
  assert.deepEqual(
    visibleStockingRequestIds(["request-b", "request-a", "stale", "request-a"], visibleRows),
    ["request-a"]
  );
  assert.match(view, /buildStockingExportPayload\(visibleSelected\)/);
});

test("来源标签和销售自选弹窗提供准确且可访问的名称", () => {
  assert.equal(stockingSourceLabel("selection1_developer_claim_feedback"), "选品1");
  assert.equal(stockingSourceLabel("selection2_caigen_claim_feedback"), "选品2/财根");
  assert.match(view, /role="dialog" aria-modal="true" aria-labelledby="sales-self-title"/);
  assert.match(view, /id="sales-self-title"/);
  assert.match(view, /aria-label="关闭销售自选弹窗"/);
  assert.match(view, /aria-label={"子 SKU " \+ \(index \+ 1\)}/);
  assert.match(view, /aria-label={"子 SKU 名称 " \+ \(index \+ 1\)}/);
  assert.match(view, /aria-label={"备货决策 " \+ \(index \+ 1\)}/);
  assert.match(view, /aria-label={"删除子 SKU " \+ \(index \+ 1\)}/);
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

test("operator role and refresh state stay aligned with authenticated ownership", () => {
  const superAdminStart = app.indexOf('if (item.role === "super_admin")');
  const superAdminBranch = app.slice(superAdminStart, app.indexOf("} else", superAdminStart));
  assert.doesNotMatch(superAdminBranch, /roles\.add\("operator"\)/);
  assert.match(app, /activeRole === "operator" && activeView !== "stock"/);
  assert.match(app, /activeView === "stock" \? authSession\.operator_name \|\| authSession\.user\.name/);

  const eventStreamStart = app.indexOf("const source = new EventSource");
  const eventStreamEffect = app.slice(app.lastIndexOf("useEffect(() =>", eventStreamStart), app.indexOf("useEffect(() =>", eventStreamStart + 1));
  assert.match(eventStreamEffect, /\}, \[authSession\?\.access_token, activeRole\]\);/);

  const refresh = app.slice(app.indexOf("async function refresh"), app.indexOf("async function loadPlmArrivalPreview"));
  assert.match(refresh, /activeRole === "manager"/);
  assert.match(refresh, /api\.myStockingRequests/);
  assert.match(refresh, /const generation = \+\+refreshGeneration\.current/);
  assert.match(refresh, /if \(generation !== refreshGeneration\.current\) \{[\s\S]*refreshLoadingGeneration\.current === generation[\s\S]*setLoading\(false\)[\s\S]*return;/);
  assert.match(refresh, /setHealthStatus[\s\S]*refreshLoadingGeneration\.current === generation[\s\S]*setLoading\(false\)/);
});
