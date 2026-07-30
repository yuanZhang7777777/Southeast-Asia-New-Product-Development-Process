import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { EMPTY_DASHBOARD_COUNTS, roleHomeMetrics } from "../src/homeMetrics.ts";

const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");

const stats = {
  assigned: 4,
  returned: 2,
  selfClaimPool: 3,
  ready: 5,
  sourceTodo: 2,
  pendingAssign: 6,
  pendingReview: 7
};

const counts = {
  waiting_listing: 8,
  waiting_secondary_research: 9,
  pending_review_periods: 10
};

test("运营视角包含原有计数并追加下游三项，数值透传后端计数", () => {
  const metrics = roleHomeMetrics("operator", stats, counts);

  assert.deepEqual(
    metrics.map((metric) => [metric.label, metric.value]),
    [
      ["待认领", 4],
      ["待补充", 2],
      ["可自认领", 3],
      ["已通过", 5],
      ["待二次调研", 9],
      ["待刊登", 8],
      ["待复盘", 10]
    ]
  );
});

test("主管视角包含原有计数并追加下游三项", () => {
  const metrics = roleHomeMetrics("manager", stats, counts);

  assert.deepEqual(
    metrics.map((metric) => [metric.label, metric.value]),
    [
      ["待导入", 2],
      ["待分配", 6],
      ["待复核", 7],
      ["可导出", 5],
      ["待二次调研", 9],
      ["待刊登", 8],
      ["待复盘", 10]
    ]
  );
});

test("每个计数项都有跳转目标视图", () => {
  for (const role of ["operator", "manager"] as const) {
    for (const metric of roleHomeMetrics(role, stats, counts)) {
      assert.ok(metric.view, `${role} ${metric.label} 缺少跳转视图`);
    }
  }
  const operatorViews = Object.fromEntries(roleHomeMetrics("operator", stats, counts).map((metric) => [metric.label, metric.view]));
  assert.equal(operatorViews["待认领"], "claim");
  assert.equal(operatorViews["待补充"], "claim");
  assert.equal(operatorViews["可自认领"], "pool");
  assert.equal(operatorViews["已通过"], "stock");
  const managerViews = Object.fromEntries(roleHomeMetrics("manager", stats, counts).map((metric) => [metric.label, metric.view]));
  assert.equal(managerViews["待导入"], "source");
  assert.equal(managerViews["待分配"], "assign");
  assert.equal(managerViews["待复核"], "review");
  assert.equal(managerViews["可导出"], "stock");
});

test("待二次调研跳转二次调研工作台并预设待处理全期", () => {
  for (const role of ["operator", "manager"] as const) {
    const metric = roleHomeMetrics(role, stats, counts).find((item) => item.label === "待二次调研");
    assert.equal(metric?.view, "research");
    assert.deepEqual(metric?.researchPreset, { scenario: "pending", periodFilter: "__all__" });
  }
});

test("待刊登与待复盘跳转刊登与观察工作台对应场景", () => {
  const listing = roleHomeMetrics("manager", stats, counts).find((item) => item.label === "待刊登");
  assert.equal(listing?.view, "listing");
  assert.deepEqual(listing?.listingPreset, { scenario: "listing", businessStatus: "pending_listing", status: "" });

  const review = roleHomeMetrics("manager", stats, counts).find((item) => item.label === "待复盘");
  assert.equal(review?.view, "listing");
  assert.deepEqual(review?.listingPreset, { scenario: "observation", businessStatus: "pending_review", status: "pending_review" });
});

test("首页面板将计数渲染为可点击按钮并接线跳转", () => {
  assert.match(appSource, /roleHomeMetrics\(activeRole, stats, dashboardCounts\)/);
  assert.match(appSource, /className="metric metric-button"/);
  assert.match(appSource, /onClick=\{\(\) => openHomeMetric\(metric\)\}/);
  assert.match(appSource, /api\s*\n?\s*\.dashboardCounts\(owner\)|api\.dashboardCounts\(owner\)/);
  assert.match(appSource, /preset=\{researchPreset\}/);
  assert.match(appSource, /preset=\{listingPreset\}/);
});

test("空计数常量兜底为 0", () => {
  assert.deepEqual(EMPTY_DASHBOARD_COUNTS, {
    waiting_listing: 0,
    waiting_secondary_research: 0,
    pending_review_periods: 0
  });
});
