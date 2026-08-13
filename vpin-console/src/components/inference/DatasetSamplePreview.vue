<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { NButton, NEmpty, NSpin } from "naive-ui";
import type { SamplePreviewItem } from "@/services/datasetPreview";
import {
  galleryWindow,
  isPreviewableDatasetId,
  loadSampleGallery,
  loadSamplePreview,
} from "@/services/datasetPreview";
import { isTauri } from "@/services/aheClient";

const props = defineProps<{
  datasetId: string;
  inferMode: "single" | "batch";
  sampleIndex: number;
  batchStart: number;
  batchEnd: number;
  indexMin?: number;
  indexMax?: number;
}>();

const emit = defineEmits<{
  "update:sampleIndex": [value: number];
}>();

const loading = ref(false);
const gallery = ref<SamplePreviewItem[]>([]);
const current = ref<SamplePreviewItem | null>(null);

const bounds = computed(() => ({
  min: props.indexMin ?? 0,
  max: props.indexMax ?? 9999,
}));

const previewSrc = computed(() =>
  current.value?.preview_png_base64
    ? `data:image/png;base64,${current.value.preview_png_base64}`
    : "",
);

const previewClass = computed(() =>
  current.value?.preview_kind === "rgb" ? "preview-img rgb" : "preview-img grayscale",
);

function clearPreview(): void {
  current.value = null;
  gallery.value = [];
}

async function refreshPreview(): Promise<void> {
  if (!isPreviewableDatasetId(props.datasetId) || !isTauri()) {
    clearPreview();
    return;
  }

  loading.value = true;
  try {
    if (props.inferMode === "single") {
      const idx = Math.min(bounds.value.max, Math.max(bounds.value.min, props.sampleIndex));
      const item = await loadSamplePreview(props.datasetId, idx);
      current.value = item;
      const win = galleryWindow(idx, bounds.value, 5);
      gallery.value = item ? await loadSampleGallery(props.datasetId, win.start, win.count) : [];
      if (item && !gallery.value.some((g) => g.sample_index === item.sample_index)) {
        gallery.value = [item, ...gallery.value].slice(0, 5);
      }
    } else {
      const start = Math.min(bounds.value.max, Math.max(bounds.value.min, props.batchStart));
      const end = Math.min(bounds.value.max, Math.max(bounds.value.min, props.batchEnd));
      if (end < start) {
        clearPreview();
        return;
      }
      const count = Math.min(5, end - start + 1);
      gallery.value = await loadSampleGallery(props.datasetId, start, count);
      current.value =
        gallery.value.find((g) => g.sample_index === start) ?? gallery.value[0] ?? null;
    }
  } finally {
    loading.value = false;
  }
}

function selectGalleryItem(item: SamplePreviewItem): void {
  current.value = item;
  if (props.inferMode === "single") {
    emit("update:sampleIndex", item.sample_index);
  }
}

watch(
  () => props.datasetId,
  () => {
    clearPreview();
    void refreshPreview();
  },
);

watch(
  () => [props.inferMode, props.sampleIndex, props.batchStart, props.batchEnd, props.indexMin, props.indexMax] as const,
  () => {
    void refreshPreview();
  },
);

onMounted(() => {
  void refreshPreview();
});
</script>

<template>
  <div v-if="isPreviewableDatasetId(datasetId)" class="preview-block">
    <div class="preview-head">
      <span class="label">样本预览</span>
      <NButton size="tiny" quaternary :loading="loading" @click="refreshPreview">刷新</NButton>
    </div>
    <NSpin :show="loading">
      <div v-if="previewSrc" class="preview-main">
        <img :src="previewSrc" alt="样本预览" :class="previewClass" />
        <div class="preview-meta">
          <span>#{{ current?.sample_index }}</span>
          <span v-if="current?.label != null">标签 {{ current.label }}</span>
        </div>
      </div>
      <NEmpty v-else-if="!loading" size="small" :description="isTauri() ? '暂无预览' : '桌面端可预览'" />
    </NSpin>

    <div v-if="gallery.length" class="gallery">
      <button
        v-for="item in gallery"
        :key="`${datasetId}-${item.sample_index}`"
        type="button"
        class="gallery-item"
        :class="{ active: current?.sample_index === item.sample_index }"
        @click="selectGalleryItem(item)"
      >
        <img
          :src="`data:image/png;base64,${item.preview_png_base64}`"
          :alt="`#${item.sample_index}`"
          :class="item.preview_kind === 'rgb' ? 'thumb rgb' : 'thumb grayscale'"
        />
        <span>#{{ item.sample_index }}</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.preview-block {
  padding: 12px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-bg);
}

.preview-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.label {
  font-size: var(--text-sm);
  font-weight: 600;
}

.preview-main {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.preview-img {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: #fff;
}

.preview-img.grayscale {
  width: 112px;
  height: 112px;
  image-rendering: pixelated;
}

.preview-img.rgb {
  width: 128px;
  height: 128px;
}

.preview-meta {
  display: flex;
  gap: 12px;
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.gallery {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 8px;
  margin-top: 12px;
}

.gallery-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 6px;
  border: 2px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: #fff;
  cursor: pointer;
  font-size: 11px;
  color: var(--color-text-secondary);
}

.gallery-item.active {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 1px var(--color-primary-light);
}

.thumb.grayscale {
  width: 48px;
  height: 48px;
  image-rendering: pixelated;
}

.thumb.rgb {
  width: 48px;
  height: 48px;
}
</style>
