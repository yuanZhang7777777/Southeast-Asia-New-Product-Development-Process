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
