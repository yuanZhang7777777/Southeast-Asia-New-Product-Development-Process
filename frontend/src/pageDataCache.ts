type CacheEntry<T> = { value: T; savedAt: number };

const pageDataCache = new Map<string, CacheEntry<unknown>>();

export const PAGE_DATA_CACHE_TTL_MS = 5 * 60 * 1000;

export function cachedValue<T>(key: string, now = Date.now(), ttlMs = PAGE_DATA_CACHE_TTL_MS): T | undefined {
  const entry = pageDataCache.get(key);
  if (!entry || now - entry.savedAt > ttlMs) return undefined;
  return entry.value as T;
}

export function setCachedValue<T>(key: string, value: T, now = Date.now()) {
  pageDataCache.set(key, { value, savedAt: now });
}

export function clearPageDataCache() {
  pageDataCache.clear();
}
