import type { SamplePreviewItem } from "@/services/datasetPreview";
import {
  isPreviewableDatasetId,
  loadSampleGallery,
  loadSamplePreview,
  parseSamplePreviewItem,
} from "@/services/datasetPreview";
import { isTauri, rustPreprocessBatch, rustPreprocessMnist } from "@/services/aheClient";

/** @deprecated use SamplePreviewItem */
export type MnistPreviewItem = SamplePreviewItem;

export { parseSamplePreviewItem as parseMnistPreviewItem };

export async function loadMnistPreview(index: number): Promise<SamplePreviewItem | null> {
  return loadSamplePreview("mnist-test", index);
}

export async function loadMnistGallery(
  start: number,
  count = 5,
): Promise<SamplePreviewItem[]> {
  if (isPreviewableDatasetId("mnist-test")) {
    return loadSampleGallery("mnist-test", start, count);
  }
  if (!isTauri() || count <= 0) return [];
  try {
    const raw = await rustPreprocessBatch(start, count);
    const items = raw.items;
    if (!Array.isArray(items)) return [];
    return items
      .map((it) => parseSamplePreviewItem(it as Record<string, unknown>, "mnist-test"))
      .filter((x): x is SamplePreviewItem => x != null);
  } catch {
    return [];
  }
}

// Legacy rust-only single load fallback
export async function loadMnistPreviewLegacy(index: number): Promise<SamplePreviewItem | null> {
  if (!isTauri()) return null;
  try {
    const raw = await rustPreprocessMnist(index);
    return parseSamplePreviewItem(raw, "mnist-test");
  } catch {
    return null;
  }
}
