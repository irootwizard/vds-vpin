<template>
  <div class="batch-header">
    <div class="batch-header-top">
      <n-tag size="small" type="info">{{ engineLabel }}</n-tag>
      <n-text depth="3" style="font-size: 12px">
        批量 {{ meta.completed }}/{{ meta.total }} · 并发 {{ meta.concurrency }} WebSocket 会话
      </n-text>
      <n-text v-if="meta.accuracy != null && meta.completed" depth="3" style="font-size: 12px">
        acc {{ (meta.accuracy * 100).toFixed(1) }}%
      </n-text>
      <n-text v-if="meta.eta_s > 0 && running" depth="3" style="font-size: 12px">
        ETA {{ meta.eta_s.toFixed(0) }}s
      </n-text>
    </div>

    <n-progress
      type="line"
      :percentage="progressPct"
      :indicator-placement="'inside'"
      :processing="running"
      style="margin: 8px 0"
    />

    <n-steps :current="runningPhase" size="small">
      <n-step
        v-for="p in phases"
        :key="p.id"
        :title="p.layer"
        :description="focusJobId ? `focus: ${focusJobId}` : p.server"
      />
    </n-steps>
  </div>
</template>

<script setup>
import { AHE_PHASES } from "../../constants/aheFlow.js";

defineProps({
  meta: { type: Object, required: true },
  progressPct: { type: Number, default: 0 },
  runningPhase: { type: Number, default: 0 },
  running: { type: Boolean, default: false },
  engineLabel: { type: String, default: "" },
  focusJobId: { type: String, default: null },
});

const phases = AHE_PHASES;
</script>

<style scoped>
.batch-header-top {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}
</style>
