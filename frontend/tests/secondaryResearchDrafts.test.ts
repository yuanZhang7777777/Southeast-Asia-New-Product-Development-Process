import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  createSecondaryResearchDraft,
  filterSecondaryResearchGroups,
  incompleteSecondaryResearchItems,
  patchSecondaryResearchDraft,
  researchLinkLabels,
  SECONDARY_RESEARCH_POSITIONINGS,
  SECONDARY_RESEARCH_SKIP_LISTING,
  syncSecondaryResearchDraftPatch
} from "../src/secondaryResearchDrafts.ts";

const secondaryResearchViewSource = readFileSync(new URL("../src/SecondaryResearchView.tsx", import.meta.url), "utf8");
const apiSource = readFileSync(new URL("../src/api.ts", import.meta.url), "utf8");

test("二次调研页面使用短期缓存避免切页重复全量拉取", () => {
  assert.match(secondaryResearchViewSource, /cachedValue<SecondaryResearchGroup\[\]>/);
  assert.match(secondaryResearchViewSource, /setCachedValue\(cacheKey, result\)/);
});

test("二次调研按场景和组合条件精确筛选国家及子 SKU", () => {
  const groups = [
    {
      country: "PH",
      business_period: "开发0710期",
      salesperson_name: "运营甲",
      main_sku: "MAIN-PH",
      main_sku_name: "菲律宾主品",
      items: [{ sub_sku: "SUB-PH", sub_sku_name: "蓝色", secondary_research_submitted_at: null, downstream_status: "waiting_secondary_research" }]
    },
    {
      country: "TH",
      business_period: "开发0710期",
      salesperson_name: "运营乙",
      main_sku: "MAIN-TH",
      main_sku_name: "泰国主品",
      items: [{ sub_sku: "SUB-TH", sub_sku_name: "红色", secondary_research_submitted_at: "2026-07-23T09:00:00Z", downstream_status: "waiting_listing" }]
    },
    {
      country: null,
      business_period: "开发0710期",
      salesperson_name: "运营甲",
      main_sku: "MAIN-NONE",
      main_sku_name: "无国家主品",
      items: [{ sub_sku: "SUB-NONE", sub_sku_name: "绿色", secondary_research_submitted_at: null, downstream_status: "waiting_secondary_research" }]
    },
    {
      country: "VN",
      business_period: "开发0710期",
      salesperson_name: "运营甲",
      main_sku: "MAIN-NOT-SUBMITTED",
      main_sku_name: "尚未进入二次调研",
      items: [{ sub_sku: "SUB-NOT-SUBMITTED", secondary_research_submitted_at: null, downstream_status: "waiting_arrival" }]
    }
  ];

  assert.deepEqual(
    filterSecondaryResearchGroups(groups, {
      scenario: "pending",
      query: "蓝色",
      country: "PH",
      businessPeriod: "开发0710期",
      salespersonName: "运营甲"
    }).map((group) => group.main_sku),
    ["MAIN-PH"]
  );
  assert.deepEqual(
    filterSecondaryResearchGroups(groups, { scenario: "submitted" }).map((group) => group.main_sku),
    ["MAIN-TH"]
  );
  assert.deepEqual(
    filterSecondaryResearchGroups(groups, { scenario: "pending", country: "PH" }).map((group) => group.main_sku),
    ["MAIN-PH"]
  );
  assert.equal(filterSecondaryResearchGroups(groups, { scenario: "submitted", country: "VN" }).length, 0);
  assert.equal(filterSecondaryResearchGroups(groups, { scenario: "pending", country: "VN" }).length, 0);
});

test("二次调研支持五种定位且只有淘汰款和清仓款跳过刊登", () => {
  assert.deepEqual(SECONDARY_RESEARCH_POSITIONINGS, ["引流款", "利润款", "淘汰款", "稳定款", "清仓款"]);
  assert.deepEqual([...SECONDARY_RESEARCH_SKIP_LISTING], ["淘汰款", "清仓款"]);
});

test("服务器已有草稿会完整还原到对应子 SKU 且不生成可编辑 AL", () => {
  const draft = createSecondaryResearchDraft({
    secondary_research_at: "2026-07-12T14:08:00+08:00",
    secondary_competitor_url: "https://shopee.ph/item/1",
    secondary_conclusion: "市场价格稳定",
    product_positioning: "利润款",
    secondary_target_daily_sales: 12,
    secondary_selling_points: "可折叠，适合海外仓",
    secondary_evidence_images: [{ name: "evidence.png", url: "/image.png" }]
  });

  assert.equal("researchedAt" in draft, false);
  assert.equal(draft.competitorUrl, "https://shopee.ph/item/1");
  assert.equal(draft.positioning, "利润款");
  assert.equal(draft.targetDailySales, "12");
  assert.equal(draft.sellingPoints, "可折叠，适合海外仓");
  assert.equal(draft.evidenceImages.length, 1);
});

