import assert from "node:assert/strict";
import test from "node:test";

import { attachCachedSnapshots, hasFullDetail, idsNeedingDetail } from "../src/opportunityDetails.ts";

test("只补取缺 snapshot 且未缓存未在途的行", () => {
  const items = [
    { id: "a" },
    { id: "b", snapshot: { cells: {} } },
    { id: "c" },
    { id: "d" }
  ];
  const pending = new Set(["c"]);
  const cache = new Map([["d", { cells: {} }]]);
  assert.deepEqual(idsNeedingDetail(items, pending, cache), ["a"]);
  assert.deepEqual(idsNeedingDetail(items, new Set(), new Map()), ["a", "c", "d"]);
});

test("刷新后的轻量列表能贴回已缓存快照且不覆盖已有快照", () => {
  const existing = { cells: { A: "已有" } };
  const cached = { cells: { A: "缓存" } };
  const items = [
    { id: "a" },
    { id: "b", snapshot: existing },
    { id: "c" }
  ];
  const merged = attachCachedSnapshots(items, new Map([["a", cached], ["b", { cells: { A: "不应覆盖" } }]]));
  assert.equal(merged[0].snapshot, cached);
  assert.equal(merged[1].snapshot, existing);
  assert.equal(merged[2].snapshot, undefined);
  assert.equal(merged[2], items[2]);
});

test("刷新后的轻量列表能贴回已缓存历史认领且不覆盖列表状态", () => {
  const cached = {
    snapshot: { cells: { A: "缓存" } },
    historical_claims: [{ salesperson_name: "冯卓宏", claim_result: "claim", claim_daily_sales: 1 }]
  };
  const items = [
    { id: "a", current_status: "claim_submitted", latest_claim_salesperson: "列表最新" }
  ];
  const merged = attachCachedSnapshots(items, new Map([["a", cached]]));

  assert.equal(merged[0].current_status, "claim_submitted");
  assert.equal(merged[0].latest_claim_salesperson, "列表最新");
  assert.deepEqual(merged[0].historical_claims, cached.historical_claims);
});

test("刷新后的轻量列表不能覆盖详情入口兜底图片", () => {
  const items = [
    { id: "a", image_url: null },
    { id: "b", image_url: "https://img.example.com/list.png" }
  ];
  const merged = attachCachedSnapshots(items, new Map([[
    "a",
    {
      snapshot: { cells: {} },
      image_url: "https://img.example.com/detail-fallback.png"
    }
  ]]));

  assert.equal(merged[0].image_url, "https://img.example.com/detail-fallback.png");
  assert.equal(merged[1].image_url, "https://img.example.com/list.png");
});

test("hasFullDetail 以 snapshot 是否取回为准（空对象也算已取回）", () => {
  assert.equal(hasFullDetail({ id: "a" }), false);
  assert.equal(hasFullDetail(null), false);
  assert.equal(hasFullDetail({ id: "a", snapshot: {} }), true);
});
