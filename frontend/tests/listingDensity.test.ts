import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import test from "node:test";

const mainSource = readFileSync(new URL("../src/main.tsx", import.meta.url), "utf8");
const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const densityStyleUrl = new URL("../src/listingDensity.css", import.meta.url);
const densityStyles = existsSync(densityStyleUrl) ? readFileSync(densityStyleUrl, "utf8") : "";
const listingSource = readFileSync(new URL("../src/ListingObservationView.tsx", import.meta.url), "utf8");
const stylesSource = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");
const researchSource = readFileSync(new URL("../src/SecondaryResearchView.tsx", import.meta.url), "utf8");

test("listing controls stay compact without stretched inputs or result rows", () => {
  assert.match(mainSource, /import "\.\/listingDensity\.css";/);
  assert.match(densityStyles, /\.listing-select-all input\s*\{[^}]*width:\s*auto;/);
  assert.match(densityStyles, /\.listing-select-all input\s*\{[^}]*min-height:\s*auto;/);
  assert.match(densityStyles, /\.listing-workbench-results\s*\{[^}]*align-content:\s*start;/);
  assert.match(densityStyles, /\.listing-batchbar\s*\{[^}]*flex-wrap:\s*nowrap;/);
  assert.match(
    densityStyles,
    /@media \(max-width: 900px\)\s*\{[\s\S]*?\.listing-batchbar\s*\{[^}]*flex-direction:\s*row;/
  );
  assert.match(
    densityStyles,
    /@media \(max-width: 560px\)\s*\{[\s\S]*?\.listing-batchbar\s*\{[^}]*flex-direction:\s*column;/
  );
  assert.match(densityStyles, /\.listing-workbench-scenarios\s*\{[^}]*flex-wrap:\s*wrap;/);
  assert.match(densityStyles, /\.listing-period-card\.correction-active\s*\{[^}]*border-color:/);
});

test("workbench scenarios keep only useful filters and recover from empty results", () => {
  assert.match(researchSource, /const controls = \(/);
  assert.match(researchSource, /if \(!group\)[\s\S]*?\{controls\}/);
  assert.match(researchSource, /当前筛选下没有已提交记录/);
  assert.doesNotMatch(researchSource, /最新期数/);
  assert.doesNotMatch(researchSource, /latestSecondaryResearchPeriod\(allGroups, scenario/);
  assert.match(listingSource, /useState<"listing" \| "observation">\("observation"\)/);
  assert.match(listingSource, /刊登任务（\{listingScenarioCount\}）/);
  assert.match(listingSource, /周期观察（\{observationScenarioCount\}）/);
  assert.match(listingSource, /business_status: scenario === "observation" \? "all" : "pending_listing"/);
  assert.doesNotMatch(listingSource, /group\.context\.country \|\| group\.context\.site/);
  assert.doesNotMatch(listingSource, /advancedOpen/);
  assert.doesNotMatch(listingSource, /高级筛选/);
  const filterStart = listingSource.indexOf('className="listing-filters"');
  const filterEnd = listingSource.indexOf('<div className="listing-batchbar">', filterStart);
  const filters = listingSource.slice(filterStart, filterEnd);
  assert.ok(filterStart >= 0 && filterEnd > filterStart);
  assert.match(filters, /业务状态[\s\S]*?店铺[\s\S]*?周次[\s\S]*?周期处理状态[\s\S]*?产品定位[\s\S]*?跟踪状态/);
});

test("刊登和观察的 SKU 可进入商品详情且有图时显示缩略图", () => {
  assert.match(listingSource, /productLinks/);
  assert.match(listingSource, /onOpenProduct/);
  assert.match(listingSource, /listing-product-thumb/);
  assert.match(listingSource, /listing-product-link/);
});

test("周期观察折叠主行直接展示 Item 当前状态", () => {
  assert.match(listingSource, /const itemSummaries = group\.listings\.map/);
  // Item 状态取全量 period_rows（经 periodRowsByListing 预索引），不受当前分组筛选影响。
  assert.match(listingSource, /const itemStatusRows = sortStartedObservationPeriods\(periodRowsByListing\.get\(listing\.id\) \|\| \[\]\);/);
  assert.match(listingSource, /for \(const row of data\.period_rows\)/);
  assert.match(listingSource, /className="listing-group-status-strip"/);
  assert.match(listingSource, /itemSummaries\.slice\(0, 3\)\.map/);
  assert.match(listingSource, /className="listing-group-status-chip"/);
  assert.match(listingSource, /已复盘 \{periodSummary\.completedWeeks\}\/\{periodSummary\.totalWeeks\} 周/);
  assert.match(listingSource, /latestMetricRow/);
  assert.match(listingSource, /className="listing-group-metric-strip"/);
  assert.match(listingSource, /订单/);
  assert.match(stylesSource, /\.listing-group-status-strip\s*\{[\s\S]*?flex-wrap:\s*wrap;/);
  assert.match(stylesSource, /\.listing-group-status-chip[\s\S]*?display:\s*inline-flex;/);
  assert.match(stylesSource, /\.listing-group-metric-strip\s*\{/);
});
test("刊登任务支持主 SKU 级新增和手工新增主 SKU", () => {
  assert.match(listingSource, /openManualListing/);
  assert.match(listingSource, /新增主 SKU 刊登/);
  assert.match(listingSource, /manual_context/);
  assert.doesNotMatch(listingSource, /listing-group-more-menu/);
  assert.match(listingSource, /listing-group-add-item/);
  assert.match(listingSource, /新增刊登 Item/);
  assert.match(listingSource, /首周周期/);
  assert.match(listingSource, /系统自动/);
  assert.doesNotMatch(listingSource, /第一周起始周期 \*/);
  assert.match(stylesSource, /\.manual-listing-grid\s*\{/);
});

test("周期观察把指标、复盘字段和操作合并在同一行", () => {
  const cardStart = listingSource.indexOf("listing-period-card ${correcting");
  const cardEnd = listingSource.indexOf("</section>", cardStart);
  const periodCard = listingSource.slice(cardStart, cardEnd);

  assert.ok(cardStart >= 0 && cardEnd > cardStart);
  assert.match(periodCard, /className="listing-period-overview"/);
  assert.match(periodCard, /className="[^"]*listing-review-positioning[^"]*"/);
  assert.match(periodCard, /className="[^"]*listing-review-optimization[^"]*"/);
  assert.match(periodCard, /className="listing-period-actions"/);
  assert.doesNotMatch(periodCard, /<div className="listing-period-review">/);
  assert.match(densityStyles, /\.listing-period-select-cell input\s*\{[^}]*width:\s*auto;[^}]*min-height:\s*auto;/);
  assert.match(
    densityStyles,
    /@media \(max-width: 1180px\)\s*\{\s*\.listing-period-overview\s*\{\s*grid-template-columns:\s*1fr;\s*\}\s*\}/
  );
});
test("二次调研主列表只留行内填写字段，SKU 名称打开模块化详情", () => {
  assert.doesNotMatch(researchSource, /className="research-matrix-head research-secondary-grid"/);
  assert.match(researchSource, /className="research-task-list secondary-input-matrix"/);
  assert.match(researchSource, /className="research-task-row"/);
  assert.match(researchSource, /const primaryImageItem = group\.items\.find\(\(item\) => item\.image_url\) \|\| group\.items\[0\];/);
  assert.match(researchSource, /<button className="research-main-sku-open" type="button" onClick=\{\(\) => setDetailGroupKey\(group\.key\)\}>/);
  assert.match(researchSource, /<ResearchMainSkuThumb item=\{primaryImageItem\} \/>/);
  assert.match(researchSource, /className="research-task-side"/);
  assert.match(researchSource, /className="research-task-tools"/);
  assert.match(researchSource, /className="[^"]*research-inline-competitor/);
  assert.match(researchSource, /className="[^"]*research-inline-images/);
  assert.match(researchSource, /className="[^"]*research-target-sales/);
  assert.match(researchSource, /className="[^"]*research-selling-points/);
  assert.doesNotMatch(researchSource, /className="[^"]*research-time-cell/);
  assert.match(researchSource, /<input[\s\S]*value=\{draft\.competitorUrl\}[\s\S]*placeholder="锚定链接"/);
  assert.match(researchSource, /<ResearchImageList[\s\S]*className="research-inline-images"/);
  assert.match(researchSource, /onOpenDetail=\{\(\) => setDetailGroupKey\(group\.key\)\}/);
  assert.match(researchSource, /<button[\s\S]*className="research-sku-open"[\s\S]*\{item\.sub_sku\}/);
  assert.match(researchSource, /hideThumb/);
  assert.doesNotMatch(researchSource, /className="[^"]*research-inline-peers/);
  assert.doesNotMatch(researchSource, /<button className="btn small" type="button" onClick=\{\(\) => setDetailGroupKey\(group\.key\)\}>详情<\/button>/);
  assert.match(researchSource, /ResearchDetailDrawer/);
  assert.match(researchSource, /selection1DrawerModules/);
  assert.match(researchSource, /\{ key: "market", label: "市场调研" \}/);
  assert.match(researchSource, /selection2DrawerModules[\s\S]*市场与采购[\s\S]*定价与利润[\s\S]*成本与包装[\s\S]*核价与首单/);
  assert.match(researchSource, /selection2HeaderFields/);
  assert.doesNotMatch(researchSource, /\{ key: "secondary", label: "二次调研填写" \}/);
  assert.match(researchSource, /activeModule === "market"[\s\S]*?<SecondaryDraftMatrix/);
  assert.match(researchSource, /className="research-drawer-header-meta"/);
  assert.doesNotMatch(researchSource, /className="claim-basic-details"/);
  assert.match(researchSource, /认领记录/);
  assert.match(researchSource, /其他运营/);
  assert.doesNotMatch(researchSource, /className="research-row-more"/);
  assert.doesNotMatch(researchSource, /<summary>更多<\/summary>/);
  assert.doesNotMatch(researchSource, /className="research-compact-details/);
  assert.doesNotMatch(researchSource, /className="research-disclosure-panels"/);
  assert.doesNotMatch(researchSource, /开品理由 <b>\{group\.items\[0\]\?\.reason \|\| "-"\}<\/b>/);
  assert.match(researchSource, /group\.items\.map\(\(item\) => \([\s\S]*?className="research-source-reason"[\s\S]*?item\.sub_sku[\s\S]*?item\.reason \|\| "-"/);
  assert.doesNotMatch(stylesSource, /\.research-secondary-grid\s*\{[^}]*min-width:\s*1650px;/);
  assert.match(stylesSource, /\.secondary-input-matrix\s*\{[^}]*width:\s*100%;/);
  assert.match(stylesSource, /\.research-task-row\s*\{[\s\S]*?grid-template-columns:\s*180px minmax\(220px, 320px\) 128px minmax\(520px, 1fr\);/);
  assert.match(stylesSource, /\.research-drawer-edit-matrix \.research-task-row\s*\{[\s\S]*?grid-template-columns:\s*132px minmax\(0, 1fr\);/);
  assert.match(stylesSource, /\.research-drawer-edit-matrix \.research-task-tools\s*\{/);
  assert.match(stylesSource, /\.research-detail-drawer\s*\{[\s\S]*?width:\s*min\(760px, calc\(100vw - 72px\)\);/);
  assert.match(stylesSource, /\.research-drawer-tabs\s*\{/);
  assert.match(stylesSource, /\.research-source-panel-scroll\s*\{[\s\S]*?width:\s*100%;[\s\S]*?min-width:\s*0;[\s\S]*?overflow-x:\s*auto;/);
  assert.match(stylesSource, /\.research-source-grid\s*\{[\s\S]*?grid-template-columns:\s*150px repeat\(var\(--research-column-count\), minmax\(140px, 170px\)\);/);
  assert.match(stylesSource, /\.research-matrix-row\s*\{[\s\S]*?min-height:\s*72px;/);
});
test("运营认领筛选和列表控制在桌面同一行", () => {
  const rowStart = appSource.indexOf('className="claim-toolbar-row"');
  const rowEnd = appSource.indexOf("{!props.rows.length", rowStart);
  const toolbar = appSource.slice(rowStart, rowEnd);

  assert.ok(rowStart >= 0 && rowEnd > rowStart);
  assert.match(toolbar, /className="claim-workflow-filters"/);
  assert.match(toolbar, /<ListControls label="运营认领"/);
  assert.match(stylesSource, /\.claim-toolbar-row\s*\{[\s\S]*?display:\s*flex;[\s\S]*?flex-wrap:\s*nowrap;/);
  assert.match(stylesSource, /\.claim-toolbar-row \.list-controls\s*\{[\s\S]*?min-width:\s*0;/);
  assert.match(stylesSource, /\.claim-workflow-filters\s*\{[\s\S]*?flex-wrap:\s*nowrap;/);
  assert.match(stylesSource, /\.claim-workflow-filters select\s*\{[\s\S]*?width:\s*180px;[\s\S]*?max-width:\s*180px;/);
  assert.match(stylesSource, /@media \(max-width: 900px\)\s*\{[\s\S]*?\.claim-toolbar-row\s*\{[\s\S]*?flex-wrap:\s*wrap;/);
});

test("选品2公共池支持按规范化业务期筛选", () => {
  const poolStart = appSource.indexOf("function PoolView");
  const poolEnd = appSource.indexOf("function ProductGroupCard", poolStart);
  const poolSource = appSource.slice(poolStart, poolEnd);

  assert.ok(poolStart >= 0 && poolEnd > poolStart);
  assert.match(poolSource, /label="期数"/);
  assert.match(poolSource, /item\.batch \|\| item\.source_sheet/);
  assert.match(poolSource, /setBusinessPeriod\(value\)/);
  assert.match(poolSource, /page: 1/);
});


test("listing-only SKU opens editable detail", () => {
  assert.match(listingSource, /props\.onOpenProduct\(listing\.id, group\.context\.main_sku, productLink\?\.opportunity_id\)/);
  assert.doesNotMatch(listingSource, /disabled=\{!productLink\}/);
  assert.match(appSource, /openListingProductDetail/);
});
