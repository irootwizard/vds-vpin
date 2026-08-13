<script setup lang="ts">
import { computed, ref, watch } from "vue";
import {
  NButton,
  NDescriptions,
  NDescriptionsItem,
  NInputNumber,
  NRadio,
  NRadioGroup,
  NSelect,
  NSpace,
  NTag,
  NUpload,
} from "naive-ui";
import type { UploadFileInfo } from "naive-ui";
import DatasetSamplePreview from "@/components/inference/DatasetSamplePreview.vue";
import type { DatasetEntry } from "@/services/datasetsApi";
import {
  custodySelectableDatasets,
  indexBounds,
  isIndexedDataset,
  isUploadDataset,
} from "@/services/custodyDataset";
import { datasetEntryBounds, isPreviewableDatasetId } from "@/services/datasetPreview";

const props = defineProps<{
  datasets: DatasetEntry[];
  loading?: boolean;
  starting?: boolean;
}>();

const emit = defineEmits<{
  start: [];
}>();

const selectedId = defineModel<string>("datasetId", { default: "mnist-test" });
const sampleIndex = defineModel<number>("sampleIndex", { default: 0 });
const uploadFile = defineModel<File | null>("uploadFile", { default: null });

const selectMode = ref<"single" | "batch">("single");
const batchStart = ref(0);
const batchEnd = ref(4);

const options = computed(() =>
  custodySelectableDatasets({ local: props.datasets }).map((d) => ({
    label: d.name,
    value: d.id,
  })),
);

const selected = computed(
  () => props.datasets.find((d) => d.id === selectedId.value) ?? null,
);

const bounds = computed(() => indexBounds(selected.value));
const showIndexInput = computed(() => isIndexedDataset(selected.value));
const showUpload = computed(() => isUploadDataset(selected.value));
const showPreview = computed(
  () => showIndexInput.value && isPreviewableDatasetId(selectedId.value),
);
const canStart = computed(() => {
  if (showUpload.value) return uploadFile.value != null;
  if (showIndexInput.value) {
    if (selectMode.value === "batch") {
      return batchEnd.value >= batchStart.value;
    }
    return (
      sampleIndex.value >= bounds.value.min && sampleIndex.value <= bounds.value.max
    );
  }
  return false;
});

function clearSelectionState(): void {
  uploadFile.value = null;
}

function resetIndexForDataset(entry: DatasetEntry | null): void {
  if (!entry?.index_range) return;
  const b = datasetEntryBounds(entry);
  sampleIndex.value = b.min;
  batchStart.value = b.min;
  batchEnd.value = Math.min(b.max, b.min + 4);
}

function onFileChange(options: { file: UploadFileInfo }) {
  uploadFile.value = (options.file.file as File) ?? null;
}

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

watch(selectedId, (id, prev) => {
  if (id === prev) return;
  clearSelectionState();
  resetIndexForDataset(selected.value);
});

watch(
  () => props.datasets,
  (list) => {
    if (list.length && !list.some((d) => d.id === selectedId.value)) {
      selectedId.value = list[0]?.id ?? "mnist-test";
      resetIndexForDataset(list[0] ?? null);
    }
  },
  { immediate: true },
);
</script>

<template>
  <NSpace vertical :size="16">
    <div>
      <span class="label">托管数据集</span>
      <NSelect
        v-model:value="selectedId"
        :options="options"
        :loading="loading"
        placeholder="选择数据集"
        style="max-width: 420px"
      />
    </div>

    <NDescriptions v-if="selected" :column="2" label-placement="left" size="small" class="meta">
      <NDescriptionsItem label="格式">{{ selected.format ?? selected.kind }}</NDescriptionsItem>
      <NDescriptionsItem label="样本数">
        {{ selected.sample_count?.toLocaleString() ?? "按需上传" }}
      </NDescriptionsItem>
      <NDescriptionsItem v-if="selected.index_range" label="索引范围">
        {{ selected.index_range[0] }} – {{ selected.index_range[1] }}
      </NDescriptionsItem>
      <NDescriptionsItem label="来源">
        <NTag size="small" :type="selected.location === 'local' ? 'success' : 'warning'">
          {{ selected.location === "local" ? "本地" : "远程" }}
        </NTag>
      </NDescriptionsItem>
    </NDescriptions>

    <p v-if="selected?.message" class="hint">{{ selected.message }}</p>

    <template v-if="showIndexInput">
      <div>
        <span class="label">选择方式</span>
        <NRadioGroup v-model:value="selectMode">
          <NSpace>
            <NRadio value="single">序号 Index</NRadio>
            <NRadio value="batch">范围 Range</NRadio>
          </NSpace>
        </NRadioGroup>
      </div>

      <div v-if="selectMode === 'single'">
        <span class="label">样本序号</span>
        <NSpace align="center">
          <NInputNumber
            v-model:value="sampleIndex"
            :min="bounds.min"
            :max="bounds.max"
            style="width: 160px"
          />
          <span class="hint">范围 {{ bounds.min }} – {{ bounds.max }}</span>
        </NSpace>
      </div>

      <div v-else>
        <span class="label">序号范围</span>
        <NSpace align="center">
          <NInputNumber
            :value="batchStart"
            :min="bounds.min"
            :max="bounds.max"
            style="width: 120px"
            @update:value="onBatchStartChange"
          />
          <span class="hint">—</span>
          <NInputNumber
            :value="batchEnd"
            :min="bounds.min"
            :max="bounds.max"
            style="width: 120px"
            @update:value="onBatchEndChange"
          />
        </NSpace>
      </div>

      <DatasetSamplePreview
        v-if="showPreview"
        :key="selectedId"
        :dataset-id="selectedId"
        :infer-mode="selectMode"
        :sample-index="sampleIndex"
        :batch-start="batchStart"
        :batch-end="batchEnd"
        :index-min="bounds.min"
        :index-max="bounds.max"
        @update:sample-index="sampleIndex = $event"
      />
    </template>

    <div v-if="showUpload">
      <span class="label">上传本地文件</span>
      <NUpload :max="1" accept="image/*" @change="onFileChange">
        <NButton>选择文件</NButton>
      </NUpload>
      <p v-if="uploadFile" class="hint">已选：{{ uploadFile.name }}</p>
    </div>

    <NButton type="primary" :disabled="!canStart || starting" :loading="starting" @click="emit('start')">
      开始托管
    </NButton>
  </NSpace>
</template>

<style scoped>
.label {
  display: block;
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  margin-bottom: 6px;
}

.hint {
  margin: 8px 0 0;
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}

.meta {
  padding: 8px 12px;
  background: var(--color-bg);
  border-radius: var(--radius-sm);
}
</style>
