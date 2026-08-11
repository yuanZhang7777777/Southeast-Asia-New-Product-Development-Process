import assert from "node:assert/strict";
import test from "node:test";
import { cachedValue, clearPageDataCache, setCachedValue } from "../src/pageDataCache.ts";

test("page data cache returns fresh values and expires stale values", () => {
  clearPageDataCache();
  setCachedValue("secondary:owner", ["a"], 1_000);

  assert.deepEqual(cachedValue<string[]>("secondary:owner", 1_000, 60_000), ["a"]);
  assert.equal(cachedValue<string[]>("secondary:owner", 62_000, 60_000), undefined);
});

test("page data cache separates keys", () => {
  clearPageDataCache();
  setCachedValue("secondary:owner-a", "a", 1_000);
  setCachedValue("listing:owner-a", "b", 1_000);

  assert.equal(cachedValue<string>("secondary:owner-a", 2_000, 60_000), "a");
  assert.equal(cachedValue<string>("listing:owner-a", 2_000, 60_000), "b");
});
