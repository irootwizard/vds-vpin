<template>
  <div class="flow-timeline">
    <n-steps v-if="running" :current="runningPhase" size="small" style="margin-bottom: 16px">
      <n-step v-for="p in expectedPhases" :key="p.id" :title="p.layer" :description="p.server" />
    </n-steps>

    <n-timeline>
      <n-timeline-item
        v-for="item in steps"
        :key="item.id"
        :type="itemType(item)"
        :title="item.title"
        :time="item.at"
      >
        <button type="button" class="step-btn" @click="emit('select', item)">
          <n-tag size="tiny" :bordered="false">{{ item.category }}</n-tag>
          <span class="step-summary">{{ item.summary }}</span>
          <n-text depth="3" class="step-hint">点击查看数据形式 →</n-text>
        </button>
      </n-timeline-item>
    </n-timeline>
  </div>
</template>

<script setup>
import { AHE_PHASES } from "../../constants/aheFlow.js";

const props = defineProps({
  steps: { type: Array, default: () => [] },
  running: { type: Boolean, default: false },
  runningPhase: { type: Number, default: 0 },
});

const emit = defineEmits(["select"]);

const expectedPhases = AHE_PHASES;

function itemType(item) {
  if (item.category === "完成") return "success";
  if (item.category === "客户端" || item.category === "P3") return "warning";
  if (item.category === "服务端") return "info";
  return "default";
}
</script>

<style scoped>
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

.step-hint {
  font-size: 11px;
}
</style>
