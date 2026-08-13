import bundledRegistry from "../../../config/models-registry.json";
import { enrichModel, type EnrichedModel } from "@/config/modelCatalog";
import { isTauri } from "@/services/aheClient";
import {
  fetchAheModelIds,
  fetchBackendModels,
  type BackendModel,
} from "@/services/backendApi";

export type { EnrichedModel };

interface ModelsRegistryDoc {
  models?: BackendModel[];
}

function bundledAheCapableIds(models: BackendModel[]): Set<string> {
  return new Set(
    models
      .filter((m) => m.deployable !== false && /cnn-mnist/i.test(m.id))
      .map((m) => m.id),
  );
}

/** 后端 :8000 不可用时回退到内置 models-registry（发布包必需） */
export async function fetchAheCapableIds(): Promise<Set<string>> {
  const backendIds = await fetchAheModelIds();
  if (backendIds.size > 0) return backendIds;
  const bundled = await loadBundledModels();
  return bundledAheCapableIds(bundled);
}

async function loadBundledModels(): Promise<BackendModel[]> {
  if (isTauri()) {
    try {
      const { invoke } = await import("@tauri-apps/api/core");
      const raw = await invoke<ModelsRegistryDoc>("read_models_registry");
      if (raw?.models?.length) return raw.models;
    } catch {
      /* fall through */
    }
  }
  const doc = bundledRegistry as ModelsRegistryDoc;
  return doc.models ?? [];
}

export async function fetchEnrichedModelCatalog(): Promise<{
  models: EnrichedModel[];
  aheCapableIds: Set<string>;
}> {
  const [backendModels, backendAheIds] = await Promise.all([
    fetchBackendModels(),
    fetchAheCapableIds(),
  ]);
  if (backendModels.length > 0) {
    return {
      models: backendModels.map(enrichModel),
      aheCapableIds: backendAheIds,
    };
  }
  const bundled = await loadBundledModels();
  return {
    models: bundled.map(enrichModel),
    aheCapableIds: bundledAheCapableIds(bundled),
  };
}

export function findEnrichedModel(
  models: EnrichedModel[],
  modelId: string,
): EnrichedModel | null {
  return models.find((m) => m.id === modelId) ?? null;
}

export async function fetchEnrichedModel(modelId: string): Promise<EnrichedModel | null> {
  const { models } = await fetchEnrichedModelCatalog();
  return findEnrichedModel(models, modelId);
}

