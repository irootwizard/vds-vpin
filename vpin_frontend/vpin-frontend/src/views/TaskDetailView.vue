<script setup>
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  NButton,
  NTag,
  NTabs,
  NTabPane,
  NDescriptions,
  NDescriptionsItem,
  NIcon,
  useMessage,
} from "naive-ui";
import { ArrowBackOutline } from "@vicons/ionicons5";
import PageCard from "../components/PageCard.vue";
import LogPanel from "../components/task/LogPanel.vue";
import ConfidentialFlowPanel from "../components/task/ConfidentialFlowPanel.vue";
import MetricsPanel from "../components/task/MetricsPanel.vue";
import { getTaskById, TASK_STATUS } from "../mocks/tasks.js";

const route = useRoute();
const router = useRouter();
const message = useMessage();

const task = computed(() => getTaskById(route.params.id));

const statusMeta = computed(() => {
  if (!task.value) return null;
  return TASK_STATUS[task.value.status];
});
</script>

<template>
  <div v-if="task" class="task-detail">
    <PageCard class="detail-head-card">
      <div class="detail-head">
        <div class="detail-head__left">
          <NButton quaternary circle @click="router.push('/tasks')">
            <template #icon><NIcon><ArrowBackOutline /></NIcon></template>
          </NButton>
          <h1>{{ task.name }}</h1>
          <NTag :type="statusMeta?.type ?? 'default'" round>{{ statusMeta?.label }}</NTag>
          <NTag size="small" :bordered="false">演示 Mock</NTag>
        </div>
        <NButton type="error" secondary size="small" @click="message.info('删除（Mock）')">删除</NButton>
      </div>

      <h2 class="section-label">配置信息</h2>
      <NDescriptions :column="3" label-placement="left" bordered size="small">
        <NDescriptionsItem label="模型及版本">{{ task.model }} ({{ task.modelVersion }})</NDescriptionsItem>
        <NDescriptionsItem label="推理方案">{{ task.scheme }}</NDescriptionsItem>
        <NDescriptionsItem label="会话 ID">
          <code class="mono">{{ task.id }}</code>
        </NDescriptionsItem>
        <NDescriptionsItem label="开始时间">{{ task.startedAt }}</NDescriptionsItem>
        <NDescriptionsItem label="结束时间">{{ task.endedAt }}</NDescriptionsItem>
        <NDescriptionsItem label="任务描述">{{ task.description || "—" }}</NDescriptionsItem>
      </NDescriptions>

      <h2 class="section-label" style="margin-top: 20px">资源配置</h2>
      <NDescriptions :column="2" label-placement="left" bordered size="small">
        <NDescriptionsItem label="AHE 曲线">E2-default（Mock）</NDescriptionsItem>
        <NDescriptionsItem label="CP-SNARK">桥接状态见安全中心</NDescriptionsItem>
      </NDescriptions>
    </PageCard>

    <PageCard class="tabs-card">
      <NTabs type="line" animated default-value="metrics">
        <NTabPane name="metrics" tab="效果指标">
          <MetricsPanel :task="task" />
        </NTabPane>
        <NTabPane name="logs" tab="日志详情">
          <LogPanel />
        </NTabPane>
        <NTabPane name="flow" tab="密态流程">
          <ConfidentialFlowPanel />
        </NTabPane>
      </NTabs>
    </PageCard>
  </div>

  <PageCard v-else>
    <p>任务不存在</p>
    <NButton type="primary" @click="router.push('/tasks')">返回列表</NButton>
  </PageCard>
</template>

<style scoped>
.task-detail {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.detail-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-5);
  flex-wrap: wrap;
  gap: var(--space-3);
}

.detail-head__left {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-wrap: wrap;
}

.detail-head h1 {
  margin: 0;
  font-size: var(--text-xl);
  font-weight: 600;
}

.section-label {
  margin: 0 0 var(--space-3);
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--color-text-primary);
}

.mono {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
}

.tabs-card {
  padding-top: var(--space-4);
}
</style>
