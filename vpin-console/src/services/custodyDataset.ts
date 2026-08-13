import type { DatasetEntry } from "@/services/datasetsApi";

export function isMnistDataset(id: string): boolean {
  return id === "mnist-test" || id === "mnist-train";
}

export function isCifarDataset(id: string): boolean {
  return id === "cifar10-test" || id === "cifar10-train";
}

export function isPreviewableIndexedDataset(id: string): boolean {
  return isMnistDataset(id) || isCifarDataset(id);
}

export function isUploadDataset(entry: DatasetEntry | null): boolean {
  return entry?.id === "user-upload-image" || entry?.dynamic === true;
}

export function isIndexedDataset(entry: DatasetEntry | null): boolean {
  return !!entry?.index_range && !isUploadDataset(entry);
}

export function isRemotePlaceholder(entry: DatasetEntry | null): boolean {
  return entry?.status === "placeholder" || entry?.location === "remote";
}

export function custodySelectableDatasets(catalog: {
  local: DatasetEntry[];
  remote?: DatasetEntry[];
}): DatasetEntry[] {
  return catalog.local.filter(
    (d) => (!d.dynamic || d.id === "user-upload-image") && d.status !== "placeholder",
  );
}

export function indexBounds(entry: DatasetEntry | null): { min: number; max: number } {
  if (!entry?.index_range) return { min: 0, max: 9999 };
  return { min: entry.index_range[0], max: entry.index_range[1] };
}

export function custodySampleLabel(
  entry: DatasetEntry,
  opts: { index?: number; fileName?: string },
): string {
  if (opts.fileName) return opts.fileName;
  if (opts.index != null) return `${entry.name} #${opts.index}`;
  return entry.name;
}

export function custodyFileId(
  entry: DatasetEntry,
  opts: { index?: number; fileName?: string },
): string | undefined {
  if (opts.fileName) return undefined;
  if (opts.index != null) return `${entry.id}-${opts.index}`;
  return undefined;
}
