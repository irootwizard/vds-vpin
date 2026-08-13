import { mockBridge } from "./mock/MockBridge";

/** 统一 Bridge：编排、托管 Shim、运行态均在 vpin-console 内实现 */
export function getBridge() {
  return mockBridge;
}

export type { BridgeClient } from "./mock/MockBridge";
