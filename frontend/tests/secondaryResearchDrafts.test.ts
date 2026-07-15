import assert from "node:assert/strict";
import test from "node:test";

import {
  createSecondaryResearchDraft,
  incompleteSecondaryResearchItems,
  patchSecondaryResearchDraft,
  syncSecondaryResearchDraftPatch
} from "../src/secondaryResearchDrafts.ts";

test("服务器已有草稿会完整还原到对应子 SKU", () => {
  const draft = createSecondaryResearchDraft({
    secondary_research_at: "2026-07-12T14:08:00+08:00",
    secondary_competitor_url: "https://shopee.ph/item/1",
    secondary_conclusion: "市场价格稳定",
    product_positioning: "利润款",
    secondary_evidence_images: [{ name: "evidence.png", url: "/image.png" }]
  });

  assert.equal(draft.researchedAt, "2026-07-12T14:08");
  assert.equal(draft.competitorUrl, "https://shopee.ph/item/1");
  assert.equal(draft.positioning, "利润款");
  assert.equal(draft.evidenceImages.length, 1);
});

test("新建空草稿默认浏览器本地当前时间", () => {
  const draft = createSecondaryResearchDraft({}, new Date("2026-07-12T14:08:30"));

  assert.equal(draft.researchedAt, "2026-07-12T14:08");
});

test("首次填写同步空白子 SKU，直接改过的子 SKU 后续独立", () => {
  const current = {
    "claim-a1": createSecondaryResearchDraft(),
    "claim-a2": createSecondaryResearchDraft(),
    "claim-a3": createSecondaryResearchDraft()
  };
  const items = [
    { claim_record_id: "claim-a1", sub_sku: "SUB-A1" },
    { claim_record_id: "claim-a2", sub_sku: "SUB-A2" },
    { claim_record_id: "claim-a3", sub_sku: "SUB-A3" }
  ];
  const first = syncSecondaryResearchDraftPatch(current, items, "claim-a1", { conclusion: "首次复查" });
  const second = syncSecondaryResearchDraftPatch(first, items, "claim-a2", { conclusion: "保留我的内容" });
  const third = syncSecondaryResearchDraftPatch(second, items, "claim-a1", { positioning: "利润款" });

  assert.equal(first["claim-a2"].conclusion, "首次复查");
  assert.equal(first["claim-a3"].conclusion, "首次复查");
  assert.equal(third["claim-a1"].positioning, "利润款");
  assert.equal(third["claim-a2"].conclusion, "保留我的内容");
  assert.equal(third["claim-a2"].positioning, "");
  assert.equal(third["claim-a3"].positioning, "利润款");
});

test("连续输入时未直接编辑的子 SKU 持续跟随最新内容", () => {
  const current = {
    "claim-a1": createSecondaryResearchDraft(),
    "claim-a2": createSecondaryResearchDraft(),
    "claim-a3": createSecondaryResearchDraft()
  };
  const items = [
    { claim_record_id: "claim-a1", sub_sku: "SUB-A1" },
    { claim_record_id: "claim-a2", sub_sku: "SUB-A2" },
    { claim_record_id: "claim-a3", sub_sku: "SUB-A3" }
  ];

  const first = syncSecondaryResearchDraftPatch(current, items, "claim-a1", { conclusion: "市" });
  const second = syncSecondaryResearchDraftPatch(first, items, "claim-a1", { conclusion: "市场" });
  const third = syncSecondaryResearchDraftPatch(second, items, "claim-a2", { conclusion: "独立内容" });
  const fourth = syncSecondaryResearchDraftPatch(third, items, "claim-a1", { conclusion: "市场稳定" });

  assert.equal(second["claim-a2"].conclusion, "市场");
  assert.equal(second["claim-a3"].conclusion, "市场");
  assert.equal(fourth["claim-a2"].conclusion, "独立内容");
  assert.equal(fourth["claim-a3"].conclusion, "市场稳定");
});

test("整组提交只列出缺少 AN/AO 必填项的子 SKU", () => {
  const complete = {
    ...createSecondaryResearchDraft(),
    conclusion: "仍有利润",
    positioning: "利润款" as const
  };
  const missing = incompleteSecondaryResearchItems(
    [
      { claim_record_id: "claim-a", sub_sku: "SUB-A" },
      { claim_record_id: "claim-b", sub_sku: "SUB-B" }
    ],
    { "claim-a": complete, "claim-b": createSecondaryResearchDraft() }
  );

  assert.deepEqual(missing, ["SUB-B"]);
});
