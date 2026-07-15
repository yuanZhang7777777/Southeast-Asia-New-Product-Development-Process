import assert from "node:assert/strict";
import test from "node:test";

import { adjacentDetailTarget } from "../src/productDetailNavigation.ts";
import { compactUrlLabel } from "../src/urlDisplay.ts";

const groups = [
  { key: "MAIN-A", items: [{ id: "A-1" }, { id: "A-2" }] },
  { key: "MAIN-B", items: [{ id: "B-1" }, { id: "B-2" }] }
];

test("详情先切同主 SKU 子项，到边界后切换主 SKU", () => {
  assert.deepEqual(adjacentDetailTarget(groups, "MAIN-A", "A-1", 1), { groupKey: "MAIN-A", childId: "A-2" });
  assert.deepEqual(adjacentDetailTarget(groups, "MAIN-A", "A-2", 1), { groupKey: "MAIN-B", childId: "B-1" });
  assert.deepEqual(adjacentDetailTarget(groups, "MAIN-B", "B-1", -1), { groupKey: "MAIN-A", childId: "A-2" });
  assert.equal(adjacentDetailTarget(groups, "MAIN-A", "A-1", -1), null);
});

test("长链接只显示域名，完整地址仍作为链接目标", () => {
  assert.equal(compactUrlLabel("https://www.shopee.vn/a/very/long/path?query=1"), "shopee.vn");
  assert.equal(compactUrlLabel("not-a-url"), "打开链接");
});
