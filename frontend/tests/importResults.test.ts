import assert from "node:assert/strict";
import test from "node:test";

import { recordImportResult } from "../src/importResults.ts";

const selection1 = {
  source_file: "selection1.xlsx",
  source_sheet: "开发0714期",
  business_period: "2026-W29",
  imported_count: 3,
  created_count: 3,
  updated_count: 0,
  skipped_count: 0,
  market_research_count: 0,
  prefill_claim_count: 0,
  task_count: 3
};

const selection2 = {
  ...selection1,
  source_file: "selection2.xlsx",
  source_sheet: "7.14期",
  business_period: "7.14期"
};

test("选品1和选品2分别保留自己的最近成功导入", () => {
  const afterSelection1 = recordImportResult({}, 1, selection1);
  const afterSelection2 = recordImportResult(afterSelection1, 2, selection2);

  assert.equal(afterSelection2[1]?.source_sheet, "开发0714期");
  assert.equal(afterSelection2[1]?.business_period, "2026-W29");
  assert.equal(afterSelection2[2]?.source_sheet, "7.14期");
  assert.equal(afterSelection2[2]?.business_period, "7.14期");
});
