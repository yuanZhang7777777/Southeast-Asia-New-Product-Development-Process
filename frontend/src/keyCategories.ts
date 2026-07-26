import type { CompanyCategory, OperatorCategorySelection } from "./api";

export const KEY_CATEGORY_LEVEL1_LIMIT = 3;
export const KEY_CATEGORY_LEVEL2_LIMIT = 2;

export function categorySelectionKey(selection: Pick<OperatorCategorySelection, "level1" | "level2">) {
  return selection.level1 + "|||" + (selection.level2 || "");
}

export function categorySelectionLabel(selection: Pick<OperatorCategorySelection, "level1" | "level2">) {
  return selection.level2 ? selection.level1 + " / " + selection.level2 : selection.level1;
}

export function normalizeCategorySelections(values: Array<OperatorCategorySelection | null | undefined>): OperatorCategorySelection[] {
  const wholeLevel1 = new Set(values.map((item) => item?.level2 ? "" : item?.level1?.trim()).filter(Boolean));
  const seen = new Set<string>();
  const output: OperatorCategorySelection[] = [];
  for (const item of values) {
    const level1 = item?.level1?.trim();
    const level2 = item?.level2?.trim() || null;
    if (!level1 || (level2 && wholeLevel1.has(level1))) continue;
    const key = categorySelectionKey({ level1, level2 });
    if (seen.has(key)) continue;
    seen.add(key);
    output.push({ level1, level2 });
  }
  return output;
}

export function categoryLevel1Options(categories: readonly Pick<CompanyCategory, "level1">[]): string[] {
  return Array.from(new Set(categories.map((item) => item.level1.trim()).filter(Boolean))).sort((left, right) =>
    left.localeCompare(right, "zh-CN")
  );
}

export function categoryLevel2Options(
  categories: readonly Pick<CompanyCategory, "level1" | "level2">[],
  level1: string
): string[] {
  const values = categories
    .filter((item) => item.level1.trim() === level1.trim())
    .map((item) => item.level2?.trim() || "")
    .filter(Boolean);
  return Array.from(new Set(values)).sort((left, right) => left.localeCompare(right, "zh-CN"));
}

export type AddKeyCategoryResult =
  | { selections: OperatorCategorySelection[]; error?: undefined }
  | { selections?: undefined; error: string };

export function addKeyCategory(
  current: readonly OperatorCategorySelection[],
  candidate: OperatorCategorySelection
): AddKeyCategoryResult {
  const level1 = candidate.level1?.trim() || "";
  const level2 = candidate.level2?.trim() || null;
  if (!level1) return { error: "请先选择一级类目" };
  const selected = normalizeCategorySelections([...current]);
  const sameLevel1 = selected.filter((item) => item.level1 === level1);
  const level1Groups = new Set(selected.map((item) => item.level1));
  if (!level1Groups.has(level1) && level1Groups.size >= KEY_CATEGORY_LEVEL1_LIMIT) {
    return { error: `最多添加 ${KEY_CATEGORY_LEVEL1_LIMIT} 组一级类目` };
  }
  if (!level2) {
    if (sameLevel1.some((item) => !item.level2)) return { error: "该一级类目已添加" };
    // 选整个一级时替换该一级下已有的二级选择。
    return { selections: normalizeCategorySelections([...selected.filter((item) => item.level1 !== level1), { level1, level2: null }]) };
  }
  if (sameLevel1.some((item) => !item.level2)) return { error: "已选择整个一级类目，无需再选二级" };
  if (sameLevel1.some((item) => item.level2 === level2)) return { error: "该类目已添加" };
  if (sameLevel1.length >= KEY_CATEGORY_LEVEL2_LIMIT) {
    return { error: `每组一级类目最多选择 ${KEY_CATEGORY_LEVEL2_LIMIT} 个二级类目` };
  }
  return { selections: normalizeCategorySelections([...selected, { level1, level2 }]) };
}

export function removeKeyCategory(
  current: readonly OperatorCategorySelection[],
  target: OperatorCategorySelection
): OperatorCategorySelection[] {
  const key = categorySelectionKey(target);
  return normalizeCategorySelections([...current]).filter((item) => categorySelectionKey(item) !== key);
}
