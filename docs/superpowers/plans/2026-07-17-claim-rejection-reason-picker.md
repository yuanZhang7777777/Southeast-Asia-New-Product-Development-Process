# Claim Rejection Reason Picker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace free-text-only claim rejection reasons with a reusable dropdown that supports one or many fixed reasons plus custom text while preserving the existing `reject_reason` string contract.

**Architecture:** Keep `ClaimDraft.rejectReason` as the single source of truth. Add pure parse/format helpers in `claimDrafts.ts`, then reuse one native `details`-based picker in both operator-claim editors; the backend, database, review view, exports, and group synchronization remain unchanged.

**Tech Stack:** React 19, TypeScript, native HTML `details`/checkbox/input controls, Node test runner, CSS, Vite.

## Global Constraints

- Provide exactly the 15 approved fixed reasons in the confirmed order.
- A single checked option is a valid single selection; multiple checked options are a valid multiple selection.
- Custom text may be used alone or together with fixed reasons.
- Serialize into the existing `reject_reason` string with Chinese semicolons `；`.
- Preserve historical custom text; do not migrate existing database rows.
- Do not add a backend endpoint, database field, dependency, deployment, or server restart.
- Do not stage or overwrite unrelated PLM documentation changes already present in the shared worktree.

---

### Task 1: Rejection Reason Value Model

**Files:**
- Modify: `frontend/src/claimDrafts.ts`
- Test: `frontend/tests/claimDrafts.test.ts`

**Interfaces:**
- Produces: `REJECT_REASON_OPTIONS: readonly string[]`.
- Produces: `parseRejectReason(value: string): { selected: string[]; custom: string }`.
- Produces: `formatRejectReason(selected: readonly string[], custom: string): string`.
- Consumes: the existing `ClaimDraftState.rejectReason` string without changing its type.

- [ ] **Step 1: Write the failing model tests**

Extend the import in `frontend/tests/claimDrafts.test.ts` and add:

```ts
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
```

- [ ] **Step 2: Run the focused tests and confirm RED**

Run:

```powershell
node --test tests/claimDrafts.test.ts
```

Expected: FAIL because `REJECT_REASON_OPTIONS`, `parseRejectReason`, and `formatRejectReason` are not exported.

- [ ] **Step 3: Implement the minimum pure helpers**

Add to `frontend/src/claimDrafts.ts`:

```ts
export const REJECT_REASON_OPTIONS = [
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
] as const;

export function parseRejectReason(value: string) {
  const parts = value.split("；").map((part) => part.trim()).filter(Boolean);
  const options = new Set<string>(REJECT_REASON_OPTIONS);
  return {
    selected: REJECT_REASON_OPTIONS.filter((option) => parts.includes(option)),
    custom: parts.filter((part) => !options.has(part)).join("；")
  };
}

export function formatRejectReason(selected: readonly string[], custom: string) {
  const selectedSet = new Set(selected);
  return [...REJECT_REASON_OPTIONS.filter((option) => selectedSet.has(option)), custom.trim()]
    .filter(Boolean)
    .join("；");
}
```

- [ ] **Step 4: Run the focused tests and confirm GREEN**

Run:

```powershell
node --test tests/claimDrafts.test.ts
```

Expected: all claim draft tests PASS.

- [ ] **Step 5: Commit the value model**

```powershell
git add -- frontend/src/claimDrafts.ts frontend/tests/claimDrafts.test.ts
git commit -m "feat: add claim rejection reason model"
```

---

### Task 2: Reusable Operator Rejection Reason Picker

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`
- Test: `frontend/tests/claimDrafts.test.ts`

**Interfaces:**
- Consumes: `REJECT_REASON_OPTIONS`, `parseRejectReason`, and `formatRejectReason` from Task 1.
- Produces: `RejectReasonPicker(props: { value: string; onChange: (value: string) => void })`.
- Keeps: `ClaimDraftEditor` and `ClaimMatrixDraftEditor` patching `{ rejectReason: string }`.

- [ ] **Step 1: Write the failing wiring test**

Add `readFileSync` and an App source fixture to `frontend/tests/claimDrafts.test.ts`:

```ts
import { readFileSync } from "node:fs";

const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");

