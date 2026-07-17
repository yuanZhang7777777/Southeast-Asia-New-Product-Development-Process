import assert from "node:assert/strict";
import test from "node:test";

import {
  claimSubmissionState,
  createClaimDraft,
  createClaimDraftFromLatest,
  formatRejectReason,
  parseClaimEvidenceImages,
  parseRejectReason,
  patchClaimDraftGroup,
  REJECT_REASON_OPTIONS
} from "../src/claimDrafts.ts";

test("不认领原因提供确认的固定选项", () => {
  assert.deepEqual(REJECT_REASON_OPTIONS, [
    "稳定期利润率过低",
    "产品生命周期过短",
    "市场需求量过小",
    "调研数据不真实",
    "侵权/违规风险过高",
    "产品需认证资质",
    "抛货/重货/易碎品",
    "系统已有同款",
    "竞对销量差",
    "之前卖过类似款无销量",
    "市场竞对过多，优势不明显",
    "系统类似款成本更低",
    "近期销量下跌",
    "属性价差超5倍",
    "老链接垄断，同类型产品市场竞争大"
  ]);
});

test("不认领原因按固定顺序合并多选和自定义内容", () => {
  const parsed = parseRejectReason("产品生命周期过短；稳定期利润率过低；临时补充");
  assert.deepEqual(parsed, {
    selected: ["稳定期利润率过低", "产品生命周期过短"],
    custom: "临时补充"
  });
  assert.equal(
    formatRejectReason(["产品生命周期过短", "稳定期利润率过低"], "临时补充"),
    "稳定期利润率过低；产品生命周期过短；临时补充"
  );
  assert.deepEqual(parseRejectReason("历史自由文本"), { selected: [], custom: "历史自由文本" });
});

test("历史认领图片从已提交 note 恢复", () => {
  assert.deepEqual(
    parseClaimEvidenceImages(JSON.stringify({
      evidence_images: [{ name: "market.png", type: "image/png", size: 123, url: "/uploaded-sources/market.png" }]
    })),
    [{ name: "market.png", type: "image/png", size: 123, url: "/uploaded-sources/market.png" }]
  );
  assert.deepEqual(parseClaimEvidenceImages("不是 JSON"), []);
});

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

test("恢复已提交图片不会误报未提交，增删图片才标记修改", () => {
  const saved = {
    current_status: "claim_submitted",
    latest_claim_result: "claim",
    latest_claim_daily_sales: 6,
    latest_claim_note: JSON.stringify({ evidence_images: [{ name: "saved.png", url: "/saved.png" }] })
  };
  const draft = {
    ...createClaimDraftFromLatest(saved),
    evidenceImages: [{ name: "saved.png", url: "/saved.png" }]
  };

  assert.equal(claimSubmissionState(saved, draft), "submitted");
  assert.equal(
    claimSubmissionState(saved, { ...draft, evidenceImages: [...draft.evidenceImages, { name: "new.png" }] }),
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
