/**
 * 各模块真实能力 vs 演示回退（不展示 Mock 标签，供内部路由决策）
 */
import { hasDeepSeekKey } from "@/demo/deepseekClient";
import { isTauri } from "@/services/aheClient";

export type CapabilitySource = "live" | "demo" | "none";

export interface RuntimeCapabilities {
  cnnInference: CapabilitySource;
  llmDialogue: CapabilitySource;
  llmComputeCommitment: CapabilitySource;
  modelRegistry: CapabilitySource;
  datasetCatalog: CapabilitySource;
  securityMetrics: CapabilitySource;
  custody: CapabilitySource;
  runStorage: CapabilitySource;
}

export function getRuntimeCapabilities(): RuntimeCapabilities {
  const desktop = isTauri();
  return {
    cnnInference: desktop ? "live" : "demo",
    llmDialogue: hasDeepSeekKey() ? "live" : "demo",
    llmComputeCommitment: "demo",
    modelRegistry: "live",
    datasetCatalog: "live",
    securityMetrics: "live",
    custody: "demo",
    runStorage: "demo",
  };
}
