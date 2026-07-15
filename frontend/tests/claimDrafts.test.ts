import assert from "node:assert/strict";
import test from "node:test";

import { createClaimDraft, patchClaimDraftGroup } from "../src/claimDrafts.ts";

test("同一主 SKU 的认领与不认领保持独立", () => {
  const claimed = { ...createClaimDraft(), mode: "claim" as const, claimDailySales: "6" };
  const drafts = {
    first: claimed,
    second: createClaimDraft()
  };

  const next = patchClaimDraftGroup(
    drafts,
    "second",
    { mode: "reject", rejectReason: "价格无优势", researchConclusion: "同款竞争激烈" },
    ["first", "second", "third"],
    true
  );

  assert.deepEqual(next.first, claimed);
  assert.equal(next.second.mode, "reject");
  assert.equal(next.second.rejectReason, "价格无优势");
  assert.equal(next.third.mode, "reject");
  assert.equal(next.third.rejectReason, "价格无优势");
});

test("首个子 SKU 的认领单销只同步未填写项", () => {
  const drafts = {
    first: createClaimDraft(),
    rejected: { ...createClaimDraft(), mode: "reject" as const, rejectReason: "价格无优势" },
    pending: createClaimDraft(),
    edited: { ...createClaimDraft(), claimDailySales: "9" }
  };

  const firstInput = patchClaimDraftGroup(
    drafts,
    "first",
    { claimDailySales: "6" },
    ["first", "rejected", "pending", "edited"],
    false,
    true
  );

  assert.equal(firstInput.pending.claimDailySales, "6");
  assert.equal(firstInput.rejected.mode, "reject");
  assert.equal(firstInput.rejected.rejectReason, "价格无优势");
  assert.equal(firstInput.edited.claimDailySales, "9");

  const corrected = patchClaimDraftGroup(
    firstInput,
    "first",
    { claimDailySales: "8" },
    ["first", "rejected", "pending", "edited"],
    false,
    true
  );

  assert.equal(corrected.pending.claimDailySales, "8");
  assert.equal(corrected.edited.claimDailySales, "9");
});
