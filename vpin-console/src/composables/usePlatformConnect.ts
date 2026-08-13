import { computed, ref } from "vue";
import { getBridge } from "@/bridge/client";
import {
  aheApiBase,
  backendApiBase,
  bootstrapCommunication,
  loadCommunicationProfile,
  resetCommunicationProfileCache,
  type LinkStatus,
} from "@/communication";
import type { StartupOptimizerResult } from "@/bridge/types";

const sessionId = ref(`sess-${Date.now().toString(36)}`);
const backendStatus = ref<LinkStatus>("checking");
const backendStandalone = ref(false);
const aheStatus = ref<LinkStatus>("checking");
const bridgeReady = ref(false);
const bootstrapResult = ref<StartupOptimizerResult | null>(null);
let initPromise: Promise<void> | null = null;

export async function initPlatformSession(force = false): Promise<void> {
  if (initPromise && !force) return initPromise;

  initPromise = (async () => {
    if (force) resetCommunicationProfileCache();
    bridgeReady.value = false;
    backendStatus.value = "checking";
    aheStatus.value = "checking";

    await loadCommunicationProfile(force);
    const bridge = getBridge();
    const session = await bootstrapCommunication(bridge);

    bootstrapResult.value = session.bootstrapResult;
    backendStatus.value = session.backendStatus;
    backendStandalone.value = session.backendStandalone;
    aheStatus.value = session.aheStatus;
    bridgeReady.value = true;
  })();

  return initPromise;
}

export function usePlatformConnect() {
  const backendUrl = computed(() =>
    backendStandalone.value ? "便携内置（无需 :8000）" : backendApiBase(),
  );
  return {
    sessionId,
    backendStatus,
    backendStandalone,
    aheStatus,
    bridgeReady,
    bootstrapResult,
    backendUrl,
    aheUrl: aheApiBase(),
    reconnect: () => initPlatformSession(true),
  };
}
