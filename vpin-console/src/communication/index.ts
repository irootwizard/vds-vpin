export type {
  AheBootResult,
  AheEndpointConfig,
  AheHealthResult,
  CommunicationProfile,
  HttpEndpointConfig,
  LinkStatus,
} from "@/communication/types";

export {
  getCommunicationProfile,
  isTauriRuntime,
  loadCommunicationProfile,
  resetCommunicationProfileCache,
} from "@/communication/runtimeConfig";

export {
  DEFAULT_HEALTH_TIMEOUT_MS,
  DEFAULT_JSON_TIMEOUT_MS,
  PROVE_POST_TIMEOUT_MS,
  fetchJson,
  fetchWithDevFallback,
  fetchWithTimeout,
  postJson,
} from "@/communication/httpClient";

export {
  aheApiBase,
  aheDisplayLabel,
  aheHealthUrl,
  aheHost,
  aheWsUrlForEngine,
  backendApiBase,
  backendHealthUrl,
  ovdsApiBase,
  shouldSkipLocalAheServer,
} from "@/communication/endpoints";

export {
  ensureLocalAheServer,
  pingAheServerForEngine,
  pingAheServerPort,
  waitForAheServer,
} from "@/communication/aheChannel";

export {
  fetchAheModelIdsFromBackend,
  fetchBackendJson,
  fetchBackendModels,
  pingBackend,
  postBackendJson,
  type BackendHealth,
  type BackendModel,
} from "@/communication/backendChannel";

export { bootstrapCommunication } from "@/communication/connectionSession";
