import type { DatasetEntry } from "@/services/datasetsApi";

const STORAGE_KEY = "vpin-console:hidden-dataset-ids";

function readHidden(): Set<string> {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return new Set();
    const ids = JSON.parse(raw) as string[];
    return new Set(Array.isArray(ids) ? ids : []);
  } catch {
    return new Set();
  }
}

function writeHidden(ids: Set<string>): void {
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify([...ids]));
}

export function getHiddenDatasetIds(): Set<string> {
  return readHidden();
}

/** 仅从列表隐藏，不删除任何本地数据文件 */
export function hideDatasetFromUi(id: string): void {
  const next = readHidden();
  next.add(id);
  writeHidden(next);
}

export function isDatasetHidden(id: string): boolean {
  return readHidden().has(id);
}

/** 不可从 UI 移除的内置项 */
export function isProtectedDataset(id: string): boolean {
  return id === "user-upload-image";
}

export function filterVisibleDatasets(entries: DatasetEntry[]): DatasetEntry[] {
  const hidden = readHidden();
  return entries.filter((d) => !hidden.has(d.id) && d.status !== "placeholder");
}

export function filterVisibleCatalog(catalog: {
  local: DatasetEntry[];
  remote: DatasetEntry[];
}): { local: DatasetEntry[]; remote: DatasetEntry[] } {
  return {
    local: filterVisibleDatasets(catalog.local),
    remote: [],
  };
}
