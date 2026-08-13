<script setup>
import { NTag, NSkeleton, NStatistic } from "naive-ui";
import { BarChartOutline } from "@vicons/ionicons5";
import { NIcon } from "naive-ui";

const props = defineProps({
  metrics: { type: Object, default: null },
  loading: { type: Boolean, default: false },
  mock: { type: Boolean, default: false },
});
</script>

<template>
  <div class="status-card warning">
    <div class="status-icon">
      <NIcon :size="22" color="#faad14"><BarChartOutline /></NIcon>
    </div>
    <div class="status-content">
      <div class="card-head">
        <h3>推理用量</h3>
        <NTag v-if="mock" size="small" type="warning" :bordered="false">演示数据</NTag>
      </div>
      <NSkeleton v-if="loading" text :repeat="2" />
      <template v-else-if="metrics">
        <p>累计推理与会话同态算子统计</p>
        <div class="stats-row">
          <NStatistic label="总推理次数" :value="metrics.total_inferences" />
          <NStatistic label="今日" :value="metrics.delta_1d" />
          <NStatistic label="近 7 日" :value="metrics.delta_7d" />
        </div>
        <div class="status-details">
          <span class="detail-item">pt_add 累计：{{ metrics.usage?.pt_add_total?.toLocaleString() ?? "—" }}</span>
          <span class="detail-item">pt_mult 累计：{{ metrics.usage?.pt_mult_total?.toLocaleString() ?? "—" }}</span>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.status-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--space-5);
  border-left: 4px solid #faad14;
  height: 100%;
}

.status-icon {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: var(--space-3);
  background: rgba(250, 173, 20, 0.1);
}

.card-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.card-head h3 {
  font-size: 16px;
  font-weight: 600;
  margin: 0;
}

.status-content p {
  color: var(--color-text-secondary);
  font-size: 14px;
  margin: 0 0 12px;
}

.stats-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  margin-bottom: 12px;
}

.status-details {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 13px;
  color: var(--color-text-secondary);
}
</style>
