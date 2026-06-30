const API_BASE = import.meta.env.VITE_VPIN_API || "/api/v1";

/** @typedef {"python"|"rust-ark"|"rust-ec"} InferEngine */
/** @typedef {"python"|"rust"} PreprocessLane */

export const INFER_ENGINES = [
  {
    value: "python",
    label: "Python 标准 · vpin-backend :8000",
    description: "vpin-client + vpin-backend（Python 同态栈，支持 MNIST / 上传图）",
    ws: "ws://127.0.0.1:8000/api/v1/session/ws",
    serverPort: 8000,
    preprocessLane: "python",
    requiresMnist: false,
  },
  {
    value: "rust-ark",
    label: "Rust 加速 · Arkworks",
    description: "ahe-cli + ahe-server (ark) :8001 · MNIST 0–9999 / 上传图",
    ws: "ws://127.0.0.1:8001/api/v1/session/ws",
    serverPort: 8001,
    preprocessLane: "rust",
    requiresMnist: false,
  },
  {
    value: "rust-ec",
    label: "Rust 加速 · EC 曲线",
    description: "ahe-cli + ahe-server (ec) :8002 · MNIST 0–9999 / 上传图",
    ws: "ws://127.0.0.1:8002/api/v1/session/ws",
    serverPort: 8002,
    preprocessLane: "rust",
    requiresMnist: false,
  },
];

export const DEFAULT_INFER_ENGINE = "python";
export const DEFAULT_BACKEND_WS = INFER_ENGINES[0].ws;

const ENGINE_STORAGE_KEY = "vpin-ahe-infer-engine";

export function loadSavedInferEngine() {
  if (typeof localStorage === "undefined") return DEFAULT_INFER_ENGINE;
  const saved = localStorage.getItem(ENGINE_STORAGE_KEY);
  return INFER_ENGINES.some((e) => e.value === saved) ? saved : DEFAULT_INFER_ENGINE;
}

export function saveInferEngine(engine) {
  if (typeof localStorage !== "undefined") {
    localStorage.setItem(ENGINE_STORAGE_KEY, engine);
  }
}

export function getEnginePreset(engine) {
  return INFER_ENGINES.find((e) => e.value === engine) || INFER_ENGINES[0];
}

/** @param {InferEngine|string} engine */
export function getPreprocessLane(engine) {
  return getEnginePreset(engine).preprocessLane;
}

/** @returns {{ stack: 'python'|'rust', rustBackend: 'ark'|'ec' }} */
export function stackFromInferEngine(engine) {
  if (engine === "python") return { stack: "python", rustBackend: "ark" };
  if (engine === "rust-ec") return { stack: "rust", rustBackend: "ec" };
  return { stack: "rust", rustBackend: "ark" };
}

/** @param {'python'|'rust'} stack @param {'ark'|'ec'} rustBackend */
export function inferEngineFromStack(stack, rustBackend = "ark") {
  if (stack === "python") return "python";
  return rustBackend === "ec" ? "rust-ec" : "rust-ark";
}

export function isRustEngine(engine) {
  return getPreprocessLane(engine) === "rust";
}

export function isTauri() {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

/** AHE inference requires the Tauri desktop client (local private key). */
export function aheInferRequiresTauri() {
  return !isTauri();
}

/**
 * Python 轨预处理 — 本地 vpin_client（Tauri 桌面端，明文不出机）
 */
export async function pythonPreprocessOfficial(mnistIndex) {
  if (!isTauri()) {
    throw new Error("Python 预处理需在 Tauri 桌面端运行（本地 vpin_client）");
  }
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke("ahe_preprocess", { mnistIndex });
}

export async function pythonPreprocessBatch(start = 0, count = 10) {
  if (!isTauri()) {
    throw new Error("Python 批量预处理需在 Tauri 桌面端运行");
  }
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke("ahe_preprocess_batch", { start, count });
}

export async function pythonPreprocessUpload(path) {
  if (!isTauri()) {
    throw new Error("Python 上传预处理需在 Tauri 桌面端运行");
  }
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke("preprocess_upload_file", { path });
}

/** Upload image via bytes (avoids File.path issues in Tauri v2 WebView2). */
export async function preprocessUploadBytes(data, filename) {
  if (!isTauri()) throw new Error("Python 上传预处理需在 Tauri 桌面端运行");
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke("preprocess_upload_bytes", { data: Array.from(data), filename });
}

/** Upload image via bytes — Rust ahe-cli lane. */
export async function rustPreprocessUploadBytes(data, filename) {
  if (!isTauri()) throw new Error("Rust 上传预处理需在 Tauri 桌面端运行");
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke("preprocess_upload_bytes_rust", { data: Array.from(data), filename });
}

/** Load test images from model_training/test_images/ as gallery items. */
export async function loadTestGallery() {
  if (!isTauri()) throw new Error("需要 Tauri 桌面端");
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke("load_test_gallery");
}

/**
 * Rust 轨预处理 — 本地 ahe-cli（mnist_official / preprocess_upload）
 */
export async function rustPreprocessOfficial(mnistIndex) {
  if (!isTauri()) {
    throw new Error("Rust 预处理需在 Tauri 桌面端运行（本地 ahe-cli）");
  }
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke("ahe_preprocess_rust", { mnistIndex });
}

export async function rustPreprocessUpload(path) {
  if (!isTauri()) {
    throw new Error("Rust 上传预处理需在 Tauri 桌面端运行");
  }
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke("preprocess_upload_file_rust", { path });
}

/** Rust 轨批量预处理 — 官方 MNIST test 任意 start/count（0–9999） */
export async function rustPreprocessBatch(start = 0, count = 10) {
  if (!isTauri()) {
    throw new Error("Rust 批量预处理需在 Tauri 桌面端运行");
  }
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke("ahe_preprocess_batch_rust", { start, count });
}

/** @deprecated use pythonPreprocessOfficial */
export const ahePreprocessOfficial = pythonPreprocessOfficial;
/** @deprecated use pythonPreprocessBatch */
export const ahePreprocessBatch = pythonPreprocessBatch;
/** @deprecated use pythonPreprocessOfficial */
export const ahePreprocess = pythonPreprocessOfficial;

/** Models with AHE npy weights (catalog only — no inference on server). */
export async function fetchAheModels() {
  const res = await fetch(`${API_BASE}/models?capability=ahe`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `list ahe models failed (${res.status})`);
  }
  const body = await res.json();
  if (Array.isArray(body)) {
    return { models: body };
  }
  return body;
}

