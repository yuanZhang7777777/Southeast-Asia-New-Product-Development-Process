import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const styles = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");
const app = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");

test("主管复核右栏固定在滚动区域顶部", () => {
  const rule = styles.match(/\.review-layout\s*>\s*\.form-card\s*\{([^}]*)\}/)?.[1] || "";

  assert.match(rule, /position:\s*sticky/);
  assert.match(rule, /top:\s*0/);
  assert.match(rule, /overflow-y:\s*auto/);
});

test("主管复核按认领类型筛选并提供批量通过和拒绝", () => {
  assert.match(app, /运营认领待复核/);
  assert.match(app, /运营不认领待复核/);
  assert.match(app, /批量通过/);
  assert.match(app, /批量拒绝/);
  assert.match(app, /api\.bulkReview/);
});

test("普通运营列表保留提交状态，商品详情矩阵只在顶部统计未提交项", () => {
  const editor = app.slice(app.indexOf("function ClaimDraftEditor"), app.indexOf("function ClaimDetailDrawer"));
  const matrixEditor = app.slice(app.indexOf("function ClaimMatrixDraftEditor"), app.indexOf("function draftForId"));
  const drawer = app.slice(app.indexOf("function ClaimDetailDrawer"), app.indexOf("function ClaimMatrixTable"));
  const setMode = app.slice(app.indexOf("function setMode"), app.indexOf("function buildPayload"));

  assert.match(editor, /claim-editor-actions[\s\S]*ClaimSubmissionBadge/);
  assert.doesNotMatch(matrixEditor, /ClaimSubmissionBadge/);
  assert.match(drawer, /dirtyCount/);
  assert.match(drawer, /提交本主 SKU 未提交项/);
  assert.match(setMode, /patchDraft\(itemId, \{ mode \}/);
  assert.doesNotMatch(setMode, /rejectReason|claimDailySales/);
});

test("商品详情组导航位于矩阵下方且不再使用绝对定位", () => {
  const drawer = app.slice(app.indexOf("function ClaimDetailDrawer"), app.indexOf("function ClaimMatrixTable"));
  const navRule = styles.match(/\.claim-group-nav\s*\{([^}]*)\}/)?.[1] || "";

  assert.match(drawer, /<ClaimMatrixTable[\s\S]*claim-group-nav-row[\s\S]*上一组[\s\S]*下一组/);
  assert.doesNotMatch(navRule, /position:\s*absolute/);
  assert.doesNotMatch(navRule, /transform:\s*translateY/);
  assert.match(styles, /\.claim-group-nav-row\s*\{/);
});

test("分配台使用紧凑工具栏、配置抽屉和去重运营卡片", () => {
  const assignView = app.slice(app.indexOf("function AssignView"), app.indexOf("function assignmentItemKey"));

  assert.match(app, /workflow-nav/);
  assert.match(assignView, /assignment-commandbar/);
  assert.match(assignView, /assignment-config-overlay/);
  assert.match(assignView, /assignment-config-drawer/);
  assert.match(assignView, /priority-badge/);
  assert.match(assignView, /operator-category-tags/);
  assert.doesNotMatch(assignView, /operatorProfileBrief\(profile\)/);
});

test("运营配置紧邻提交分配且全部运营负载直接换行展示", () => {
  const assignView = app.slice(app.indexOf("function AssignView"), app.indexOf("function assignmentItemKey"));
  const commandbar = assignView.slice(assignView.indexOf("assignment-commandbar"), assignView.indexOf("assignment-workload-grid"));
  const toolbar = app.slice(app.indexOf("function Toolbar"), app.indexOf("function ListControls"));
  const workloadRule = styles.match(/\.assignment-workload-grid\s*\{([^}]*)\}/)?.[1] || "";

  assert.doesNotMatch(commandbar, /assignment-config-trigger/);
  assert.ok(toolbar.indexOf("提交分配") < toolbar.indexOf("运营配置"));
  assert.match(toolbar, /assignment-primary-actions[\s\S]*提交分配[\s\S]*运营配置/);
  assert.match(toolbar, /onOpenProfilePanel/);
  assert.match(workloadRule, /position:\s*sticky/);
  assert.match(workloadRule, /display:\s*grid/);
  assert.match(workloadRule, /grid-template-columns:\s*repeat\(auto-fit/);
  assert.doesNotMatch(workloadRule, /overflow-x/);
  assert.match(assignView, /reorderOperatorWithinSite/);
  assert.match(assignView, /draggable/);
  assert.match(assignView, /onDrop/);
});

test("主管统计栏缩窄并使用单列指标", () => {
  const layoutRule = styles.match(/\.layout\s*\{([^}]*)\}/)?.[1] || "";
  const sideMetricsRule = styles.match(/\.side\s+\.metrics\s*\{([^}]*)\}/)?.[1] || "";

  assert.match(layoutRule, /170px/);
  assert.match(sideMetricsRule, /grid-template-columns:\s*1fr/);
});

test("窄屏分配明细只在表格内部横向滚动", () => {
  const viewportRule = styles.match(/\.assignment-table-panel,\s*\.assignment-table-scroll\s*\{([^}]*)\}/)?.[1] || "";

  assert.match(viewportRule, /min-width:\s*0/);
  assert.match(viewportRule, /max-width:\s*100%/);
});

test("导出中心按期展示且不保留无范围导出按钮", () => {
  const stockView = app.slice(app.indexOf("function StockView"), app.indexOf("function ArrivalPreviewView"));

  assert.match(stockView, /export-periods-table/);
  assert.match(stockView, /export-period-select/);
  assert.match(stockView, /viewPeriod\(period\.business_period\)/);
  assert.doesNotMatch(stockView, /查看明细/);
  assert.match(stockView, /period\.stocking_count\s*<=\s*0/);
  assert.match(stockView, /period\.traceability_count\s*<=\s*0/);
  assert.match(stockView, /exportPeriodFilter\(period\.business_period\)/);
  assert.doesNotMatch(stockView, /api\.traceabilityExport\(\)/);
  assert.doesNotMatch(stockView, /api\.availableStockingExport\(\)/);
});

test("导出中心刷新失败时保留当前期数和明细切片", () => {
  const refresh = app.slice(app.indexOf("async function refresh"), app.indexOf("async function loadPlmArrivalPreview"));

  assert.match(refresh, /loadPart\("导出中心", api\.availableStocking, availableStocking\)/);
  assert.match(refresh, /loadPart\("导出期数", api\.exportPeriods, exportPeriods\)/);
  assert.doesNotMatch(refresh, /loadPart\("导出中心", api\.availableStocking, \[\]\)/);
  assert.doesNotMatch(refresh, /loadPart\("导出期数", api\.exportPeriods, \[\]\)/);
  assert.match(refresh, /部分数据未加载/);
});
