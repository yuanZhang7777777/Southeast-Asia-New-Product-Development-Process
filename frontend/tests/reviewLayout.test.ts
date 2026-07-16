import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const styles = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");
const app = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");

test("主管复核右栏固定在滚动区域顶部", () => {
  const rule = styles.match(/\.review-layout\s*>\s*\.form-card\s*\{([^}]*)\}/)?.[1] || "";

  assert.match(rule, /position:\s*sticky/);
  assert.match(rule, /top:\s*0/);
  assert.match(rule, /overflow-y:\s*auto/);
});

test("主管复核按认领类型筛选并提供批量通过和拒绝", () => {
  assert.match(app, /运营认领待复核/);
  assert.match(app, /运营不认领待复核/);
  assert.match(app, /批量通过/);
  assert.match(app, /批量拒绝/);
  assert.match(app, /api\.bulkReview/);
});
