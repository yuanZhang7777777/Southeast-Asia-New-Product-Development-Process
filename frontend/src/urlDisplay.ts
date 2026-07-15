export function compactUrlLabel(value: string) {
  try {
    return new URL(value.trim()).hostname.replace(/^www\./, "") || "打开链接";
  } catch {
    return "打开链接";
  }
}
