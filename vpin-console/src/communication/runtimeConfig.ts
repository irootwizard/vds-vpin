import {
  normalizeCommunicationProfile,
  type CommunicationProfile,
} from "@/communication/types";

let cached: CommunicationProfile | null = null;

function buildDefaultProfile(): CommunicationProfile {
  const backendRaw = import.meta.env.VITE_BACKEND_URL ?? "http://127.0.0.1:8000/api/v1";
  const aheRaw = import.meta.env.VITE_AHE_SERVER_URL ?? "http://127.0.0.1:8001/api/v1";
  const aheBase = aheRaw.replace(/\/$/, "");
  let host = "127.0.0.1";
  let port = 8001;
  try {
    const u = new URL(aheBase);
    host = u.hostname;
    port = Number(u.port || 8001);
  } catch {
    /* keep defaults */
  }
  return {
    backend: { httpBase: backendRaw.replace(/\/$/, "") },
    ahe: {
      host,
      port,
      httpBase: aheBase,
      wsSession: `ws://${host}:${port}/api/v1/session/ws`,
      skipLocalServer: false,
    },
  };
}

export function isTauriRuntime(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

/** 启动时调用一次；Tauri 从 Rust 读 env + config/client-endpoints.json */
export async function loadCommunicationProfile(force = false): Promise<CommunicationProfile> {
  if (cached && !force) return cached;
  if (isTauriRuntime()) {
    try {
      const { invoke } = await import("@tauri-apps/api/core");
      const raw = (await invoke("get_communication_profile")) as Record<string, unknown>;
      cached = normalizeCommunicationProfile(raw);
      return cached;
    } catch {
      /* dev 未编译 tauri 命令时回退 */
    }
  }
  cached = buildDefaultProfile();
  return cached;
}

export function getCommunicationProfile(): CommunicationProfile {
  return cached ?? buildDefaultProfile();
}

export function resetCommunicationProfileCache(): void {
  cached = null;
}
