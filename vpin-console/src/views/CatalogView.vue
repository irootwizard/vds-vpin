<script setup lang="ts">
import { h, onMounted, ref } from "vue";
import { useMessage } from "naive-ui";
import { NButton, NDataTable, NPopconfirm, NTag } from "naive-ui";
import { fetchDatasetCatalog, type DatasetEntry } from "@/services/datasetsApi";
import {
  filterVisibleDatasets,
  hideDatasetFromUi,
  isProtectedDataset,
} from "@/services/datasetUiStore";
import PageCard from "@/components/PageCard.vue";

const message = useMessage();
const local = ref<DatasetEntry[]>([]);
const loading = ref(true);

function reload(): void {
  loading.value = true;
  void fetchDatasetCatalog().then((catalog) => {
    local.value = catalog?.local ?? [];
    loading.value = false;
  });
}

function removeFromList(row: DatasetEntry): void {
  hideDatasetFromUi(row.id);
  local.value = local.value.filter((d) => d.id !== row.id);
  message.success("已从列表移除");
}

const columns = [
  { title: "ID", key: "id", ellipsis: { tooltip: true } },
  { title: "名称", key: "name", ellipsis: { tooltip: true } },
  { title: "类型", key: "kind" },
  {
    title: "样本数",
    key: "sample_count",
    render: (row: DatasetEntry) => row.sample_count?.toLocaleString() ?? "—",
  },
  {
    title: "索引",
    key: "index_range",
    render: (row: DatasetEntry) =>
      row.index_range ? `${row.index_range[0]}–${row.index_range[1]}` : "—",
  },
  {
    title: "来源",
    key: "location",
    render: () => h(NTag, { size: "small", type: "success" }, { default: () => "本地" }),
  },
  {
    title: "操作",
    key: "actions",
    width: 88,
    render: (row: DatasetEntry) =>
      isProtectedDataset(row.id)
        ? h("span", { class: "muted-action" }, "—")
        : h(
            NPopconfirm,
            { onPositiveClick: () => removeFromList(row) },
            {
              trigger: () =>
                h(
                  NButton,
                  { size: "tiny", quaternary: true, type: "error" },
                  { default: () => "删除" },
                ),
              default: () => "仅从列表移除，不删除本地文件",
            },
          ),
  },
];

onMounted(reload);
</script>

<template>
  <PageCard>
    <h1 class="page-title">数据集目录</h1>
    <p class="page-subtitle">本机可托管 / 可预览数据集</p>

    <n-spin :show="loading">
      <n-card size="small" title="本地数据集" :bordered="false" class="section">
        <NDataTable :columns="columns" :data="local" size="small" :bordered="false">
          <template #empty>暂无数据集</template>
        </NDataTable>
      </n-card>
    </n-spin>
  </PageCard>
</template>

<style scoped>
.section {
  margin-bottom: var(--space-4);
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
}

.page-subtitle {
  margin-bottom: var(--space-4);
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}

:deep(.muted-action) {
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
}
</style>
