# Image Paste Upload Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every operator-claim and secondary-research image entry accept file selection, drag/drop, and clipboard paste, including image paste from the current row's research-conclusion input.

**Architecture:** Keep the existing `POST /claims/evidence-images` API and current previews. Add one native file-filter helper shared by both pages, route only row-scoped DOM events to the existing upload functions, and make secondary-research uploads merge against the latest draft so an upload cannot overwrite text typed while the request is in flight.

**Tech Stack:** React 19, TypeScript, native Clipboard/Drag events, Node test runner, Vite.

## Global Constraints

- Cover both `运营认领` and `二次调研`.
- Mixed text-and-image paste keeps the text and uploads every clipboard image to the current child SKU.
- Do not add a global paste listener, backend endpoint, database field, or dependency.
- Keep the existing backend image-only and 8MB-per-image validation.
- Do not deploy or restart any environment.

---

### Task 1: Row-scoped image selection, drag and paste

**Files:**
- Create: `frontend/src/imageUploads.ts`
- Create: `frontend/tests/imageUploads.test.ts`
- Modify: `frontend/package.json`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/SecondaryResearchView.tsx`

**Interfaces:**
- Produces: `imageFiles(files: FileList | File[] | null | undefined): File[]`.
- Consumes: existing `api.uploadClaimEvidence(opportunityId, file)`, `readEvidenceFiles(...)`, `EvidencePicker`, and secondary-research `saveDraft(...)`.

- [ ] **Step 1: Write the failing test**

Create `frontend/tests/imageUploads.test.ts` with a helper test and source-level wiring checks:

```ts
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { imageFiles } from "../src/imageUploads.ts";

const app = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const secondary = readFileSync(new URL("../src/SecondaryResearchView.tsx", import.meta.url), "utf8");

test("only image clipboard and drop files are accepted", () => {
  const png = { type: "image/png" } as File;
  const text = { type: "text/plain" } as File;
  assert.deepEqual(imageFiles([png, text]), [png]);
  assert.deepEqual(imageFiles(null), []);
});

test("claim conclusion fields paste images without blocking text paste", () => {
  const detail = app.slice(app.indexOf("function ClaimDraftEditor"), app.indexOf("function ClaimDetailDrawer"));
  const matrix = app.slice(app.indexOf("function ClaimMatrixDraftEditor"), app.indexOf("function draftForId"));
  assert.match(detail, /onPaste=.*pasteClaimEvidence/);
  assert.match(matrix, /onPaste=.*pasteClaimEvidence/);
  assert.doesNotMatch(app.slice(app.indexOf("function pasteClaimEvidence"), app.indexOf("function EvidencePicker")), /preventDefault/);
});

