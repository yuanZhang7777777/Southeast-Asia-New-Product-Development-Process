import assert from "node:assert/strict";
import test from "node:test";

import { selection1ColumnLabel } from "../src/selection1Columns.ts";

test("二次调研源表模块在旧快照缺少表头时仍显示选品1真实字段名", () => {
  assert.equal(selection1ColumnLabel("Z"), "最低价链接");
  assert.equal(selection1ColumnLabel("AA"), "售价1");
  assert.equal(selection1ColumnLabel("AC"), "most orders链接");
  assert.equal(selection1ColumnLabel("AO"), "参考单销");
  assert.equal(selection1ColumnLabel("AR"), "一次毛利额（人民币）");
  assert.equal(selection1ColumnLabel("AW"), "稳定期总成本（THB）（含头程+平台费+基础设施）");
});

test("未知列不伪装成字段占位文案", () => {
  assert.equal(selection1ColumnLabel("ZZ"), "ZZ");
});
