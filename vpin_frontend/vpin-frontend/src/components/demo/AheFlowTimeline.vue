<template>
  <div class="flow-timeline">
    <div v-if="engineLabel" class="engine-badge">
      <n-tag size="small" type="info">{{ engineLabel }}</n-tag>
      <n-text v-if="running" depth="3" style="font-size: 12px; margin-left: 8px">推理进行中…</n-text>
    </div>

    <n-steps v-if="running" :current="runningPhase" size="small" style="margin-bottom: 16px">
      <n-step
        v-for="p in expectedPhases"
        :key="p.id"
        :title="p.layer"
        :description="p.server"
      />
    </n-steps>

    <n-timeline>
      <n-timeline-item
        v-for="item in steps"
        :key="item.id + (item.at || '')"
        :type="itemType(item)"
        :title="item.title"
        :time="stepTime(item)"
      >
        <button type="button" class="step-btn" @click="emit('select', item)">
          <n-tag size="tiny" :bordered="false">{{ item.category }}</n-tag>
          <span class="step-summary">{{ item.summary }}</span>
          <n-text v-if="item.elapsed_ms != null" depth="3" class="step-elapsed">
            +{{ item.elapsed_ms.toFixed(0) }} ms
          </n-text>
          <n-text depth="3" class="step-hint">点击查看数据形式 →</n-text>
        </button>
      </n-timeline-item>
    </n-timeline>
  </div>
</template>

<script setup>
import { AHE_PHASES } from "../../constants/aheFlow.js";

defineProps({
  steps: { type: Array, default: () => [] },
  running: { type: Boolean, default: false },
  runningPhase: { type: Number, default: 0 },
  engineLabel: { type: String, default: "" },
});

const emit = defineEmits(["select"]);

const expectedPhases = AHE_PHASES;

function itemType(item) {
  if (item.category === "完成") return "success";
  if (item.category === "客户端" || item.category === "P3") return "warning";
  if (item.category === "服务端") return "info";
  return "default";
}

function stepTime(item) {
  const parts = [];
  if (item.at) parts.push(item.at);
  if (item.elapsed_ms != null) parts.push(`${item.elapsed_ms.toFixed(0)}ms`);
  return parts.join(" · ");
}
</script>

<style scoped>
.engine-badge {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
}

.step-btn {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  width: 100%;
  padding: 8px 10px;
  margin: -4px 0;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  cursor: pointer;
  text-align: left;
  transition: background 0.15s, border-color 0.15s;
}

.step-btn:hover {
  background: #f5f5f5;
  border-color: #e0e0e0;
}

.step-summary {
  font-size: 13px;
  color: #333;
}

.step-elapsed {
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}

.step-hint {
  font-size: 11px;
}
</style>
