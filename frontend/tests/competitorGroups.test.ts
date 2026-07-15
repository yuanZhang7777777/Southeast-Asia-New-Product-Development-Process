import assert from "node:assert/strict";
import test from "node:test";

import { competitorGroupForColumn, competitorGroupForLabel } from "../src/competitorGroups.ts";

test("五组竞品字段使用固定分组样式并保留文字标签", () => {
  assert.deepEqual(
    ["Z", "AC", "AF", "AI", "AL"].map((column) => competitorGroupForColumn(column)),
    [
      { key: "lowest", label: "最低价" },
      { key: "most-orders", label: "月销最高" },
      { key: "second", label: "月销次高" },
      { key: "third", label: "月销第三高" },
      { key: "new", label: "新晋" }
    ]
  );
  assert.deepEqual(competitorGroupForLabel("Most orders"), { key: "most-orders", label: "月销最高" });
});
