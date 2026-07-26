import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  addKeyCategory,
  categoryLevel1Options,
  categoryLevel2Options,
  categorySelectionLabel,
  KEY_CATEGORY_LEVEL1_LIMIT,
  KEY_CATEGORY_LEVEL2_LIMIT,
  normalizeCategorySelections,
  removeKeyCategory
} from "../src/keyCategories.ts";

const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");

const dictionary = [
  { id: "1", level1: "家居厨卫", level2: "收纳清洁", enabled: true },
  { id: "2", level1: "家居厨卫", level2: "厨房用品", enabled: true },
  { id: "3", level1: "家居厨卫", level2: "卫浴用品", enabled: true },
  { id: "4", level1: "汽摩配", level2: "摩托车配件", enabled: true },
  { id: "5", level1: "户外运动", level2: null, enabled: true }
];

test("一级选项去重排序，二级选项按一级联动", () => {
  assert.deepEqual(categoryLevel1Options(dictionary), ["户外运动", "家居厨卫", "汽摩配"]);
  assert.deepEqual(categoryLevel2Options(dictionary, "家居厨卫"), ["厨房用品", "收纳清洁", "卫浴用品"]);
  assert.deepEqual(categoryLevel2Options(dictionary, "汽摩配"), ["摩托车配件"]);
  assert.deepEqual(categoryLevel2Options(dictionary, "户外运动"), []);
});

test("添加：无一级拒绝，一级加二级正常累积", () => {
  assert.equal(addKeyCategory([], { level1: "", level2: null }).error, "请先选择一级类目");

  const first = addKeyCategory([], { level1: "家居厨卫", level2: "收纳清洁" });
  assert.deepEqual(first.selections, [{ level1: "家居厨卫", level2: "收纳清洁" }]);

  const second = addKeyCategory(first.selections!, { level1: "家居厨卫", level2: "厨房用品" });
  assert.deepEqual(second.selections, [
    { level1: "家居厨卫", level2: "收纳清洁" },
    { level1: "家居厨卫", level2: "厨房用品" }
  ]);
});

test("添加：不选二级代表整个一级，并替换该一级下的二级选择", () => {
  const wholeOnly = addKeyCategory([], { level1: "户外运动", level2: null });
  assert.deepEqual(wholeOnly.selections, [{ level1: "户外运动", level2: null }]);

  const replaced = addKeyCategory(
    [
      { level1: "家居厨卫", level2: "收纳清洁" },
      { level1: "家居厨卫", level2: "厨房用品" }
    ],
    { level1: "家居厨卫", level2: null }
  );
  assert.deepEqual(replaced.selections, [{ level1: "家居厨卫", level2: null }]);
});

test("添加：重复与冲突有提示", () => {
  const wholeSelected = [{ level1: "户外运动", level2: null }];
  assert.equal(addKeyCategory(wholeSelected, { level1: "户外运动", level2: null }).error, "该一级类目已添加");
  assert.equal(addKeyCategory(wholeSelected, { level1: "户外运动", level2: "露营" }).error, "已选择整个一级类目，无需再选二级");
  assert.equal(
    addKeyCategory([{ level1: "家居厨卫", level2: "收纳清洁" }], { level1: "家居厨卫", level2: "收纳清洁" }).error,
    "该类目已添加"
  );
});

test("上限：最多 3 组一级，每组最多 2 个二级", () => {
  const threeGroups = [
    { level1: "家居厨卫", level2: null },
    { level1: "汽摩配", level2: null },
    { level1: "户外运动", level2: null }
  ];
  const overflow = addKeyCategory(threeGroups, { level1: "商办工业", level2: null });
  assert.equal(overflow.error, `最多添加 ${KEY_CATEGORY_LEVEL1_LIMIT} 组一级类目`);

  const twoLevel2 = [
    { level1: "家居厨卫", level2: "收纳清洁" },
    { level1: "家居厨卫", level2: "厨房用品" }
  ];
  const level2Overflow = addKeyCategory(twoLevel2, { level1: "家居厨卫", level2: "卫浴用品" });
  assert.equal(level2Overflow.error, `每组一级类目最多选择 ${KEY_CATEGORY_LEVEL2_LIMIT} 个二级类目`);

  // 已满 3 组时，已有组内仍可补二级。
  const mixed = addKeyCategory(
    [
      { level1: "家居厨卫", level2: "收纳清洁" },
      { level1: "汽摩配", level2: null },
      { level1: "户外运动", level2: null }
    ],
    { level1: "家居厨卫", level2: "厨房用品" }
  );
  assert.equal(mixed.error, undefined);
  assert.equal(mixed.selections!.length, 4);
});

test("删除标签与标签文案", () => {
  const selections = [
    { level1: "家居厨卫", level2: "收纳清洁" },
    { level1: "汽摩配", level2: null }
  ];
  assert.deepEqual(removeKeyCategory(selections, { level1: "家居厨卫", level2: "收纳清洁" }), [
    { level1: "汽摩配", level2: null }
  ]);
  assert.equal(categorySelectionLabel({ level1: "家居厨卫", level2: "收纳清洁" }), "家居厨卫 / 收纳清洁");
  assert.equal(categorySelectionLabel({ level1: "汽摩配", level2: null }), "汽摩配");
});

test("normalize 保持整一级优先并去重", () => {
  assert.deepEqual(
    normalizeCategorySelections([
      { level1: "家居厨卫", level2: null },
      { level1: "家居厨卫", level2: "收纳清洁" },
      { level1: "家居厨卫", level2: null }
    ]),
    [{ level1: "家居厨卫", level2: null }]
  );
});

test("运营配置抽屉使用下拉联动编辑器且不再写旧字段", () => {
  assert.match(appSource, /function KeyCategoryEditor/);
  assert.match(appSource, /categoryLevel2Options\(props\.companyCategories, level1\)/);
  assert.match(appSource, /key-category-tag/);
  assert.doesNotMatch(appSource, /legacyCategoryFields/);
  assert.doesNotMatch(appSource, /key_category1/);
  assert.doesNotMatch(appSource, /key_category2/);
});
