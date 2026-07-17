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
  const conclusionStart = secondary.lastIndexOf("<span>AN 调研结论</span>");
  const conclusion = secondary.slice(conclusionStart, secondary.indexOf("<span>AO 商品定位</span>", conclusionStart));
  const uploadStart = secondary.indexOf('className="research-upload"');
  const upload = secondary.slice(uploadStart, secondary.indexOf("</label>", uploadStart));
  assert.match(conclusion, /onPaste=\{\(event: ClipboardEvent<HTMLTextAreaElement>\) => void uploadImages\(item, event\.clipboardData\.files\)\}/);
  assert.match(upload, /onDrop=\{\(event\) => \{ event\.preventDefault\(\); void uploadImages\(item, event\.dataTransfer\.files\); \}\}/);
  assert.match(upload, /onPaste=\{\(event\) => void uploadImages\(item, event\.clipboardData\.files\)\}/);
  assert.doesNotMatch(secondary, /document\.addEventListener\(["']paste/);
});

function deferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

async function keyedQueue() {
  const { createKeyedSaveQueue } = await import("../src/imageUploads.ts");
  return createKeyedSaveQueue();
}

async function flushQueue() {
  await new Promise<void>((resolve) => setTimeout(resolve, 0));
}

test("same claim saves start in call order", async () => {
  const queue = await keyedQueue();
  const first = deferred<void>();
  const second = deferred<void>();
  const started: string[] = [];
  const firstSave = queue("claim-1", async () => {
    started.push("first");
    await first.promise;
  });
  const secondSave = queue("claim-1", async () => {
    started.push("second");
    await second.promise;
  });

  await flushQueue();
  assert.deepEqual(started, ["first"]);
  first.resolve();
  await firstSave;
  await flushQueue();
  assert.deepEqual(started, ["first", "second"]);
  second.resolve();
  await secondSave;
});

test("a rejected save does not block the next save for the same claim", async () => {
  const queue = await keyedQueue();
  const first = deferred<void>();
  const second = deferred<void>();
  const started: string[] = [];
  const failedSave = queue("claim-1", async () => {
    started.push("first");
    await first.promise;
  });
  const nextSave = queue("claim-1", async () => {
    started.push("second");
    await second.promise;
  });

  const failure = assert.rejects(failedSave);
  await flushQueue();
  first.reject(new Error("save failed"));
  await failure;
  await Promise.resolve();
  assert.deepEqual(started, ["first", "second"]);
  second.resolve();
  await nextSave;
});

test("different claim save queues start independently", async () => {
  const queue = await keyedQueue();
  const first = deferred<void>();
  const second = deferred<void>();
  const started: string[] = [];
  const firstSave = queue("claim-1", async () => {
    started.push("claim-1");
    await first.promise;
  });
  const secondSave = queue("claim-2", async () => {
    started.push("claim-2");
    await second.promise;
  });

  await flushQueue();
  assert.deepEqual(started.sort(), ["claim-1", "claim-2"]);
  first.resolve();
  second.resolve();
  await Promise.all([firstSave, secondSave]);
});

test("operator evidence updates use current drafts and surface upload failures", () => {
  const workspace = app.slice(app.indexOf("function ClaimView"), app.indexOf("function claimSubmitButtonText"));
  const upload = app.slice(app.indexOf("async function readEvidenceFile"), app.indexOf("function formatDate"));
  const picker = app.slice(app.indexOf("function EvidencePicker"));

  assert.match(workspace, /function addEvidence[\s\S]*?props\.setDrafts\(\(current\) => \{[\s\S]*?evidenceImages: \[\.\.\.draft\.evidenceImages, \.\.\.images\]/);
  assert.match(workspace, /function removeEvidence[\s\S]*?props\.setDrafts\(\(current\) => \{[\s\S]*?evidenceImages: draft\.evidenceImages\.filter/);
  assert.doesNotMatch(upload, /FileReader|catch\s*\(/);
  assert.match(app, /function pasteClaimEvidence[\s\S]*?\.catch\(showUploadError\)/);
  assert.match(picker, /props\.onFiles\(files\)\.catch\(showUploadError\)/);
});

test("secondary research only lets the latest queued save set final status", () => {
  const saveDraft = secondary.slice(secondary.indexOf("async function saveDraft"), secondary.indexOf("async function uploadImages"));

  assert.match(secondary, /const saveRevision = useRef<Record<string, number>>\(\{\}\)/);
  assert.match(saveDraft, /const revision = \(saveRevision\.current\[item\.claim_record_id\] \?\? 0\) \+ 1/);
  assert.match(saveDraft, /saveRevision\.current\[item\.claim_record_id\] = revision/);
  assert.match(saveDraft, /if \(saveRevision\.current\[item\.claim_record_id\] === revision\) \{[\s\S]*?"已保存"/);
  assert.match(saveDraft, /catch \(error\) \{[\s\S]*?if \(saveRevision\.current\[item\.claim_record_id\] === revision\) \{[\s\S]*?"保存失败"/);
});
