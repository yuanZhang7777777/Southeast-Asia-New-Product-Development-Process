import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(new URL("../src/StockingRequestView.tsx", import.meta.url), "utf8");
const api = readFileSync(new URL("../src/api.ts", import.meta.url), "utf8");

test("导出中心展示已导出行但只允许勾选待导出", () => {
  const managerView = source.slice(source.indexOf("function ManagerStockingView"), source.indexOf("function Field"));

  assert.match(managerView, /exportableRows = filteredRows\.filter\(\(row\) => row\.status === "submitted"\)/);
  assert.match(managerView, /visibleStockingRequestIds\(selected, exportableRows\)/);
  assert.match(managerView, /disabled=\{row\.status !== "submitted"\}/);
  assert.match(managerView, /当前筛选下暂无备货申请记录/);
});

test("导出中心提供备货申请和认领情况两个明细视图", () => {
  const managerView = source.slice(source.indexOf("function ManagerStockingView"), source.indexOf("function Field"));

  assert.match(api, /traceabilityList: \(filter\?: PeriodFilter\) => request<TraceabilityItem\[\]>/);
  assert.match(api, /traceabilityExport: \(filter\?: PeriodFilter\) => download/);
  assert.match(api, /centralTraceabilityExport: \(filter\?: PeriodFilter\) => download/);
  assert.match(managerView, /detailMode/);
  assert.match(managerView, /备货申请明细/);
  assert.match(managerView, /认领情况明细/);
  assert.match(managerView, /api\.traceabilityList\(\{ business_period: period \}\)/);
  assert.match(managerView, /api\.centralTraceabilityExport\(\{ business_period: period \}\)/);
  assert.match(managerView, /traceabilityLoading \? "认领情况加载中…"/);
  assert.match(managerView, /正在生成 \$\{period\} 认领情况表/);
  assert.match(managerView, /导出中央表/);
});
