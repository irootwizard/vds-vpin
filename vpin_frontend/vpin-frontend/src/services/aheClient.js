const API_BASE = import.meta.env.VITE_VPIN_API || "/api/v1";

export const DEFAULT_BACKEND_WS = "ws://127.0.0.1:8000/api/v1/session/ws";

export function isTauri() {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

/** AHE inference requires the Tauri desktop client (local private key). */
export function aheInferRequiresTauri() {
  return !isTauri();
}

/**
 * Official MNIST preview — always via backend REST (single long-lived Python process).
 * Avoids Tauri spawning N Python subprocesses (each ~30s torch cold start).
 */
export async function ahePreprocessOfficial(mnistIndex) {
  const res = await fetch(`${API_BASE}/data/official/test/${mnistIndex}`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `official preprocess failed (${res.status})`);
  }
  return res.json();
}

export async function ahePreprocessBatch(start = 0, count = 10) {
  const res = await fetch(`${API_BASE}/data/official/batch?start=${start}&count=${count}`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `batch preprocess failed (${res.status})`);
  }
  return res.json();
}

/** @deprecated use ahePreprocessOfficial */
export const ahePreprocess = ahePreprocessOfficial;

/** Models with AHE npy weights (catalog only — no inference on server). */
export async function fetchAheModels() {
  const res = await fetch(`${API_BASE}/models?capability=ahe`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `list ahe models failed (${res.status})`);
  }
  const body = await res.json();
  if (Array.isArray(body)) {
    return {
      models: body.filter((m) => m.id === "cnn-mnist-trained" || m.id === "cnn-mnist" || m.network === "A" || m.network === "B"),
    };
  }
  return body;
}

/**
 * Run AHE inference via Tauri → vpin_client.pipeline (local private key).
 * Browser mode is not supported — use the desktop app.
 */
export async function aheInfer({
  mnistIndex,
  uploadId,
  imagePath,
  modelId,
  backendWs = DEFAULT_BACKEND_WS,
}) {
  if (!isTauri()) {
    throw new Error(
      "AHE 推理需在 Tauri 桌面端运行（私钥不能离开本机）。请使用 npm run tauri dev 启动。"
    );
  }
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke("run_ahe_inference", {
    mnistIndex: mnistIndex ?? null,
    uploadId: uploadId ?? null,
    imagePath: imagePath ?? null,
    backendWs,
    modelId,
  });
}
