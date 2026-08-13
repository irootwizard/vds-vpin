<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import {
  NButton,
  NInputNumber,
  NRadio,
  NRadioGroup,
  NSelect,
  NSpace,
  NText,
} from "naive-ui";
import DatasetSamplePreview from "@/components/inference/DatasetSamplePreview.vue";
import { fetchDatasetCatalog, type DatasetEntry } from "@/services/datasetsApi";
import { datasetEntryBounds, isPreviewableDatasetId } from "@/services/datasetPreview";

const inferMode = defineModel<"single" | "batch">("inferMode", { default: "single" });
const datasetId = defineModel<string>("datasetId", { default: "mnist-test" });
const sampleIndex = defineModel<number>("sampleIndex", { default: 0 });
const batchStart = defineModel<number>("batchStart", { default: 0 });
const batchEnd = defineModel<number>("batchEnd", { default: 4 });

/** @deprecated 兼容旧 v-model:mnist-index */
const legacyMnistIndex = defineModel<number | undefined>("mnistIndex");

const datasets = ref<DatasetEntry[]>([]);

const previewableDatasets = computed(() =>
  datasets.value.filter((d) => d.previewable && isPreviewableDatasetId(d.id)),
);

const options = computed(() =>
  previewableDatasets.value.map((d) => ({
    label: d.name,
    value: d.id,
  })),
);

const selected = computed(
  () => previewableDatasets.value.find((d) => d.id === datasetId.value) ?? null,
);

const bounds = computed(() => datasetEntryBounds(selected.value));

const batchCount = computed(() => Math.max(0, batchEnd.value - batchStart.value + 1));

const effectiveIndex = computed({
  get: () => legacyMnistIndex.value ?? sampleIndex.value,
  set: (v: number) => {
    sampleIndex.value = v;
    legacyMnistIndex.value = v;
  },
});

function resetForDataset(entry: DatasetEntry | null): void {
  if (!entry) return;
  const { min, max } = datasetEntryBounds(entry);
  effectiveIndex.value = min;
  batchStart.value = min;
  batchEnd.value = Math.min(max, min + 4);
}

watch(datasetId, (id, prev) => {
  if (id === prev) return;
  resetForDataset(selected.value);
});

watch(
  () => legacyMnistIndex.value,
  (v) => {
    if (v != null && v !== sampleIndex.value) sampleIndex.value = v;
  },
);

watch(sampleIndex, (v) => {
  if (legacyMnistIndex.value != null && legacyMnistIndex.value !== v) {
    legacyMnistIndex.value = v;
  }
});

function onBatchEndChange(v: number | null): void {
  if (v == null) return;
  batchEnd.value = Math.min(bounds.value.max, v);
  if (batchEnd.value < batchStart.value) batchStart.value = batchEnd.value;
}

function onBatchStartChange(v: number | null): void {
  if (v == null) return;
  batchStart.value = Math.max(bounds.value.min, v);
  if (batchEnd.value < batchStart.value) batchEnd.value = batchStart.value;
}

onMounted(async () => {
  const catalog = await fetchDatasetCatalog();
  datasets.value = catalog?.local ?? [];
  if (datasets.value.length && !datasets.value.some((d) => d.id === datasetId.value)) {
    datasetId.value = previewableDatasets.value[0]?.id ?? "mnist-test";
  }
  resetForDataset(selected.value);
});
</script>

<template>
  <div class="sample-panel">
    <div class="field-row">
      <span class="field-label">数据集</span>
      <NSelect
        v-model:value="datasetId"
        :options="options"
        placeholder="选择数据集"
        style="max-width: 320px"
      />
    </div>

    <div class="field-row">
      <span class="field-label">选择方式</span>
      <NRadioGroup v-model:value="inferMode">
        <NSpace>
          <NRadio value="single">序号 Index</NRadio>
          <NRadio value="batch">范围 Range</NRadio>
        </NSpace>
      </NRadioGroup>
    </div>

    <div v-if="inferMode === 'single'" class="field-row">
      <span class="field-label">样本序号</span>
      <NSpace align="center">
        <NButton
          quaternary
          size="small"
          @click="effectiveIndex = Math.max(bounds.min, effectiveIndex - 1)"
        >
          −
        </NButton>
        <NInputNumber
          v-model:value="effectiveIndex"
          :min="bounds.min"
          :max="bounds.max"
          style="width: 120px"
        />
        <NButton
          quaternary
          size="small"
          @click="effectiveIndex = Math.min(bounds.max, effectiveIndex + 1)"
        >
          +
        </NButton>
        <NText depth="3">#{{ effectiveIndex }}</NText>
      </NSpace>
    </div>

    <div v-else class="field-row">
      <span class="field-label">序号范围</span>
      <NSpace align="center">
        <NInputNumber
          :value="batchStart"
          :min="bounds.min"
          :max="bounds.max"
          style="width: 120px"
          @update:value="onBatchStartChange"
        />
        <NText depth="3">—</NText>
        <NInputNumber
          :value="batchEnd"
          :min="bounds.min"
          :max="bounds.max"
          style="width: 120px"
          @update:value="onBatchEndChange"
        />
        <NText depth="3">共 {{ batchCount }} 张</NText>
      </NSpace>
    </div>

    <DatasetSamplePreview
      :dataset-id="datasetId"
      :infer-mode="inferMode"
      :sample-index="effectiveIndex"
      :batch-start="batchStart"
      :batch-end="batchEnd"
      :index-min="bounds.min"
      :index-max="bounds.max"
      @update:sample-index="effectiveIndex = $event"
    />
  </div>
</template>

<style scoped>
.sample-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
  width: 100%;
}

.field-row {
  display: flex;
  align-items: center;
  gap: 16px;
}

.field-label {
  width: 104px;
  flex-shrink: 0;
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}
</style>
