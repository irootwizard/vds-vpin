<script setup lang="ts">
import { computed } from "vue";
import { AHE_PHASE_WEIGHTS } from "@/demo/demoTiming";

const props = defineProps<{
  completed: number;
  total: number;
  running: boolean;
  activePhaseIndex: number;
}>();

const pct = computed(() =>
  props.total > 0 ? Math.round((props.completed / props.total) * 100) : 0,
);

const phases = AHE_PHASE_WEIGHTS;
</script>

<template>
  <div class="batch-header">
    <div class="row">
      <span class="title">批量推理</span>
      <n-tag v-if="running" size="small" type="warning">进行中</n-tag>
      <span class="mono stats">{{ completed }} / {{ total }} ({{ pct }}%)</span>
    </div>
    <n-progress
      type="line"
      :percentage="pct"
      :show-indicator="false"
      :height="8"
      status="info"
    />
    <div v-if="running" class="phase-bar">
      <span
        v-for="(p, i) in phases"
        :key="p.phase_id"
        class="phase-chip"
        :class="{ active: i === activePhaseIndex }"
      >
        {{ p.label }}
      </span>
    </div>
  </div>
</template>

<style scoped>
.batch-header {
  margin-bottom: var(--space-4);
  padding: var(--space-4);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm);
}

.row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}

.title {
  font-weight: 600;
}

.stats {
  margin-left: auto;
  color: var(--color-text-muted);
  font-family: var(--font-mono);
}

.phase-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}

.phase-chip {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: var(--radius-full);
  background: var(--color-bg);
  color: var(--color-text-muted);
  border: 1px solid var(--color-border);
}

.phase-chip.active {
  background: rgba(79, 110, 247, 0.12);
  color: var(--color-primary);
  border-color: rgba(79, 110, 247, 0.3);
}
</style>
