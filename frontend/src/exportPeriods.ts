export type ExportPeriodLike = { business_period: string };
export type ExportPeriodRowLike = { business_period?: string | null };

export function selectExportPeriod(periods: readonly ExportPeriodLike[], current: string) {
  return current && periods.some((period) => period.business_period === current)
    ? current
    : periods[0]?.business_period || "";
}

export function filterRowsForExportPeriod<T extends ExportPeriodRowLike>(rows: readonly T[], businessPeriod: string): T[] {
  return businessPeriod ? rows.filter((row) => row.business_period === businessPeriod) : [];
}

export function exportPeriodFilter(businessPeriod: string) {
  if (!businessPeriod) throw new Error("请选择业务期数");
  return { business_period: businessPeriod };
}
