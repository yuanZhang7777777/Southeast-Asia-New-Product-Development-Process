import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import test from "node:test";

const mainSource = readFileSync(new URL("../src/main.tsx", import.meta.url), "utf8");
const densityStyleUrl = new URL("../src/listingDensity.css", import.meta.url);
const densityStyles = existsSync(densityStyleUrl) ? readFileSync(densityStyleUrl, "utf8") : "";
const listingSource = readFileSync(new URL("../src/ListingObservationView.tsx", import.meta.url), "utf8");
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
  assert.match(researchSource, /latestSecondaryResearchPeriod\(allGroups, scenario/);
  assert.match(listingSource, /scenario === "observation" && advancedOpen/);
  assert.match(listingSource, /useState<"listing" \| "observation">\("observation"\)/);
  assert.match(listingSource, /刊登任务（\{listingScenarioCount\}）/);
  assert.match(listingSource, /周期观察（\{observationScenarioCount\}）/);
  assert.match(listingSource, /business_status: scenario === "observation" \? "all" : "pending_listing"/);
  assert.doesNotMatch(listingSource, /group\.context\.country \|\| group\.context\.site/);
  assert.match(listingSource, /listing-advanced-filters[\s\S]*?业务状态[\s\S]*?店铺/);
});

test("刊登和观察的 SKU 可进入商品详情且有图时显示缩略图", () => {
  assert.match(listingSource, /productLinks/);
  assert.match(listingSource, /onOpenProduct/);
  assert.match(listingSource, /listing-product-thumb/);
  assert.match(listingSource, /listing-product-link/);
});
