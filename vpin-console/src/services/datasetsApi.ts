import bundledCatalog from "../../../config/datasets-catalog.json";
import { fetchBackendJson } from "@/services/backendApi";
import { isTauri } from "@/services/aheClient";
import { filterVisibleCatalog } from "@/services/datasetUiStore";

export interface DatasetEntry {
  id: string;
  name: string;
  kind: string;
  format?: string;
  sample_count?: number | null;
  index_range?: [number, number];
  location?: string;
  status?: string;
  previewable?: boolean;
  dynamic?: boolean;
  message?: string;
  source_url?: string;
}

export interface DatasetCatalog {
  local: DatasetEntry[];
  remote: DatasetEntry[];
}

async function loadBundledDatasetCatalog(): Promise<DatasetCatalog | null> {
  if (isTauri()) {
    try {
      const { invoke } = await import("@tauri-apps/api/core");
      const raw = await invoke<DatasetCatalog>("read_datasets_catalog");
      if (raw?.local?.length) return raw;
    } catch {
      /* fall through to static catalog */
    }
  }
  return bundledCatalog as DatasetCatalog;
}

export async function fetchDatasetCatalog(): Promise<DatasetCatalog | null> {
  const raw = await fetchBackendJson<DatasetCatalog>("/datasets/catalog");
  if (raw) return filterVisibleCatalog(raw);
  const bundled = await loadBundledDatasetCatalog();
  if (!bundled) return null;
  return filterVisibleCatalog(bundled);
}
