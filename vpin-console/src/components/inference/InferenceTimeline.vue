<script setup lang="ts">
import { AHE_PHASE_WEIGHTS } from "@/demo/demoTiming";

export interface TimelineStep {
  id: string;
  phase_id: string;
  title: string;
  category: string;
  summary: string;
  at?: string;
  elapsed_ms?: number;
  status: "pending" | "active" | "done";
}

defineProps<{
  steps: TimelineStep[];
  running: boolean;
  runningPhase: number;
  engineLabel?: string;
}>();

const expectedPhases = AHE_PHASE_WEIGHTS;
</script>

<template>
  <div class="flow-timeline">
    <div v-if="engineLabel" class="engine-badge">
      <n-tag size="small" type="info">{{ engineLabel }}</n-tag>
      <n-text v-if="running" depth="3" style="font-size: 12px; margin-left: 8px">推理进行中…</n-text>
    </div>

    <n-steps v-if="running" :current="runningPhase" size="small" style="margin-bottom: 16px">
      <n-step
        v-for="p in expectedPhases"
        :key="p.phase_id"
        :title="p.label"
        :description="p.phase_id"
      />
    </n-steps>

    <n-timeline>
      <n-timeline-item
        v-for="item in steps"
        :key="item.id"
        :type="item.status === 'done' ? 'success' : item.status === 'active' ? 'warning' : 'default'"
        :title="item.title"
        :time="item.at"
      >
        <n-tag size="tiny" :bordered="false">{{ item.category }}</n-tag>
        <div class="summary">{{ item.summary }}</div>
        <n-text v-if="item.elapsed_ms != null" depth="3" class="mono">
          +{{ item.elapsed_ms.toFixed(0) }} ms
        </n-text>
      </n-timeline-item>
    </n-timeline>
  </div>
</template>

<style scoped>
.engine-badge {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
}

.summary {
  font-size: 13px;
  margin-top: 4px;
}
</style>
