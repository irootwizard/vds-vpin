<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { NButton, NDataTable } from "naive-ui";
import { getBridge } from "@/bridge/client";
import type { RunRecord } from "@/bridge/types";
import PageCard from "@/components/PageCard.vue";
import { inferenceEngineLabel } from "@/utils/productLabels";

const router = useRouter();
const runs = ref<RunRecord[]>([]);

const columns = [
  { title: "Run ID", key: "run_id", ellipsis: { tooltip: true } },
  {
    title: "模型",
    key: "model",
    render: (row: RunRecord) => row.config.model_id,
  },
  {
    title: "批量",
    key: "batch",
    render: (row: RunRecord) => row.config.batch_size,
  },
  { title: "状态", key: "status" },
  {
    title: "引擎",
    key: "engine",
    render: (row: RunRecord) => inferenceEngineLabel(row.inference_engine),
  },
];

onMounted(async () => {
  const res = await getBridge().bridgeRunList();
  if (res.ok && res.data) runs.value = res.data;
});
</script>

<template>
  <PageCard>
    <div class="head">
      <div>
        <h1 class="page-title">推理运行</h1>
        <p class="page-subtitle">L3 调度 · 运行列表</p>
      </div>
      <NButton type="primary" @click="router.push('/runs/new')">新建</NButton>
    </div>
    <NDataTable
      :columns="columns"
      :data="runs"
      size="small"
      :row-props="(row: RunRecord) => ({
        style: 'cursor:pointer',
        onClick: () => router.push(`/runs/${row.run_id}`),
      })"
    />
  </PageCard>
</template>

<style scoped>
.head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: var(--space-2);
}

.page-subtitle {
  margin-bottom: var(--space-4);
}
</style>
