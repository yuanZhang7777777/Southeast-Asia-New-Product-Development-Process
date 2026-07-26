import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { adjacentDetailTarget } from "../src/productDetailNavigation.ts";
import { compactUrlLabel } from "../src/urlDisplay.ts";

const groups = [
  { key: "MAIN-A", items: [{ id: "A-1" }, { id: "A-2" }] },
  { key: "MAIN-B", items: [{ id: "B-1" }, { id: "B-2" }] }
];

const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const apiSource = readFileSync(new URL("../src/api.ts", import.meta.url), "utf8");

test("详情先切同主 SKU 子项，到边界后切换主 SKU", () => {
  assert.deepEqual(adjacentDetailTarget(groups, "MAIN-A", "A-1", 1), { groupKey: "MAIN-A", childId: "A-2" });
  assert.deepEqual(adjacentDetailTarget(groups, "MAIN-A", "A-2", 1), { groupKey: "MAIN-B", childId: "B-1" });
  assert.deepEqual(adjacentDetailTarget(groups, "MAIN-B", "B-1", -1), { groupKey: "MAIN-A", childId: "A-2" });
  assert.equal(adjacentDetailTarget(groups, "MAIN-A", "A-1", -1), null);
});

test("长链接只显示域名，完整地址仍作为链接目标", () => {
  assert.equal(compactUrlLabel("https://www.shopee.vn/a/very/long/path?query=1"), "shopee.vn");
  assert.equal(compactUrlLabel("not-a-url"), "打开链接");
});

test("商品全局档案分别提供二次调研和刊登观察只读历史", () => {
  assert.match(appSource, /\{ key: "secondary", label: "二次调研" \}/);
  assert.match(appSource, /activeSection === "secondary"/);
  assert.match(appSource, /<SecondaryResearchSummary/);
  assert.match(appSource, /<ListingObservationSummary/);
});

test("二次调研历史查询可显式请求全部下游状态", () => {
  assert.match(apiSource, /secondaryResearchQuery\(salespersonName, businessPeriod, downstreamStatus\)/);
  assert.match(apiSource, /downstream_status/);
});

test("商品详情打开时不卸载来源工作台以便返回原场景", () => {
  assert.match(appSource, /detailGroup && \(/);
  assert.match(appSource, /style=\{\{ display: detailGroup \? "none" : undefined \}\}/);
});
test("历史回填 development_source 可作为商品详情字段兜底", () => {
  assert.match(appSource, /historicalDevelopmentColumns/);
  assert.match(appSource, /development_source/);
  assert.match(appSource, /snapshotColumnText[\s\S]*historicalDevelopmentColumnText/);
});
