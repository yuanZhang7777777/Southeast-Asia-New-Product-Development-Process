import assert from "node:assert/strict";
import test from "node:test";

import { exportPeriodFilter, filterRowsForExportPeriod, selectExportPeriod } from "../src/exportPeriods.ts";

const periods = [
  { business_period: "开发0714期", stocking_count: 2, traceability_count: 3 },
  { business_period: "开发0707期", stocking_count: 1, traceability_count: 1 }
];

test("默认选择后端返回的最新期并保留仍存在的当前期", () => {
  assert.equal(selectExportPeriod(periods, ""), "开发0714期");
  assert.equal(selectExportPeriod(periods, "开发0707期"), "开发0707期");
  assert.equal(selectExportPeriod(periods, "不存在"), "开发0714期");
});

test("明细和下载都强制绑定一个业务期数", () => {
  const rows = [{ business_period: "开发0714期", claim_record_id: "A" }, { business_period: "开发0707期", claim_record_id: "B" }];
  assert.deepEqual(filterRowsForExportPeriod(rows, "开发0707期").map((row) => row.claim_record_id), ["B"]);
  assert.deepEqual(exportPeriodFilter("开发0714期"), { business_period: "开发0714期" });
  assert.throws(() => exportPeriodFilter(""), /请选择业务期数/);
});
