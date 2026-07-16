import assert from "node:assert/strict";
import test from "node:test";

import { claimSubmissionState, createClaimDraft, createClaimDraftFromLatest, patchClaimDraftGroup } from "../src/claimDrafts.ts";

test("运营认领提交状态区分待填写、未提交和已提交", () => {
  const saved = {
    current_status: "claim_submitted",
    latest_claim_result: "claim",
    latest_claim_daily_sales: 6,
    latest_feedback_summary: "竞品稳定"
  };

  assert.equal(claimSubmissionState({ current_status: "assigned" }), "pending");
  assert.equal(
    claimSubmissionState(
      { current_status: "assigned" },
      { ...createClaimDraft(), claimDailySales: "6" }
    ),
    "dirty"
  );
  assert.equal(claimSubmissionState(saved), "submitted");
  assert.equal(claimSubmissionState(saved, createClaimDraftFromLatest(saved)), "submitted");
  assert.equal(
    claimSubmissionState(saved, { ...createClaimDraftFromLatest(saved), claimDailySales: "8" }),
    "dirty"
  );
});

test("已提交认领从最新单销和调研结论恢复草稿", () => {
  const draft = createClaimDraftFromLatest({
    latest_claim_result: "claim",
    latest_claim_daily_sales: 6,
    latest_feedback_summary: "竞品稳定"
  });

  assert.equal(draft.mode, "claim");
  assert.equal(draft.claimDailySales, "6");
  assert.equal(draft.researchConclusion, "竞品稳定");
});

test("已提交不认领从最新原因恢复草稿", () => {
  const draft = createClaimDraftFromLatest({
    latest_claim_result: "reject",
    latest_reject_reason: "利润不足",
    latest_feedback_summary: "不建议进入"
  });

  assert.equal(draft.mode, "reject");
  assert.equal(draft.rejectReason, "利润不足");
  assert.equal(draft.researchConclusion, "不建议进入");
});

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
