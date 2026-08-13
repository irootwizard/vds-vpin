import { isTauri } from "@/services/aheClient";
import { indexBounds } from "@/services/custodyDataset";
import type { DatasetEntry } from "@/services/datasetsApi";

export type PreviewKind = "grayscale" | "rgb";

export interface SamplePreviewItem {
  dataset_id: string;
  sample_index: number;
  label?: number;
  preview_png_base64: string;
  preview_kind: PreviewKind;
  input_digest_hex?: string;
}

export const PREVIEWABLE_DATASET_IDS = [
  "mnist-test",
  "mnist-train",
  "cifar10-test",
  "cifar10-train",
] as const;

export function isPreviewableDatasetId(id: string): boolean {
  return (PREVIEWABLE_DATASET_IDS as readonly string[]).includes(id);
}

export function datasetEntryBounds(entry: DatasetEntry | null): { min: number; max: number } {
  return indexBounds(entry);
}

function extractPreviewB64(raw: Record<string, unknown>): string {
  const normalized = raw.normalized as Record<string, unknown> | undefined;
  return String(
    raw.preview_png_base64 ??
      normalized?.preview_png_base64 ??
      "",
  );
}

export function parseSamplePreviewItem(
  raw: Record<string, unknown>,
  datasetId: string,
): SamplePreviewItem | null {
  const preview = extractPreviewB64(raw);
  if (!preview) return null;
  const sample_index = Number(
    raw.sample_index ?? raw.mnist_index ?? raw.cifar_index ?? raw.mnistIndex ?? -1,
  );
  if (sample_index < 0) return null;
  const labelRaw = raw.label ?? raw.true_label;
  const label = labelRaw != null ? Number(labelRaw) : undefined;
  const preview_kind =
    raw.preview_kind === "rgb" || datasetId.startsWith("cifar10") ? "rgb" : "grayscale";
  const digest = raw.input_digest_hex != null ? String(raw.input_digest_hex) : undefined;
  return {
    dataset_id: String(raw.dataset_id ?? datasetId),
    sample_index,
    label,
    preview_png_base64: preview,
    preview_kind,
    input_digest_hex: digest,
  };
}

async function invokeDatasetSingle(datasetId: string, index: number): Promise<Record<string, unknown>> {
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke("preprocess_dataset_single", { datasetId, index }) as Promise<
    Record<string, unknown>
  >;
}

async function invokeDatasetBatch(
  datasetId: string,
  start: number,
  count: number,
): Promise<Record<string, unknown>> {
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke("preprocess_dataset_batch", { datasetId, start, count }) as Promise<
    Record<string, unknown>
  >;
}

export async function loadSamplePreview(
  datasetId: string,
  index: number,
): Promise<SamplePreviewItem | null> {
  if (!isTauri() || !isPreviewableDatasetId(datasetId)) return null;
  try {
    const raw = await invokeDatasetSingle(datasetId, index);
    return parseSamplePreviewItem(raw, datasetId);
  } catch {
    return null;
  }
}

export async function loadSampleGallery(
  datasetId: string,
  start: number,
  count = 5,
): Promise<SamplePreviewItem[]> {
  if (!isTauri() || !isPreviewableDatasetId(datasetId) || count <= 0) return [];
  try {
    const raw = await invokeDatasetBatch(datasetId, start, count);
    const items = raw.items;
    if (!Array.isArray(items)) return [];
    return items
      .map((it) => parseSamplePreviewItem(it as Record<string, unknown>, datasetId))
      .filter((x): x is SamplePreviewItem => x != null);
  } catch {
    return [];
  }
}

/** 单图模式：以 index 为中心取 5 张缩略图 */
export function galleryWindow(
  index: number,
  bounds: { min: number; max: number },
  size = 5,
): { start: number; count: number } {
  const half = Math.floor(size / 2);
  let start = index - half;
  if (start < bounds.min) start = bounds.min;
  if (start + size - 1 > bounds.max) start = Math.max(bounds.min, bounds.max - size + 1);
  const count = Math.min(size, bounds.max - start + 1);
  return { start, count };
}
