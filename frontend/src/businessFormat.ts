const decimalFormat = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 });

export function formatBusinessNumber(value: unknown) {
  if (value === null || value === undefined || value === "") return "";
  const number = typeof value === "number" ? value : Number(String(value).replace(/,/g, "").trim());
  return Number.isFinite(number) ? decimalFormat.format(number) : String(value).trim();
}

export function formatBusinessValue(value: unknown, label: string) {
  if (value === null || value === undefined || value === "") return "";
  const text = String(value).trim();
  if (/率|占比/.test(label) && !/汇率/.test(label)) {
    if (text.endsWith("%")) return `${formatBusinessNumber(text.slice(0, -1))}%`;
    const number = Number(text.replace(/,/g, ""));
    if (Number.isFinite(number)) return `${formatBusinessNumber(Math.abs(number) <= 1 ? number * 100 : number)}%`;
  }
  return /价|成本|利润额|单销|月销|销量|数量|运费|费用|重量|金额|备货量|天数|汇率/.test(label)
    ? formatBusinessNumber(value)
    : text;
}
