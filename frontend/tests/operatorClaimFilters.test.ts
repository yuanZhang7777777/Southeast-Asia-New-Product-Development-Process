import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { businessPeriodsByNewest, filterOperatorClaimRows } from "../src/operatorClaimFilters.ts";

const __dirname = dirname(fileURLToPath(import.meta.url));

const rows = [
  { id: "new-name-old-time", batch: "开发新品9999期", created_at: "2026-07-01T00:00:00Z", current_status: "assigned" },
  { id: "latest", batch: "开发新品0714期", created_at: "2026-07-14T08:00:00Z", current_status: "claim_submitted" },
  { id: "rejected", batch: "开发新品0714期", created_at: "2026-07-14T07:00:00Z", current_status: "claim_rejected" },
  { id: "returned", batch: "开发新品0714期", created_at: "2026-07-14T06:00:00Z", current_status: "returned_for_supplement" }
];

test("业务期选项按记录创建时间倒序展示", () => {
  assert.deepEqual(businessPeriodsByNewest(rows), ["开发新品0714期", "开发新品9999期"]);
});

test("运营认领页业务期默认全部期数，不自动切到最新期", () => {
  const appSource = readFileSync(join(__dirname, "../src/App.tsx"), "utf8");
  assert.doesNotMatch(appSource, /latestBusinessPeriod/);
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
