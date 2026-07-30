import assert from "node:assert/strict";
import test from "node:test";

import { defaultFineBIWeekLabel, validateFineBIWeekLabel } from "../src/finebiPull.ts";

test("默认周标签取上一个完整的周四至周三区间", () => {
  assert.equal(defaultFineBIWeekLabel(new Date(2026, 6, 30)), "0723-0729"); // 周四：上一区间刚结束
  assert.equal(defaultFineBIWeekLabel(new Date(2026, 6, 29)), "0716-0722"); // 周三当天：本区间未结束
  assert.equal(defaultFineBIWeekLabel(new Date(2026, 6, 26)), "0716-0722"); // 周日
  assert.equal(defaultFineBIWeekLabel(new Date(2026, 7, 6)), "0730-0805"); // 跨月
  assert.equal(defaultFineBIWeekLabel(new Date(2026, 0, 1)), "1225-1231"); // 跨年
});

test("周标签校验：MMDD-MMDD 通过，其余给出提示", () => {
  assert.equal(validateFineBIWeekLabel("0723-0729"), "");
  assert.equal(validateFineBIWeekLabel(" 0716-0722 "), "");
  assert.notEqual(validateFineBIWeekLabel(""), "");
  assert.notEqual(validateFineBIWeekLabel("2026-07-23"), "");
  assert.notEqual(validateFineBIWeekLabel("723-729"), "");
  assert.notEqual(validateFineBIWeekLabel("0723~0729"), "");
});