test("新建空草稿不再默认浏览器本地当前时间", () => {
  const draft = createSecondaryResearchDraft({}, new Date("2026-07-12T14:08:30"));

  assert.equal("researchedAt" in draft, false);
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
  const first = syncSecondaryResearchDraftPatch(current, items, "claim-a1", { conclusion: "首次复查", targetDailySales: "12" });
  const second = syncSecondaryResearchDraftPatch(first, items, "claim-a2", { conclusion: "保留我的内容" });
  const third = syncSecondaryResearchDraftPatch(second, items, "claim-a1", { positioning: "利润款", sellingPoints: "卖点明确" });

  assert.equal(first["claim-a2"].conclusion, "首次复查");
  assert.equal(first["claim-a3"].targetDailySales, "12");
  assert.equal(third["claim-a1"].positioning, "利润款");
  assert.equal(third["claim-a2"].conclusion, "保留我的内容");
  assert.equal(third["claim-a2"].positioning, "");
  assert.equal(third["claim-a2"].sellingPoints, "");
  assert.equal(third["claim-a3"].positioning, "利润款");
  assert.equal(third["claim-a3"].sellingPoints, "卖点明确");
});


test("二次调研同步跟随的子 SKU 也进入自动保存队列", () => {
  assert.match(secondaryResearchViewSource, /pendingSyncedSaveIds/);
  assert.match(secondaryResearchViewSource, /syncedDraftFields\.some\(\(key\) => key in patch\)/);
  assert.match(secondaryResearchViewSource, /savePendingSyncedDrafts\(item\.claim_record_id\)\.catch\(\(\) => undefined\)/);
  assert.match(secondaryResearchViewSource, /saveDraft\(syncedItem, syncedDraft, \{ saveSynced: false \}\)/);
  assert.match(secondaryResearchViewSource, /pendingSyncedSaveRevision/);
  assert.match(secondaryResearchViewSource, /Object\.entries\(pending \|\| \{\}\)/);
  assert.match(secondaryResearchViewSource, /pending\?\.\[claimRecordId\] === revision/);
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

test("整组提交只列出缺少必填项的子 SKU", () => {
  const complete = {
    ...createSecondaryResearchDraft(),
    conclusion: "仍有利润",
    positioning: "利润款" as const,
    targetDailySales: "12",
    sellingPoints: "卖点明确"
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

test("二次调研混合组按场景裁剪条目，已提交条目不会回到待处理", () => {
  const groups = [{
    country: "PH",
    business_period: "开发0710期",
    salesperson_name: "运营甲",
    main_sku: "MAIN-1",
    items: [
      { sub_sku: "SUB-PENDING", secondary_research_submitted_at: null, downstream_status: "waiting_secondary_research" },
      { sub_sku: "SUB-DONE", secondary_research_submitted_at: "2026-07-23T09:00:00Z", downstream_status: "waiting_listing" }
    ]
  }];

  assert.deepEqual(filterSecondaryResearchGroups(groups, { scenario: "pending" })[0].items.map((item) => item.sub_sku), ["SUB-PENDING"]);
  assert.deepEqual(filterSecondaryResearchGroups(groups, { scenario: "submitted" })[0].items.map((item) => item.sub_sku), ["SUB-DONE"]);
});


test("二次调研填写区使用锚定链接和新增字段且不再编辑 AL", () => {
  assert.match(secondaryResearchViewSource, /锚定链接/);
  assert.match(secondaryResearchViewSource, /目标单销/);
  assert.match(secondaryResearchViewSource, /卖点总结/);
  assert.match(secondaryResearchViewSource, /提交后自动记录|自动记录/);
  assert.doesNotMatch(secondaryResearchViewSource, /type="datetime-local"/);
  assert.doesNotMatch(secondaryResearchViewSource, /placeholder="竞品链接"/);
});

test("二次调研支持手工新增之前没有的 SKU", () => {
  assert.match(secondaryResearchViewSource, /新增二调 SKU/);
  assert.match(secondaryResearchViewSource, /createManualSecondaryResearch/);
  assert.match(apiSource, /\/secondary-research\/manual/);
});

test("源表链接按实际 URL 编号，重复链接显示同链接编号", () => {
  assert.deepEqual(
    researchLinkLabels(["https://a.example/item", "https://b.example/item", "https://a.example/item"]).map((item) => item.label),
    ["链接1", "链接2", "同链接1"]
  );
  assert.match(secondaryResearchViewSource, /research-link-chip/);
});
