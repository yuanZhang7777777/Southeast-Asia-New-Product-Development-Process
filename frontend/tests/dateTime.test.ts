import assert from "node:assert/strict";
import test from "node:test";
import { formatBeijingDateTime } from "../src/dateTime.ts";

test("UTC timestamps render as Beijing time", () => {
  assert.equal(formatBeijingDateTime("2026-08-05T05:16:00Z"), "2026-08-05 13:16");
});

test("empty or invalid timestamps render as dash", () => {
  assert.equal(formatBeijingDateTime(null), "-");
  assert.equal(formatBeijingDateTime("not-a-date"), "-");
});
