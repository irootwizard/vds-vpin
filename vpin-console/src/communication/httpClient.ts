/** 统一 HTTP 请求：超时、dev proxy 回退 */

export const DEFAULT_HEALTH_TIMEOUT_MS = 2500;
export const DEFAULT_JSON_TIMEOUT_MS = 30_000;
export const PROVE_POST_TIMEOUT_MS = 600_000;

export async function fetchWithTimeout(
  url: string,
  init: RequestInit = {},
  timeoutMs = DEFAULT_JSON_TIMEOUT_MS,
): Promise<Response> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    return await fetch(url, { ...init, signal: ctrl.signal });
  } finally {
    clearTimeout(timer);
  }
}

export async function fetchWithDevFallback(
  primaryUrl: string,
  fallbackPath: string,
  init: RequestInit = {},
  timeoutMs = DEFAULT_JSON_TIMEOUT_MS,
): Promise<Response> {
  try {
    const res = await fetchWithTimeout(primaryUrl, init, timeoutMs);
    if (res.ok) return res;
  } catch {
    /* try vite proxy */
  }
  if (fallbackPath && fallbackPath !== primaryUrl) {
    return fetchWithTimeout(fallbackPath, init, timeoutMs);
  }
  throw new Error(`request failed: ${primaryUrl}`);
}

export async function fetchJson<T>(
  primaryUrl: string,
  fallbackPath: string,
  timeoutMs = DEFAULT_JSON_TIMEOUT_MS,
): Promise<T | null> {
  try {
    const res = await fetchWithDevFallback(primaryUrl, fallbackPath, {}, timeoutMs);
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

export async function postJson<T>(
  primaryUrl: string,
  fallbackPath: string,
  body: unknown,
  timeoutMs = DEFAULT_JSON_TIMEOUT_MS,
): Promise<T | null> {
  const opts: RequestInit = {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
  try {
    let res = await fetchWithTimeout(primaryUrl, opts, timeoutMs);
    if (!res.ok && fallbackPath !== primaryUrl) {
      res = await fetchWithTimeout(fallbackPath, opts, timeoutMs);
    }
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}