/**
 * Run AHE inference via Tauri (active driver). Progress is passive: subscribe via
 * `subscribeAheProgress()` or `useAheInferTimeline()` — do NOT block in callbacks.
 */
export async function aheInfer({
  mnistIndex,
  uploadId,
  imagePath,
  modelId,
  inferEngine = DEFAULT_INFER_ENGINE,
  backendWs,
}) {
  if (!isTauri()) {
    throw new Error(
      "AHE 推理需在 Tauri 桌面端运行（私钥不能离开本机）。请使用 npm run tauri dev 启动。"
    );
  }
  const { invoke } = await import("@tauri-apps/api/core");
  const preset = getEnginePreset(inferEngine);
  return invoke("run_ahe_inference", {
    inferEngine: preset.value,
    mnistIndex: mnistIndex ?? null,
    uploadId: uploadId ?? null,
    imagePath: imagePath ?? null,
    backendWs: backendWs ?? preset.ws,
    modelId,
  });
}

export { subscribeAheProgress } from "../composables/useAheInferTimeline.js";

/**
 * Stable job id aligned with Python `job_id_for`.
 * @param {{ mnist_index?: number|null, upload_id?: string|null, image_path?: string|null }} job
 */
export function jobIdFor(job) {
  if (job.mnist_index != null) return `mnist-${job.mnist_index}`;
  if (job.upload_id) return `upload-${String(job.upload_id).slice(0, 12)}`;
  if (job.image_path) {
    const parts = String(job.image_path).split(/[/\\]/);
    return `image-${parts[parts.length - 1]}`;
  }
  return `job-${Date.now()}`;
}

/**
 * Build batch jobs from MNIST index range [start, end] inclusive.
 * @param {number} start
 * @param {number} end
 */
export function jobsFromRange(start, end) {
  const jobs = [];
  for (let i = start; i <= end; i += 1) {
    jobs.push({ mnist_index: i, upload_id: null, image_path: null });
  }
  return jobs;
}

/** @param {number} start @param {number} end inclusive */
export function jobKeysForRange(start, end) {
  const keys = [];
  for (let i = start; i <= end; i += 1) {
    keys.push(`mnist-${i}`);
  }
  return keys;
}

/**
 * Build batch jobs from preprocess gallery samples.
 * @param {object[]} samples
 * @param {'python'|'rust'} lane
 * @param {{ python?: { lastUploadPath?: string|null }, rust?: { lastUploadPath?: string|null } }} lanes
 */
export function jobsFromSelectedSamples(samples, lane, lanes = {}) {
  const laneState = lanes[lane] || {};
  return samples.map((sample) => {
    if (sample.source === "upload") {
      const path = laneState.lastUploadPath || sample.local_path || null;
      if (path) {
        return { mnist_index: null, upload_id: null, image_path: path };
      }
      if (sample.upload_id) {
        return { mnist_index: null, upload_id: sample.upload_id, image_path: null };
      }
      throw new Error(`上传样本缺少路径或 upload_id: ${sample.filename || "?"}`);
    }
    return {
      mnist_index: sample.mnist_index ?? 0,
      upload_id: null,
      image_path: null,
    };
  });
}

/**
 * Run batch AHE inference via Tauri. Progress via subscribeAheProgress / useAheBatchTimeline.
 */
export async function aheBatchInfer({
  jobs,
  mnistStart,
  mnistEnd,
  modelId,
  inferEngine = DEFAULT_INFER_ENGINE,
  concurrency = 2,
  traceMode = "focus",
  backendWs,
}) {
  if (!isTauri()) {
    throw new Error("AHE 批量推理需在 Tauri 桌面端运行");
  }
  const hasRange = mnistStart != null && mnistEnd != null;
  if (!hasRange && !jobs?.length) {
    throw new Error("批量任务列表为空");
  }
  const { invoke } = await import("@tauri-apps/api/core");
  const preset = getEnginePreset(inferEngine);
  return invoke("run_ahe_batch_inference", {
    inferEngine: preset.value,
    modelId,
    jobs: hasRange ? null : jobs,
    mnistStart: hasRange ? mnistStart : null,
    mnistEnd: hasRange ? mnistEnd : null,
    concurrency,
    traceMode,
    backendWs: backendWs ?? preset.ws,
  });
}
