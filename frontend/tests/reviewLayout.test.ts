import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const styles = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");
const app = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const stockViewSource = readFileSync(new URL("../src/StockingRequestView.tsx", import.meta.url), "utf8");

test("主管复核右栏固定在滚动区域顶部", () => {
  const rule = styles.match(/\.review-layout\s*>\s*\.form-card\s*\{([^}]*)\}/)?.[1] || "";

  assert.match(rule, /position:\s*sticky/);
  assert.match(rule, /top:\s*0/);
  assert.match(rule, /overflow-y:\s*auto/);
});

test("主管复核展开右栏时左侧列表保持顶部紧凑排列", () => {
  const rule = styles.match(/\.review-layout\s*>\s*\.group-list\s*\{([^}]*)\}/)?.[1] || "";

  assert.match(rule, /align-content:\s*start/);
  assert.match(rule, /align-self:\s*start/);
});

test("主管复核筛选分页和批量操作固定在列表顶部", () => {
  const reviewView = app.slice(app.indexOf("function ReviewView"), app.indexOf("function ArrivalPreviewView"));
  const rule = styles.match(/\.review-sticky-controls\s*\{([^}]*)\}/)?.[1] || "";

  assert.match(reviewView, /review-sticky-controls[\s\S]*review-type-tabs[\s\S]*ListControls[\s\S]*review-bulkbar/);
  assert.match(rule, /position:\s*sticky/);
  assert.match(rule, /top:\s*0/);
  assert.match(rule, /z-index:\s*9/);
});

test("商品详情返回恢复打开前页面", () => {
  assert.match(app, /detailReturnView/);
  assert.match(app, /setDetailReturnView\(activeView\)/);
  assert.match(app, /function closeProductDetail\(\)[\s\S]*setDetailGroupKey\(null\)[\s\S]*if \(returnView\) setActiveView\(returnView\)/);
  assert.match(app, /onBack=\{closeProductDetail\}/);
});

test("主管复核使用自身右栏时不再显示通用主管统计侧栏", () => {
  const sideCondition = app.slice(app.indexOf('{activeView !== "claim"'), app.indexOf('<aside className="side">'));

  assert.match(sideCondition, /activeView !== "review"/);
  assert.match(app, /\["claim", "research", "listing", "review", "admin"\]\.includes\(activeView\)/);
});

test("主管复核按认领类型筛选并提供批量通过和拒绝", () => {
  assert.match(app, /运营认领待复核/);
  assert.match(app, /运营不认领待复核/);
  assert.match(app, /批量通过/);
  assert.match(app, /批量拒绝/);
  assert.match(app, /pendingReviewRows\(opportunities\)/);
  assert.match(app, /claim_record_id:\s*item\.latest_claim_record_id/);
  assert.match(app, /for \(const item of items\)[\s\S]*api\.review/);
  assert.match(app, /function reviewRowKey/);
});

test("运营任务用任务自身的认领记录覆盖机会级最新汇总", () => {
  assert.match(app, /function opportunityForOperatorTask/);
  assert.match(app, /task\.claim_record_id/);
  assert.match(app, /task\.node_code === "returned_claim"/);
  assert.match(app, /opportunityForOperatorTask\(item, task\)/);
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

test("分配台筛选和分页控件固定在列表顶部", () => {
  const assignView = app.slice(app.indexOf("function AssignView"), app.indexOf("function assignmentItemKey"));
  const stickyRule = styles.match(/\.assignment-sticky-controls\s*\{([^}]*)\}/)?.[1] || "";

  assert.match(assignView, /assignment-sticky-controls[\s\S]*assignment-commandbar[\s\S]*assignment-workload-toggle/);
  assert.match(stickyRule, /position:\s*sticky/);
  assert.match(stickyRule, /top:\s*0/);
  assert.match(stickyRule, /z-index:\s*9/);
});

test("导出中心按期筛选并只导出勾选申请", () => {
  assert.match(stockViewSource, /stocking-periods/);
  assert.match(stockViewSource, /stocking-manager-toolbar/);
  assert.match(stockViewSource, /buildStockingExportPayload\(visibleSelected\)/);
  assert.match(stockViewSource, /api\.availableStockingExport/);
  assert.match(stockViewSource, /traceabilityExport\(\{ business_period: period \}\)/);
  assert.match(stockViewSource, /onStatus\(error instanceof Error \? error\.message : "导出失败"\)/);
  assert.doesNotMatch(stockViewSource, /查看明细/);
});
test("导出中心刷新失败时保留当前期数和明细切片", () => {
  const refresh = app.slice(app.indexOf("async function refresh"), app.indexOf("async function loadPlmArrivalPreview"));

  assert.match(refresh, /loadPart\("导出中心", api\.availableStocking, availableStocking\)/);
  assert.match(refresh, /loadPart\("导出期数", api\.exportPeriods, exportPeriods\)/);
  assert.doesNotMatch(refresh, /loadPart\("导出中心", api\.availableStocking, \[\]\)/);
  assert.doesNotMatch(refresh, /loadPart\("导出期数", api\.exportPeriods, \[\]\)/);
  assert.match(refresh, /部分数据未加载/);
});

test("静默刷新失败不弹出部分数据未加载提示", () => {
  const refresh = app.slice(app.indexOf("async function refresh"), app.indexOf("async function loadPlmArrivalPreview"));

  assert.match(refresh, /if \(!options\.silent\)\s*\{[\s\S]*setStatusMessage\(failures\.length \? `部分数据未加载：/);
});


test("stock 工作台使用全宽布局", () => {
  assert.match(app, /activeView === "stock"/);
  assert.match(app, /activeView !== "stock"/);
});
test("运营配置站点使用动态选项和明确的国家代码标签", () => {
  assert.match(app, /siteOptions[\s\S]*operatorProfiles/);
  assert.match(app, /<select value=\{normalizeSiteText\(profile\.key_site\)\}/);
  assert.match(app, /siteOptionLabel\(site\)/);
  assert.match(app, /负责站点/);
});
test("运营配置重点类目使用字典多选而不是自由文本", () => {
  const assignView = app.slice(app.indexOf("function AssignView"), app.indexOf("function assignmentItemKey"));

  assert.match(assignView, /KeyCategoryEditor/);
  assert.match(assignView, /companyCategories/);
  assert.doesNotMatch(assignView, /key_category1/);
  assert.doesNotMatch(assignView, /key_category2/);
});

test("分配台按最终选择运营显示站点和品类匹配红绿标记", () => {
  const tableRow = app.slice(app.indexOf("function AssignmentTableRow"), app.indexOf("function AssignmentPreviewCard"));
  const reasonClass = app.slice(app.indexOf("function assignmentReasonClass"), app.indexOf("function siteOptionLabel"));

  assert.match(tableRow, /selectedProfile[\s\S]*assignmentMatchLines/);
  assert.match(tableRow, /selectedProfile[\s\S]*reasonLines/);
  assert.match(app, /站点匹配/);
  assert.match(app, /站点未匹配/);
  assert.match(app, /一级类目匹配|二级类目匹配/);
  assert.match(app, /品类未匹配/);
  assert.match(reasonClass, /assignment-reason-line category/);
  assert.match(reasonClass, /assignment-reason-line miss/);
});
