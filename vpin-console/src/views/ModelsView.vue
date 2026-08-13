<script setup lang="ts">
import { computed, h, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { NButton, NDataTable, NTag, NTooltip } from "naive-ui";
import { resolveInferencePlan } from "@/config/modelCatalog";
import { isTauri } from "@/services/aheClient";
import {
  fetchEnrichedModelCatalog,
  type EnrichedModel,
} from "@/services/modelCatalogApi";
import PageCard from "@/components/PageCard.vue";

const router = useRouter();
const models = ref<EnrichedModel[]>([]);
const aheIds = ref<Set<string>>(new Set());
const desktop = isTauri();

const columns = computed(() => [
  { title: "ID", key: "id", ellipsis: { tooltip: true } },
  { title: "名称", key: "name", ellipsis: { tooltip: true } },
  {
    title: "模型族",
    key: "familyLabel",
    render: (row: EnrichedModel) =>
      h(NTag, { size: "small", round: true }, () => row.familyLabel),
  },
  { title: "输入", key: "input_shape" },
  {
    title: "测试准确度",
    key: "accuracy",
    render: (row: EnrichedModel) =>
      row.accuracy > 0 ? `${row.accuracy.toFixed(2)}%` : "—",
  },
  {
    title: "推理路径",
    key: "inference",
    render: (row: EnrichedModel) => {
      const plan = resolveInferencePlan(row, row.id, aheIds.value, desktop);
      return h(
        NTag,
        {
          size: "small",
          round: true,
          type: plan.mode === "rust_ahe" ? "success" : "info",
        },
        () => (plan.mode === "rust_ahe" ? "密态推理" : "演示计时"),
      );
    },
  },
  {
    title: "说明",
    key: "message",
    render: (row: EnrichedModel) =>
      row.message
        ? h(NTooltip, null, {
            trigger: () => h("span", { class: "hint" }, "…"),
            default: () => row.message,
          })
        : row.deployable === false
          ? "待 AHE 部署"
          : "—",
  },
]);

onMounted(async () => {
  const catalog = await fetchEnrichedModelCatalog();
  models.value = catalog.models;
  aheIds.value = catalog.aheCapableIds;
});
</script>

<template>
  <PageCard>
    <h1 class="page-title">模型仓库</h1>
    <p class="page-subtitle">
      已注册模型 · 按模型族自动匹配数据集与推理路径（Network A / LeNet / ResNet …）
    </p>
    <NDataTable :columns="columns" :data="models" :bordered="false" size="small">
      <template #empty>暂无模型</template>
    </NDataTable>
    <NButton style="margin-top: 16px" type="primary" @click="router.push('/runs/new')">
      使用模型创建任务
    </NButton>
  </PageCard>
</template>

<style scoped>
.hint {
  cursor: help;
  color: var(--color-text-muted);
}
</style>
