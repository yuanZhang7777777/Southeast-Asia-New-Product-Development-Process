import assert from "node:assert/strict";
import test from "node:test";

import { filterAssignmentItems, moveOperatorWithinSite, sortOperatorProfiles } from "../src/assignmentFilters.ts";

const groups = [
  {
    key: "PH-A",
    items: [{ id: "a", main_sku: "MAIN-A", sub_sku: "SUB-RED", main_sku_name: "Red rack", site: "PH", category_level1: "家居厨卫" }]
  },
  {
    key: "TH-B",
    items: [{ id: "b", main_sku: "MAIN-B", sub_sku: "SUB-BLUE", main_sku_name: "Blue bag", site: "TH", category_level1: "户外运动" }]
  }
];

const items = [
  { main_sku: "MAIN-A", sub_sku_count: 1, suggested_assignee: "运营甲", opportunity_ids: ["a"] },
  { main_sku: "MAIN-B", sub_sku_count: 1, suggested_assignee: "运营乙", opportunity_ids: ["b"] }
];

test("多关键词任一命中，独立筛选条件之间同时满足", () => {
  const filtered = filterAssignmentItems(items, groups, {}, {
    query: "NOT-FOUND SUB-BLUE",
    site: "TH",
    category: "户外运动"
  });

  assert.deepEqual(filtered.map((item) => item.main_sku), ["MAIN-B"]);
  assert.deepEqual(filterAssignmentItems(items, groups, {}, { query: "SUB-RED SUB-BLUE" }).map((item) => item.main_sku), ["MAIN-A", "MAIN-B"]);
});

test("运营筛选同时匹配系统推荐和主管手动选择", () => {
  const drafts = { a: "运营丙" };

  assert.deepEqual(filterAssignmentItems(items, groups, drafts, { operator: "运营甲" }).map((item) => item.main_sku), ["MAIN-A"]);
  assert.deepEqual(filterAssignmentItems(items, groups, drafts, { operator: "运营丙" }).map((item) => item.main_sku), ["MAIN-A"]);
});

test("运营按站点和自定义顺序稳定排列", () => {
  const profiles = [
    { id: "th-1", operator_name: "运营丁", key_site: "TH", display_order: 1 },
    { id: "ph-2", operator_name: "运营乙", key_site: "PH", display_order: 2 },
    { id: "ph-1", operator_name: "运营甲", key_site: "菲律宾", display_order: 1 }
  ];

  assert.deepEqual(sortOperatorProfiles(profiles).map((profile) => profile.id), ["ph-1", "ph-2", "th-1"]);
});

test("上下移动只调整同站点运营", () => {
  const profiles = [
    { id: "ph-1", operator_name: "运营甲", key_site: "PH", display_order: 1 },
    { id: "th-1", operator_name: "运营丁", key_site: "TH", display_order: 1 },
    { id: "ph-2", operator_name: "运营乙", key_site: "PH", display_order: 2 }
  ];
  const moved = moveOperatorWithinSite(profiles, "ph-2", -1);

  assert.deepEqual(sortOperatorProfiles(moved).map((profile) => profile.id), ["ph-2", "ph-1", "th-1"]);
  assert.equal(moved.find((profile) => profile.id === "th-1")?.display_order, 1);
});
