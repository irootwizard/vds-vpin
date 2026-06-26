<script setup>
import { NEmpty, NDescriptions, NDescriptionsItem, NTag, NStatistic } from "naive-ui";

defineProps({
  task: { type: Object, default: null },
});
</script>

<template>
  <div class="metrics-panel">
    <NTag size="small" type="warning" :bordered="false" style="margin-bottom: 12px">
      占位 · 推理指标将在接入 backend 会话结果后展示
    </NTag>
    <div class="metrics-grid">
      <div class="metric-card">
        <NStatistic label="推理准确率" value="—" />
        <span class="hint">CNN/LeNet 实验指标</span>
      </div>
      <div class="metric-card">
        <NStatistic label="Verify 结果" value="—" />
        <span class="hint">客户端本地验证</span>
      </div>
      <div class="metric-card">
        <NStatistic label="证明覆盖" value="部分" />
        <span class="hint">以验证报告为准</span>
      </div>
    </div>
    <NDescriptions v-if="task" :column="2" label-placement="left" bordered size="small" style="margin-top: 16px">
      <NDescriptionsItem label="测评方案">{{ task.scheme }}</NDescriptionsItem>
      <NDescriptionsItem label="模型">{{ task.model }} ({{ task.modelVersion }})</NDescriptionsItem>
      <NDescriptionsItem label="任务说明" :span="2">{{ task.description || "—" }}</NDescriptionsItem>
    </NDescriptions>
    <NEmpty v-else description="暂无指标数据" style="margin-top: 24px" />
  </div>
</template>

<style scoped>
.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: var(--space-4);
}

.metric-card {
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-4);
}

.hint {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}
</style>
