import assert from "node:assert/strict";
import test from "node:test";

import { groupByBusinessIdentity } from "../src/opportunityGroups.ts";

const base = {
  id: "1",
  source_type: "selection1",
  batch: "2026-W29",
  site: "PH",
  main_sku: "MAIN-1"
};

test("相同主 SKU 按来源、业务期数和标准化站点隔离", () => {
  const groups = groupByBusinessIdentity([
    base,
    { ...base, id: "2", batch: "2026-W30" },
    { ...base, id: "3", site: "TH" },
    { ...base, id: "4", source_type: "selection2" }
  ]);

  assert.equal(groups.length, 4);
});

test("同一期数的中文站点别名归入同一组", () => {
  const groups = groupByBusinessIdentity([base, { ...base, id: "2", site: "菲律宾" }]);

  assert.equal(groups.length, 1);
  assert.deepEqual(groups[0].items.map((item) => item.id), ["1", "2"]);
});
