import type { Selection1ImportResponse } from "./api";

export type ImportKind = 1 | 2;
export type ImportResults = Partial<Record<ImportKind, Selection1ImportResponse>>;

export function recordImportResult(
  current: ImportResults,
  kind: ImportKind,
  result: Selection1ImportResponse
): ImportResults {
  return { ...current, [kind]: result };
}
