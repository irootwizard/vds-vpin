import {
  ensureLocalAheServer,
  aheWsUrlForEngine,
  isTauriRuntime,
} from "@/communication";
import {
  DEFAULT_NETWORK_A_ENGINE,
  networkAEnginePort,
  type NetworkARustEngine,
} from "@/config/networkAEngine";

export type InferEngine = NetworkARustEngine;

export { DEFAULT_NETWORK_A_ENGINE as DEFAULT_RUST_ENGINE };
export type { NetworkARustEngine };

export const isTauri = isTauriRuntime;

export function rustWsUrl(engine: NetworkARustEngine = DEFAULT_NETWORK_A_ENGINE): string {
  return aheWsUrlForEngine(engine);
}

export async function ensureRuntimeArtifacts(): Promise<Record<string, unknown>> {
  if (!isTauriRuntime()) {
    return { skipped: true, reason: "browser" };
  }
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke("ensure_runtime_artifacts") as Promise<Record<string, unknown>>;
}

export async function ensureAheServer(
  port = networkAEnginePort(DEFAULT_NETWORK_A_ENGINE),
): Promise<{
  started: boolean;
  port: number;
  status: string;
  host?: string;
  skipLocal?: boolean;
}> {
  return ensureLocalAheServer(port);
}

export async function ensureAheServerForEngine(
  engine: NetworkARustEngine = DEFAULT_NETWORK_A_ENGINE,
): Promise<{ started: boolean; port: number; status: string; host?: string; skipLocal?: boolean }> {
  return ensureLocalAheServer(networkAEnginePort(engine));
}

export async function rustPreprocessMnist(mnistIndex: number): Promise<Record<string, unknown>> {
  if (!isTauriRuntime()) {
    throw new Error("Rust 预处理需在 Tauri 桌面端运行");
  }
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke("ahe_preprocess_rust", { mnistIndex }) as Promise<Record<string, unknown>>;
}

export async function rustPreprocessUpload(path: string): Promise<Record<string, unknown>> {
  if (!isTauriRuntime()) {
    throw new Error("Rust 预处理需在 Tauri 桌面端运行");
  }
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke("preprocess_upload_file_rust", { path }) as Promise<Record<string, unknown>>;
}

export async function rustPreprocessBatch(
  start: number,
  count: number,
): Promise<Record<string, unknown>> {
  if (!isTauriRuntime()) {
    throw new Error("Rust 预处理需在 Tauri 桌面端运行");
  }
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke("ahe_preprocess_batch_rust", { start, count }) as Promise<
    Record<string, unknown>
  >;
}

export async function runRustAheInfer(opts: {
  modelId: string;
  mnistIndex?: number;
  inferEngine?: NetworkARustEngine;
  backendWs?: string;
}): Promise<Record<string, unknown>> {
  if (!isTauriRuntime()) {
    throw new Error("Rust AHE 推理需在 Tauri 桌面端运行");
  }
  const engine = opts.inferEngine ?? DEFAULT_NETWORK_A_ENGINE;
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke("run_ahe_inference", {
    inferEngine: engine,
    mnistIndex: opts.mnistIndex ?? 0,
    uploadId: null,
    imagePath: null,
    backendWs: opts.backendWs ?? aheWsUrlForEngine(engine),
    modelId: opts.modelId,
  }) as Promise<Record<string, unknown>>;
}

export async function runRustAheBatch(opts: {
  modelId: string;
  mnistStart: number;
  mnistEnd: number;
  concurrency?: number;
  inferEngine?: NetworkARustEngine;
  backendWs?: string;
}): Promise<Record<string, unknown>> {
  if (!isTauriRuntime()) {
    throw new Error("Rust AHE 批量推理需在 Tauri 桌面端运行");
  }
  const engine = opts.inferEngine ?? DEFAULT_NETWORK_A_ENGINE;
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke("run_ahe_batch_inference", {
    inferEngine: engine,
    modelId: opts.modelId,
    jobs: null,
    mnistStart: opts.mnistStart,
    mnistEnd: opts.mnistEnd,
    concurrency: opts.concurrency ?? 4,
    traceMode: "focus",
    backendWs: opts.backendWs ?? aheWsUrlForEngine(engine),
  }) as Promise<Record<string, unknown>>;
}

type ProgressHandler = (payload: Record<string, unknown>) => void;

let globalUnlisten: (() => void) | null = null;
const handlers = new Set<ProgressHandler>();
let subscriberCount = 0;

async function ensureGlobalListener(): Promise<void> {
  if (globalUnlisten) return;
  const { listen } = await import("@tauri-apps/api/event");
  globalUnlisten = await listen<Record<string, unknown>>("ahe-progress", (ev) => {
    for (const h of handlers) {
      try {
        h(ev.payload);
      } catch {
        /* UI handler must not throw */
      }
    }
  });
}

export async function subscribeAheProgress(handler: ProgressHandler): Promise<() => void> {
  await ensureGlobalListener();
  subscriberCount += 1;
  handlers.add(handler);
  return () => {
    handlers.delete(handler);
    subscriberCount -= 1;
    if (subscriberCount <= 0 && globalUnlisten) {
      globalUnlisten();
      globalUnlisten = null;
      subscriberCount = 0;
    }
  };
}
