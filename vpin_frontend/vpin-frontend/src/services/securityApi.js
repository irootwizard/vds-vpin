import {
  mockTransport,
  mockInferenceMetrics,
  mockComputationProof,
} from "../mocks/securityMetrics.js";

const API_BASE = import.meta.env.VITE_VPIN_API || "/api/v1";

async function getJson(path) {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`${path} ${res.status}`);
  return res.json();
}

/**
 * @template T
 * @param {() => Promise<T>} fn
 * @param {T} fallback
 * @returns {Promise<{ data: T, mock: boolean }>}
 */
async function withFallback(fn, fallback) {
  try {
    const data = await fn();
    return { data, mock: false };
  } catch {
    return { data: fallback, mock: true };
  }
}

export function fetchSecurityTransport() {
  return withFallback(() => getJson("/security/transport"), mockTransport);
}

export function fetchInferenceMetrics() {
  return withFallback(() => getJson("/security/inference-metrics"), mockInferenceMetrics);
}

export function fetchComputationProof() {
  return withFallback(() => getJson("/security/computation-proof"), mockComputationProof);
}
