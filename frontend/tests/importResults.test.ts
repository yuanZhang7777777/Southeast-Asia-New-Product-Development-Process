import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { recordImportResult } from "../src/importResults.ts";

const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const apiSource = readFileSync(new URL("../src/api.ts", import.meta.url), "utf8");

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

test("源表导入上传期间显示明确导入中状态", () => {
  assert.match(appSource, /sourceImportingKind/);
  assert.match(appSource, /正在上传并导入，请勿关闭页面/);
  assert.match(appSource, /正在上传并导入/);
});

test("首页刷新不默认拉取隐藏商品档案", () => {
  assert.doesNotMatch(appSource, /api\.opportunities\(5000/);
  assert.doesNotMatch(appSource, /api\.opportunities\(5000,\s*undefined,\s*isSuperAdmin\)/);
  assert.match(appSource, /api\.opportunities\(300\)/);
});

test("源表文件导入走后台任务并轮询状态", () => {
  assert.match(apiSource, /importSelection1FileAsync/);
  assert.match(apiSource, /\/opportunities\/import\/selection1\/upload-async/);
  assert.match(appSource, /waitImportJob/);
});
