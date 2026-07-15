import assert from "node:assert/strict";
import test from "node:test";

import { filterOperatorClaimRows, latestBusinessPeriod } from "../src/operatorClaimFilters.ts";

const rows = [
  { id: "new-name-old-time", batch: "开发新品9999期", created_at: "2026-07-01T00:00:00Z", current_status: "assigned" },
  { id: "latest", batch: "开发新品0714期", created_at: "2026-07-14T08:00:00Z", current_status: "claim_submitted" },
  { id: "rejected", batch: "开发新品0714期", created_at: "2026-07-14T07:00:00Z", current_status: "claim_rejected" },
  { id: "returned", batch: "开发新品0714期", created_at: "2026-07-14T06:00:00Z", current_status: "returned_for_supplement" }
];

test("默认最新期数按记录创建时间判断而不是期数字符串", () => {
  assert.equal(latestBusinessPeriod(rows), "开发新品0714期");
});

test("期数和操作状态筛选同时生效", () => {
  assert.deepEqual(
    filterOperatorClaimRows(rows, { businessPeriod: "开发新品0714期", status: "claimed_pending_review" }).map((item) => item.id),
    ["latest"]
  );
  assert.deepEqual(
    filterOperatorClaimRows(rows, { businessPeriod: "开发新品0714期", status: "rejected_pending_review" }).map((item) => item.id),
    ["rejected"]
  );
  assert.deepEqual(
    filterOperatorClaimRows(rows, { businessPeriod: "开发新品0714期", status: "returned" }).map((item) => item.id),
    ["returned"]
  );
});
