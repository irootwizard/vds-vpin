/** Network A 密态 CNN：Tauri 默认 Rust；浏览器仅 timing-demo Mock */

import { aheWsUrlForEngine } from "@/communication/endpoints";

export type NetworkARustEngine = "rust-ark" | "rust-ec";

export const DEFAULT_NETWORK_A_ENGINE: NetworkARustEngine = "rust-ark";

export const NETWORK_A_RUST_ENGINES = [
  { id: "rust-ark" as const, label: "Arkworks", port: 8001, crypto: "ark" },
  { id: "rust-ec" as const, label: "EC 曲线", port: 8002, crypto: "ec" },
];

const STORAGE_KEY = "vpin-network-a-engine";

export function networkAEnginePort(engine: NetworkARustEngine): number {
  return engine === "rust-ec" ? 8002 : 8001;
}

export function networkAEngineLabel(engine: NetworkARustEngine): string {
  return NETWORK_A_RUST_ENGINES.find((e) => e.id === engine)?.label ?? engine;
}

export function networkAEngineWsUrl(engine: NetworkARustEngine): string {
  return aheWsUrlForEngine(engine);
}

export function loadSavedNetworkAEngine(): NetworkARustEngine {
  if (typeof localStorage === "undefined") return DEFAULT_NETWORK_A_ENGINE;
  const saved = localStorage.getItem(STORAGE_KEY);
  return saved === "rust-ec" ? "rust-ec" : "rust-ark";
}

export function saveNetworkAEngine(engine: NetworkARustEngine): void {
  if (typeof localStorage !== "undefined") {
    localStorage.setItem(STORAGE_KEY, engine);
  }
}

/** 浏览器 dev：Network A 走演示计时，非 Rust */
export function networkAExecutionMode(isDesktop: boolean): "rust" | "timing-demo" {
  return isDesktop ? "rust" : "timing-demo";
}
