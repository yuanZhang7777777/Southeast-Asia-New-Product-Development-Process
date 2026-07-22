import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import test from "node:test";

const mainSource = readFileSync(new URL("../src/main.tsx", import.meta.url), "utf8");
const densityStyleUrl = new URL("../src/listingDensity.css", import.meta.url);
const densityStyles = existsSync(densityStyleUrl) ? readFileSync(densityStyleUrl, "utf8") : "";

test("listing controls stay compact without stretched inputs or result rows", () => {
  assert.match(mainSource, /import "\.\/listingDensity\.css";/);
  assert.match(densityStyles, /\.listing-select-all input\s*\{[^}]*width:\s*auto;/);
  assert.match(densityStyles, /\.listing-select-all input\s*\{[^}]*min-height:\s*auto;/);
  assert.match(densityStyles, /\.listing-workbench-results\s*\{[^}]*align-content:\s*start;/);
  assert.match(densityStyles, /\.listing-batchbar\s*\{[^}]*flex-wrap:\s*nowrap;/);
  assert.match(
    densityStyles,
    /@media \(max-width: 900px\)\s*\{[\s\S]*?\.listing-batchbar\s*\{[^}]*flex-direction:\s*row;/
  );
  assert.match(
    densityStyles,
    /@media \(max-width: 560px\)\s*\{[\s\S]*?\.listing-batchbar\s*\{[^}]*flex-direction:\s*column;/
  );
});
