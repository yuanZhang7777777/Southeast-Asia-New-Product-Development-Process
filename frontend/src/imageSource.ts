// 商品图统一取源：私有 OSS 桶直链改走后端公开只读代理 /media/oss-image。
// 认领/调研证据图有独立的 /claims/evidence-images/proxy（带 token），不走本函数。
const FALLBACK_API_BASE = "/api";

function apiBase(): string {
  // node --test 下无 window 也无 import.meta.env，直接回落默认值；
  // 浏览器构建时 Vite 静态替换 VITE_API_BASE_URL，与 api.ts 的 API_BASE 保持一致。
  if (typeof window === "undefined") return FALLBACK_API_BASE;
  return import.meta.env.VITE_API_BASE_URL || FALLBACK_API_BASE;
}

const OSS_URL_PATTERN = /^https?:\/\/[^/]*\.aliyuncs\.com\//i;

export function productImageSrc(url?: string | null, options?: { thumb?: boolean }): string {
  if (!url) return "";
  if (url.startsWith("/uploaded-sources/")) return `${apiBase()}${url}`;
  if (OSS_URL_PATTERN.test(url)) {
    const thumb = options?.thumb ? "&thumb=true" : "";
    return `${apiBase()}/media/oss-image?src=${encodeURIComponent(url)}${thumb}`;
  }
  return url;
}

// 列表/缩略场景统一走 OSS 400px 缩略图，省 ~90% 传输量；详情大图仍用原图。
export function productThumbSrc(url?: string | null): string {
  return productImageSrc(url, { thumb: true });
}
