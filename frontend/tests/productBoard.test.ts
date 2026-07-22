import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { buildProductBoardRows, filterProductBoardRows, hasMultipleOwners, productBoardStatusLabel } from "../src/productBoard.ts";

const productBoardViewSource = readFileSync(new URL("../src/ProductBoardView.tsx", import.meta.url), "utf8");

const baseGroup = {
  key: "2026-W29|PH|MAIN-1",
  business_period: "2026-W29",
  site: "PH",
  country: "PH",
  main_sku: "MAIN-1",
  main_sku_name: "Main One",
  child_skus: [
    { opportunity_id: "opp-a", sub_sku: "SUB-A", sub_sku_name: "Sub A", visible_status: "waiting_secondary_research" },
    { opportunity_id: "opp-b", sub_sku: "SUB-B", sub_sku_name: "Sub B", visible_status: "waiting_listing" }
  ],
  responsibilities: [
    {
      claim_record_id: "claim-a",
      opportunity_id: "opp-a",
      salesperson_name: "Owner A",
      sub_sku: "SUB-A",
      claim_daily_sales: 6,
      visible_status: "waiting_secondary_research",
      arrival_detected_at: "2026-07-10T00:00:00Z"
    },
    {
      claim_record_id: "claim-b",
      opportunity_id: "opp-b",
      salesperson_name: "Owner B",
      sub_sku: "SUB-B",
      claim_daily_sales: 3,
      visible_status: "waiting_listing",
      arrival_detected_at: null
    }
  ],
  summary_tags: ["multi_owner"]
};

test("product board rows keep one main SKU group per period and status filter reads responsibilities", () => {
  const rows = buildProductBoardRows([
    baseGroup,
    {
      ...baseGroup,
      key: "2026-W30|PH|MAIN-1",
      business_period: "2026-W30",
      responsibilities: [{ ...baseGroup.responsibilities[0], claim_record_id: "claim-c" }],
      summary_tags: []
    }
  ]);

  assert.deepEqual(rows.map((row) => row.key), ["2026-W29|PH|MAIN-1", "2026-W30|PH|MAIN-1"]);
  assert.equal(rows[0].childCount, 2);
  assert.equal(rows[0].responsibilityCount, 2);
  assert.equal(rows[0].ownersText, "Owner A、Owner B");

  const waitingResearch = filterProductBoardRows(rows, { status: "waiting_secondary_research" });

  assert.deepEqual(waitingResearch.map((row) => row.key), ["2026-W29|PH|MAIN-1", "2026-W30|PH|MAIN-1"]);
  assert.equal(waitingResearch[0].responsibilities.length, 1);
  assert.equal(waitingResearch[0].responsibilities[0].salesperson_name, "Owner A");

  const ownerA = filterProductBoardRows(rows, { owner: "Owner A" });

  assert.deepEqual(ownerA.map((row) => row.key), ["2026-W29|PH|MAIN-1", "2026-W30|PH|MAIN-1"]);
  assert.equal(ownerA[0].responsibilities.length, 1);
  assert.equal(ownerA[0].responsibilities[0].salesperson_name, "Owner A");
});

test("multi-owner tag only appears when more than one owner is responsible", () => {
  assert.equal(hasMultipleOwners(baseGroup), true);
  assert.equal(
    hasMultipleOwners({
      ...baseGroup,
      responsibilities: [{ ...baseGroup.responsibilities[0] }],
      summary_tags: ["multi_owner"]
    }),
    false
  );
});

test("product board keeps business-period filtering without a generic date picker", () => {
  assert.match(productBoardViewSource, /全部期数/);
  assert.doesNotMatch(productBoardViewSource, /type="date"/);
});


test("product board labels the new stocking states and keeps ordinary waiting listing", () => {
  assert.equal(productBoardStatusLabel("waiting_stocking_request"), "待填备货申请");
  assert.equal(productBoardStatusLabel("waiting_export"), "待导出");
  assert.equal(productBoardStatusLabel("stocking_paused"), "暂不推进");
  assert.equal(productBoardStatusLabel("waiting_listing"), "待刊登");
  assert.equal(productBoardStatusLabel("listing_observation"), "刊登观察中");
});
