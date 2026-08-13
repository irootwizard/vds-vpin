import { getCommunicationProfile } from "@/communication/runtimeConfig";
import type { NetworkARustEngine } from "@/config/networkAEngine";
import { networkAEnginePort } from "@/config/networkAEngine";

export function backendApiBase(): string {
  return getCommunicationProfile().backend.httpBase;
}

export function backendHealthUrl(): string {
  return `${backendApiBase()}/health`;
}

export function ovdsApiBase(): string | undefined {
  return getCommunicationProfile().ovds?.httpBase;
}

export function aheApiBase(): string {
  return getCommunicationProfile().ahe.httpBase;
}

export function aheHealthUrl(): string {
  return `${aheApiBase()}/health`;
}

export function aheHost(): string {
  return getCommunicationProfile().ahe.host;
}

export function shouldSkipLocalAheServer(): boolean {
  return getCommunicationProfile().ahe.skipLocalServer;
}

/** 按引擎端口（8001/8002）构造 WS；host 来自运行时配置 */
export function aheWsUrlForEngine(engine: NetworkARustEngine): string {
  const host = aheHost();
  const port = networkAEnginePort(engine);
  return `ws://${host}:${port}/api/v1/session/ws`;
}

export function aheDisplayLabel(port: number): string {
  const host = aheHost();
  return `${host}:${port}`;
}
