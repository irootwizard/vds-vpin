import { aheDisplayLabel, aheHost, shouldSkipLocalAheServer } from "@/communication/endpoints";
import {
  DEFAULT_HEALTH_TIMEOUT_MS,
  fetchWithDevFallback,
} from "@/communication/httpClient";
import { isTauriRuntime } from "@/communication/runtimeConfig";
import type { AheBootResult, AheHealthResult } from "@/communication/types";
import type { NetworkARustEngine } from "@/config/networkAEngine";
import { networkAEnginePort } from "@/config/networkAEngine";

export async function pingAheServerPort(port: number): Promise<AheHealthResult> {
  if (!isTauriRuntime()) {
    return { ok: false };
  }
  const { invoke } = await import("@tauri-apps/api/core");
  return (await invoke("ping_ahe_server_health", { port })) as AheHealthResult;
}

export async function pingAheServerForEngine(
  engine: NetworkARustEngine = "rust-ark",
): Promise<AheHealthResult> {
  return pingAheServerPort(networkAEnginePort(engine));
}

export async function ensureLocalAheServer(
  port = networkAEnginePort("rust-ark"),
): Promise<AheBootResult> {
  if (!isTauriRuntime()) {
    return { started: false, port, status: "browser" };
  }
  if (shouldSkipLocalAheServer()) {
    const health = await pingAheServerPort(port);
    if (health.ok) {
      return {
        started: false,
        port: health.port ?? port,
        host: health.host,
        status: "remote_ok",
        skipLocal: true,
      };
    }
    throw new Error(
      `远程 ahe-server ${aheDisplayLabel(port)} 不可达（VPIN_SKIP_LOCAL_AHE=1）`,
    );
  }
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke("ensure_ahe_server", { port }) as Promise<AheBootResult>;
}

export async function waitForAheServer(
  port: number,
  attempts = 6,
  intervalMs = 500,
): Promise<AheHealthResult> {
  for (let i = 0; i < attempts; i++) {
    const health = await pingAheServerPort(port);
    if (health.ok) return health;
    if (i + 1 < attempts) {
      await new Promise((r) => setTimeout(r, intervalMs));
    }
  }
  return { ok: false, port };
}

/** 浏览器 dev 可尝试 HTTP 探活（分包 client 无 Tauri 时备用） */
export async function pingAheServerHttp(port: number): Promise<boolean> {
  const host = aheHost();
  const primary = `http://${host}:${port}/api/v1/health`;
  const fallback = `/api/v1/health`;
  try {
    const res = await fetchWithDevFallback(primary, fallback, {}, DEFAULT_HEALTH_TIMEOUT_MS);
    return res.ok;
  } catch {
    return false;
  }
}
