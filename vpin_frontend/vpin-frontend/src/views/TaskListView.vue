<script setup>
import { ref, computed, h } from "vue";
import { useRouter } from "vue-router";
import {
  NInput,
  NSelect,
  NButton,
  NDataTable,
  NTag,
  NSpace,
  useMessage,
} from "naive-ui";
import PageCard from "../components/PageCard.vue";
import { mockTasks, TASK_STATUS } from "../mocks/tasks.js";

const router = useRouter();
const message = useMessage();

const keyword = ref("");
const statusFilter = ref(null);

const statusOptions = [
  { label: "全部状态", value: null },
  { label: "运行中", value: "running" },
  { label: "已完成", value: "completed" },
  { label: "失败", value: "failed" },
];

const filteredTasks = computed(() => {
  return mockTasks.filter((t) => {
    const matchKw = !keyword.value || t.name.includes(keyword.value);
    const matchSt = !statusFilter.value || t.status === statusFilter.value;
    return matchKw && matchSt;
  });
});

const columns = [
  {
    title: "任务名称",
    key: "name",
    render(row) {
      return h(
        "a",
        {
          class: "task-link",
          onClick: () => router.push(`/tasks/${row.id}`),
        },
        row.name,
      );
    },
  },
  { title: "模型及版本", key: "model", render: (row) => `${row.model} (${row.modelVersion})` },
  {
    title: "状态",
    key: "status",
    width: 100,
    render(row) {
      const s = TASK_STATUS[row.status];
      return h(NTag, { size: "small", type: s?.type ?? "default", round: true }, () => s?.label ?? row.status);
    },
  },
  { title: "推理方案", key: "scheme", width: 140 },
  { title: "开始时间", key: "startedAt", width: 170 },
  { title: "结束时间", key: "endedAt", width: 170 },
  {
    title: "操作",
    key: "actions",
    width: 120,
    render(row) {
      return h(
        NSpace,
        { size: 8 },
        {
          default: () => [
            h(NButton, { size: "small", quaternary: true, type: "primary", onClick: () => router.push(`/tasks/${row.id}`) }, () => "详情"),
            h(NButton, { size: "small", quaternary: true, type: "error", onClick: () => message.info(`删除 ${row.name}（Mock）`) }, () => "删除"),
          ],
        },
      );
    },
  },
];

</script>

<template>
  <PageCard>
    <div class="page-head">
      <div>
        <h1 class="page-title">推理任务</h1>
        <p class="page-desc">管理隐私推理会话（对照隐语云「测评任务」列表，不含训练/优化）</p>
      </div>
      <NButton type="primary" @click="router.push('/tasks/new')">新建推理任务</NButton>
    </div>

    <div class="toolbar">
      <NInput v-model:value="keyword" placeholder="搜索任务名称" clearable style="width: 240px" />
      <NSelect v-model:value="statusFilter" :options="statusOptions" style="width: 140px" />
    </div>

    <NDataTable
      :columns="columns"
      :data="filteredTasks"
      :bordered="false"
      :single-line="false"
      size="small"
      class="task-table"
    />
  </PageCard>
</template>

<style scoped>
.page-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--space-4);
  margin-bottom: var(--space-5);
  flex-wrap: wrap;
}

.page-title {
  margin: 0 0 4px;
  font-size: var(--text-xl);
  font-weight: 600;
  color: var(--color-text-primary);
}

.page-desc {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.toolbar {
  display: flex;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
  flex-wrap: wrap;
}

.task-table :deep(.task-link) {
  color: var(--color-primary);
  cursor: pointer;
  text-decoration: none;
}

.task-table :deep(.task-link:hover) {
  text-decoration: underline;
}
</style>
