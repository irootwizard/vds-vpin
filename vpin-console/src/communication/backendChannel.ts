import { backendApiBase, backendHealthUrl } from "@/communication/endpoints";
import {
  DEFAULT_HEALTH_TIMEOUT_MS,
  fetchJson,
  fetchWithDevFallback,
  postJson,
  PROVE_POST_TIMEOUT_MS,
} from "@/communication/httpClient";
import type { LinkStatus } from "@/communication/types";

export type { LinkStatus };

export interface BackendHealth {
  status?: string;
  repo_root?: string;
}

export interface BackendModel {
  id: string;
  name: string;
  framework: string;
  task: string;
  accuracy: number;
  input_shape: string;
  updated?: string | null;
  network?: string | null;
  deployable?: boolean | null;
  message?: string | null;
}

function apiPath(path: string): { primary: string; fallback: string } {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  return {
    primary: `${backendApiBase()}${normalized}`,
    fallback: `/api/v1${normalized}`,
  };
}

export async function pingBackend(): Promise<{ ok: boolean; body?: BackendHealth }> {
  try {
    const res = await fetchWithDevFallback(
      backendHealthUrl(),
      "/api/v1/health",
      {},
      DEFAULT_HEALTH_TIMEOUT_MS,
    );
    if (!res.ok) return { ok: false };
    return { ok: true, body: (await res.json()) as BackendHealth };
  } catch {
    return { ok: false };
  }
}

export async function fetchBackendModels(): Promise<BackendModel[]> {
  const { primary, fallback } = apiPath("/models");
  const data = await fetchJson<BackendModel[]>(primary, fallback);
  return Array.isArray(data) ? data : [];
}

export async function fetchAheModelIdsFromBackend(): Promise<Set<string>> {
  const { primary, fallback } = apiPath("/models?capability=ahe");
  const body = await fetchJson<{ models?: { id: string }[] }>(primary, fallback);
  return new Set((body?.models ?? []).map((m) => m.id));
}

export async function fetchBackendJson<T>(path: string): Promise<T | null> {
  const { primary, fallback } = apiPath(path);
  return fetchJson<T>(primary, fallback);
}

export async function postBackendJson<T>(
  path: string,
  body: unknown,
  timeoutMs = PROVE_POST_TIMEOUT_MS,
): Promise<T | null> {
  const { primary, fallback } = apiPath(path);
  return postJson<T>(primary, fallback, body, timeoutMs);
}

export { backendApiBase, backendHealthUrl };