test("secondary research conclusion and image control are row-scoped paste and drop targets", () => {
  assert.match(secondary, /AN 调研结论[\s\S]*onPaste=.*uploadImages/);
  assert.match(secondary, /research-upload[\s\S]*onDrop=.*uploadImages/);
  assert.match(secondary, /research-upload[\s\S]*onPaste=.*uploadImages/);
  assert.doesNotMatch(secondary, /document\.addEventListener\(["']paste/);
});
```

Append `tests/imageUploads.test.ts` to the existing `frontend/package.json` test command.

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `node --test --test-name-pattern="image|paste|clipboard|row-scoped" tests/imageUploads.test.ts`

Expected: FAIL because `frontend/src/imageUploads.ts` and the new event wiring do not exist.

- [ ] **Step 3: Add the native image filter**

Create `frontend/src/imageUploads.ts`:

```ts
export function imageFiles(files: FileList | File[] | null | undefined): File[] {
  return Array.from(files || []).filter((file) => file.type.startsWith("image/"));
}
```

- [ ] **Step 4: Wire operator-claim conclusion paste**

In `frontend/src/App.tsx`, import `imageFiles`, use it inside `readEvidenceFiles` and `EvidencePicker`, and add this row-scoped helper:

```ts
function pasteClaimEvidence(
  event: ClipboardEvent<HTMLInputElement | HTMLTextAreaElement>,
  opportunityId: string,
  onAdd: (images: EvidenceImage[]) => void
) {
  const files = imageFiles(event.clipboardData.files);
  if (files.length) void readEvidenceFiles(files, opportunityId).then(onAdd);
}
```

Attach the same handler to the compact input, detail textarea, and matrix input:

```tsx
onPaste={(event) => pasteClaimEvidence(event, props.item.id, props.onAddEvidence)}
```

Do not call `preventDefault`, so pasted text continues through the existing controlled input `onChange`.

- [ ] **Step 5: Wire secondary-research selection, drag and paste without stale draft overwrite**

In `frontend/src/SecondaryResearchView.tsx`, import `ClipboardEvent`, `DragEvent`, `useRef`, and `imageFiles`. Keep the latest draft map available synchronously:

```ts
const [drafts, setDrafts] = useState<DraftMap>({});
const draftsRef = useRef<DraftMap>({});

function replaceDrafts(next: DraftMap) {
  draftsRef.current = next;
  setDrafts(next);
}

function updateDraft(claimRecordId: string, patch: Partial<SecondaryResearchDraft<UploadedEvidenceImage>>) {
  replaceDrafts(
    group
      ? syncSecondaryResearchDraftPatch(draftsRef.current, group.items, claimRecordId, patch)
      : patchSecondaryResearchDraft(draftsRef.current, claimRecordId, patch)
  );
}
```

Use `replaceDrafts(...)` when loading initial drafts and removing an image. Change upload to accept every native file source and merge after the request against the latest draft:

```ts
async function uploadImages(item: SecondaryResearchItem, source: FileList | File[]) {
  const files = imageFiles(source);
  if (!files.length) return;
  setSaveState((current) => ({ ...current, [item.claim_record_id]: "上传中" }));
  try {
    const uploaded = await Promise.all(files.map((file) => api.uploadClaimEvidence(item.opportunity_id, file)));
    const currentDraft = draftsRef.current[item.claim_record_id] || createSecondaryResearchDraft<UploadedEvidenceImage>();
    const nextDraft = { ...currentDraft, evidenceImages: [...currentDraft.evidenceImages, ...uploaded] };
    replaceDrafts({ ...draftsRef.current, [item.claim_record_id]: nextDraft });
    await saveDraft(item, nextDraft).catch(() => undefined);
  } catch (error) {
    setSaveState((current) => ({ ...current, [item.claim_record_id]: "上传失败" }));
    props.onStatus(error instanceof Error ? error.message : `${item.sub_sku} 图片上传失败`);
  }
}
```

Attach row-scoped paste to `AN 调研结论` without preventing text paste:

```tsx
onPaste={(event: ClipboardEvent<HTMLTextAreaElement>) => void uploadImages(item, event.clipboardData.files)}
```

Make the existing image label the drop and paste target; only drop prevents browser file navigation:

```tsx
<label
  className="research-upload"
  title="添加调研图片"
  tabIndex={0}
  onDragOver={(event: DragEvent<HTMLLabelElement>) => event.preventDefault()}
  onDrop={(event) => {
    event.preventDefault();
    void uploadImages(item, event.dataTransfer.files);
  }}
  onPaste={(event) => void uploadImages(item, event.clipboardData.files)}
>
```

The file input copies its `FileList` before resetting:

```tsx
onChange={(event) => {
  const files = imageFiles(event.currentTarget.files);
  event.currentTarget.value = "";
  void uploadImages(item, files);
}}
```

- [ ] **Step 6: Run the focused test and frontend suite**

Run: `node --test --test-name-pattern="image|paste|clipboard|row-scoped" tests/imageUploads.test.ts`

Expected: PASS.

Run: `npm test`

Expected: all frontend tests PASS.

- [ ] **Step 7: Commit the behavior change**

```bash
git add frontend/package.json frontend/src/imageUploads.ts frontend/src/App.tsx frontend/src/SecondaryResearchView.tsx frontend/tests/imageUploads.test.ts
git commit -m "feat: paste images into research rows"
```

### Task 2: Verification and durable status

**Files:**
- Modify: `docs/02-功能实现状态.md`
- Modify: `docs/20-项目推进总控.md`

**Interfaces:**
- Consumes: completed Task 1 behavior and verification output.
- Produces: durable implementation and release-status record; no runtime interface.

- [ ] **Step 1: Record the implemented behavior**

Update the `运营认领` row in `docs/02-功能实现状态.md` with this capability text:

```text
图片支持选择、拖拽和 Ctrl+V 粘贴；在当前子 SKU 的调研结论中粘贴图片会自动上传且保留同时粘贴的文字。
```

Update the `后段二次调研` row in `docs/20-项目推进总控.md` with this capability text:

```text
调研图片支持选择、拖拽和 Ctrl+V 粘贴，调研结论粘贴图片自动归入当前子 SKU。
```

Keep deployment state as development baseline only and do not claim this commit is deployed.

- [ ] **Step 2: Run final verification**

Run: `npm test`

Expected: all frontend tests PASS.

Run: `npm run build`

Expected: TypeScript and Vite build PASS.

Run: `git diff --check`

Expected: no output.

- [ ] **Step 3: Commit documentation and verification state**

```bash
git add docs/02-功能实现状态.md docs/20-项目推进总控.md
git commit -m "docs: record image paste upload support"
```
