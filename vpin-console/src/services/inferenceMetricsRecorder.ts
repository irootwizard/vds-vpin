import type { RunRecord } from "@/bridge/types";
import { postBackendJson } from "@/services/backendApi";
import { estimateHomomorphicOps, imageCountFromRun } from "@/services/homomorphicUsage";
import type { InferenceMetrics } from "@/services/securityApi";
import { fetchInferenceMetrics } from "@/services/securityApi";

const metricsListeners = new Set<(m: InferenceMetrics | null) => void>();

export function subscribeInferenceMetrics(fn: (m: InferenceMetrics | null) => void): () => void {
  metricsListeners.add(fn);
  return () => metricsListeners.delete(fn);
}

function notifyMetrics(m: InferenceMetrics | null): void {
  for (const fn of metricsListeners) fn(m);
}

export async function refreshInferenceMetrics(): Promise<InferenceMetrics | null> {
  const m = await fetchInferenceMetrics();
  notifyMetrics(m);
  return m;
}

export async function recordRunInferenceUsage(
  run: RunRecord,
  overrides?: { pt_add?: number; pt_mult?: number },
): Promise<void> {
  const images = imageCountFromRun(
    run.config.batch_size,
    run.config.sample_index ?? run.config.mnist_start ?? run.config.mnist_index,
    run.config.mnist_end,
  );
  const est = estimateHomomorphicOps(run.config.model_id, images);
  const pt_add = overrides?.pt_add ?? est.pt_add;
  const pt_mult = overrides?.pt_mult ?? est.pt_mult;

  await postBackendJson("/security/inference-metrics/record", { pt_add, pt_mult });
  await refreshInferenceMetrics();
}