test("运营列表和商品详情复用不认领原因选择器", () => {
  assert.equal(appSource.match(/<RejectReasonPicker/g)?.length, 2);
  const picker = appSource.slice(
    appSource.indexOf("function RejectReasonPicker"),
    appSource.indexOf("function pasteClaimEvidence")
  );
  assert.match(picker, /REJECT_REASON_OPTIONS\.map/);
  assert.match(picker, /type="checkbox"/);
  assert.match(picker, /placeholder="其他原因"/);
});
```

- [ ] **Step 2: Run the focused tests and confirm RED**

Run:

```powershell
node --test tests/claimDrafts.test.ts
```

Expected: FAIL because neither editor renders `RejectReasonPicker`.

- [ ] **Step 3: Import the model and implement one native picker**

Extend the `claimDrafts` import in `frontend/src/App.tsx` with `formatRejectReason`, `parseRejectReason`, and `REJECT_REASON_OPTIONS`. Add before `pasteClaimEvidence`:

```tsx
function RejectReasonPicker(props: { value: string; onChange: (value: string) => void }) {
  const parsed = parseRejectReason(props.value);
  const summary = props.value || "请选择或填写原因";

  return (
    <details className="reject-reason-picker">
      <summary title={props.value}>{parsed.selected.length ? `已选 ${parsed.selected.length} 项 · ${summary}` : summary}</summary>
      <div className="reject-reason-menu">
        <div className="reject-reason-options">
          {REJECT_REASON_OPTIONS.map((option) => (
            <label className="reject-reason-option" key={option}>
              <input
                checked={parsed.selected.includes(option)}
                onChange={(event) => props.onChange(formatRejectReason(
                  event.target.checked
                    ? [...parsed.selected, option]
                    : parsed.selected.filter((item) => item !== option),
                  parsed.custom
                ))}
                type="checkbox"
              />
              <span>{option}</span>
            </label>
          ))}
        </div>
        <label className="reject-reason-custom">
          <span>其他原因</span>
          <input
            onChange={(event) => props.onChange(formatRejectReason(parsed.selected, event.target.value))}
            placeholder="其他原因"
            value={parsed.custom}
          />
        </label>
      </div>
    </details>
  );
}
```

- [ ] **Step 4: Replace both free-text rejection inputs**

In `ClaimDraftEditor`, change the outer `claim-editor-field primary-field` element from `label` to `div` because the picker contains its own labels. Keep the number input for claim mode and render:

```tsx
<RejectReasonPicker
  onChange={(rejectReason) => props.onPatch({ rejectReason })}
  value={draft.rejectReason}
/>
```

for reject mode. In `ClaimMatrixDraftEditor`, likewise change the outer `claim-editor-field` element from `label` to `div`, split the combined input by mode, and render the same picker for reject mode with `props.draft.rejectReason`.

- [ ] **Step 5: Add compact dropdown styles**

Add to `frontend/src/styles.css` near the existing claim editor styles:

```css
.reject-reason-picker {
  position: relative;
  min-width: 0;
}

.reject-reason-picker[open] {
  z-index: 12;
}

.reject-reason-picker > summary {
  min-height: 32px;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 5px 8px;
  background: #fff;
  cursor: pointer;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.reject-reason-menu {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  z-index: 20;
  display: grid;
  gap: 8px;
  width: min(360px, calc(100vw - 48px));
  max-height: 360px;
  overflow-y: auto;
  padding: 10px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: #fff;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.14);
}

.reject-reason-options {
  display: grid;
  gap: 4px;
}

.reject-reason-option {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  padding: 4px;
}

.reject-reason-option input {
  width: 16px;
  min-height: 16px;
  margin-top: 2px;
  padding: 0;
}

.reject-reason-custom {
  display: grid;
  gap: 4px;
  padding-top: 8px;
  border-top: 1px solid var(--line);
}
```

- [ ] **Step 6: Run focused and complete frontend verification**

Run:

```powershell
node --test tests/claimDrafts.test.ts
npm test
npm run build
```

Expected: focused tests PASS, all frontend tests PASS, and TypeScript/Vite build succeeds.

- [ ] **Step 7: Commit the picker**

```powershell
git add -- frontend/src/App.tsx frontend/src/styles.css frontend/tests/claimDrafts.test.ts
git commit -m "feat: add rejection reason picker"
```

---

### Task 3: Durable Requirement and Handoff State

**Files:**
- Modify: `docs/01-需求文档-东南亚新品流程.md`
- Modify: `docs/02-功能实现状态.md`
- Modify: `docs/20-项目推进总控.md`

**Interfaces:**
- Consumes: verified Task 2 behavior and final test count.
- Produces: current business rule and implementation status; no runtime interface.

- [ ] **Step 1: Replace the stale custom-only requirement**

Update the role statement and operator-claim requirements in `docs/01-需求文档-东南亚新品流程.md` to state:

```text
不认领原因使用固定选项下拉，可单选或多选，并支持同时填写自定义原因；固定选项和自定义内容按中文分号保存在现有字段。
```

Remove the stale open question `不认领原因是否必须从枚举选择。` without changing unrelated PLM documentation.

- [ ] **Step 2: Record implementation status**

Update the operator claim row in `docs/02-功能实现状态.md` and `docs/20-项目推进总控.md` with the verified picker behavior and actual final frontend test count. Keep the status as not deployed.

- [ ] **Step 3: Verify only task-owned documentation is staged**

Run:

```powershell
git diff --check
git diff --cached --name-only
git status --short
```

Expected: no whitespace errors; only this feature's intended documentation hunks are staged. Existing PLM worktree changes remain unstaged and intact.

- [ ] **Step 4: Run final verification from committed code**

Run:

```powershell
npm test
npm run build
git diff --check
```

Expected: all frontend tests PASS, TypeScript/Vite build succeeds, and no diff errors are reported.

- [ ] **Step 5: Commit the documentation update**

```powershell
git commit -m "docs: record rejection reason picker"
```

Do not push, deploy, restart, or stage the unrelated PLM documentation changes.
