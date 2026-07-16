import assert from "node:assert/strict";
import test from "node:test";

import { formatBusinessNumber, formatBusinessValue } from "../src/businessFormat.ts";

test("业务数字最多显示两位小数", () => {
  assert.equal(formatBusinessNumber(35.235647706422014), "35.24");
  assert.equal(formatBusinessNumber(2.8200000000000003), "2.82");
  assert.equal(formatBusinessNumber(633), "633");
});

test("利润率按百分比显示", () => {
  assert.equal(formatBusinessValue(0.161309873307121, "稳定期利润率"), "16.13%");
  assert.equal(formatBusinessValue("8.5%", "推广期利润率"), "8.5%");
  assert.equal(formatBusinessValue("0.08942910149992718", "AP · 推广期利润率"), "8.94%");
  assert.equal(formatBusinessValue("95.60994434250765", "AR · 推广期总成本"), "95.61");
  assert.equal(formatBusinessValue("0.42504000000000003", "AS · 头程费用（元）"), "0.43");
  assert.equal(formatBusinessValue("7.123456", "AT · 菲律宾汇率"), "7.12");
});
