# Operator Claim Submit State Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在运营认领页清楚显示`待填写 / 已填写未提交 / 已提交`，并保证只有接口成功才清理草稿。

**Architecture:** 复用现有机会状态和最新认领字段，在`claimDrafts.ts`集中判断草稿是否相对已保存值发生变化。`App.tsx`只负责展示状态、选择按钮文案和按 API 成功结果清理草稿，不新增后端字段。

**Tech Stack:** React 19、TypeScript、Node test runner、Vite。

## Global Constraints

- 主管复核前原运营可以修改并重新提交，复核后保持现有禁止修改规则。
- 接口失败时保留草稿。
- 不新增数据库字段、后端接口或依赖。
- 页面不展示“写入数据库”等技术术语。

---

### Task 1: 公共提交状态判断

**Files:**
- Modify: `frontend/src/claimDrafts.ts`
- Test: `frontend/tests/claimDrafts.test.ts`

**Interfaces:**
- Produces: `claimSubmissionState(item, draft?) => "pending" | "dirty" | "submitted"`

- [ ] **Step 1: Write the failing test**

```ts
assert.equal(claimSubmissionState({ current_status: "assigned" }), "pending");
assert.equal(claimSubmissionState({ current_status: "assigned" }, { ...createClaimDraft(), claimDailySales: "6" }), "dirty");
assert.equal(claimSubmissionState({ current_status: "claim_submitted", latest_claim_result: "claim", latest_claim_daily_sales: 6 }), "submitted");
assert.equal(claimSubmissionState(saved, { ...createClaimDraftFromLatest(saved), claimDailySales: "8" }), "dirty");
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test --test-name-pattern="提交状态" tests/claimDrafts.test.ts`
Expected: FAIL because `claimSubmissionState` is not exported.

- [ ] **Step 3: Write minimal implementation**

```ts
export function claimSubmissionState(item, draft?) {
  const submitted = ["claim_submitted", "claim_rejected"].includes(item.current_status) && Boolean(item.latest_claim_result);
  if (!draft) return submitted ? "submitted" : "pending";
  const saved = createClaimDraftFromLatest(item);
  const changed =
    draft.mode !== saved.mode ||
    draft.claimDailySales.trim() !== saved.claimDailySales ||
    draft.rejectReason.trim() !== saved.rejectReason.trim() ||
    draft.researchConclusion.trim() !== saved.researchConclusion.trim() ||
    draft.evidenceImages.length > 0;
  return changed ? "dirty" : submitted ? "submitted" : "pending";
}
```

- [ ] **Step 4: Run focused test to verify it passes**

Run: `node --test --test-name-pattern="提交状态" tests/claimDrafts.test.ts`
Expected: PASS.

### Task 2: 页面状态、成功边界和文档

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`
- Modify: `docs/02-功能实现状态.md`

**Interfaces:**
- Consumes: `claimSubmissionState` from Task 1.
- Produces: list and drawer status labels; `runAction(...) => Promise<boolean>`.

- [ ] **Step 1: Integrate the three labels**

```tsx
<span className={`claim-save-state ${state}`}>
  {state === "submitted" ? "已提交" : state === "dirty" ? "已填写未提交" : "待填写"}
</span>
```

Use `提交修改` for dirty previously submitted rows, `已提交` for unchanged submitted rows, and `提交` otherwise.

- [ ] **Step 2: Preserve drafts on failure**

```ts
const submitted = await props.onSubmit(payload);
if (!submitted) return;
```

Make `runAction` return `true` only after the action succeeds, return `false` on error, and refresh silently so the success message is not overwritten by`已刷新`.

- [ ] **Step 3: Seed edits from saved values**

Before applying the first patch to an already submitted row, initialize its editable draft with `draftForOpportunity(item)` so editing one field does not erase other saved fields.

- [ ] **Step 4: Update the authoritative feature status**

Document the three labels, explicit submit boundary, pre-review edits, and failure draft retention in `docs/02-功能实现状态.md`.

- [ ] **Step 5: Verify**

Run: `npm test`
Expected: all frontend tests pass.

Run: `npm run build`
Expected: TypeScript and Vite production build pass.

- [ ] **Step 6: Commit and deploy**

Commit the implementation, build a frontend-only candidate container, verify it through Caddy, atomically reload Caddy, persist the new container target, and verify `/api/health` remains `production / ok`.
