import type { EnrichedModel, InferencePlan } from "@/config/modelCatalog";
import { resolveInferencePlan } from "@/config/modelCatalog";
import { isStrictNetworkAModel } from "@/config/networkAProof";

/** @deprecated 使用 isStrictNetworkAModel + resolveInferencePlan */
export function isNetworkAAheModel(modelId: string, aheCapableIds: Set<string>): boolean {
  return isStrictNetworkAModel(modelId) && aheCapableIds.has(modelId);
}

export function usesRustAheInference(
  model: EnrichedModel | null,
  modelId: string,
  aheCapableIds: Set<string>,
  isDesktop: boolean,
  datasetId?: string,
): boolean {
  return (
    resolveInferencePlan(model, modelId, aheCapableIds, isDesktop, datasetId).mode === "rust_ahe"
  );
}

export type { InferencePlan };
