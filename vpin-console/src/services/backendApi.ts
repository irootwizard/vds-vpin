/** @deprecated 请改用 `@/communication/backendChannel` 与 `@/communication/aheChannel` */
export {
  pingBackend,
  fetchBackendModels,
  fetchBackendJson,
  postBackendJson,
  type BackendHealth,
  type BackendModel,
  type LinkStatus,
} from "@/communication/backendChannel";

export {
  pingAheServerPort,
  pingAheServerForEngine,
} from "@/communication/aheChannel";

import { networkAEnginePort } from "@/config/networkAEngine";

/** 默认 Ark 引擎端口探活 */
export async function pingAheServer(): Promise<{
  ok: boolean;
  runtime?: string;
  host?: string;
  port?: number;
}> {
  return pingAheServerPort(networkAEnginePort("rust-ark"));
}

export async function fetchAheModelIds(): Promise<Set<string>> {
  const { fetchAheModelIdsFromBackend } = await import("@/communication/backendChannel");
  return fetchAheModelIdsFromBackend();
}
