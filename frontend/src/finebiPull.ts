const WEEK_LABEL_PATTERN = /^\d{4}-\d{4}$/;

function mmdd(value: Date): string {
  return `${String(value.getMonth() + 1).padStart(2, "0")}${String(value.getDate()).padStart(2, "0")}`;
}

/** FineBI 周区间为周四~周三；默认取今天之前最近一个完整区间（结束于上一个周三）。 */
export function defaultFineBIWeekLabel(today: Date = new Date()): string {
  const end = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const offset = (end.getDay() - 3 + 7) % 7 || 7;
  end.setDate(end.getDate() - offset);
  const start = new Date(end);
  start.setDate(end.getDate() - 6);
  return `${mmdd(start)}-${mmdd(end)}`;
}

export function validateFineBIWeekLabel(value: string): string {
  return WEEK_LABEL_PATTERN.test(value.trim()) ? "" : "周标签格式应为 MMDD-MMDD，例如 0723-0729";
}
