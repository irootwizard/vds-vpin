<script setup>
import { NTag, NSteps, NStep } from "naive-ui";
import { CONFIDENTIAL_FLOW_STEPS } from "../../mocks/tasks.js";

const props = defineProps({
  steps: { type: Array, default: () => CONFIDENTIAL_FLOW_STEPS },
});

function stepStatus(status) {
  if (status === "done") return "finish";
  if (status === "active") return "process";
  if (status === "error") return "error";
  return "wait";
}
</script>

<template>
  <div class="flow-panel">
    <div class="flow-panel__head">
      <span class="flow-panel__title">密态流程</span>
      <NTag size="small" type="warning" :bordered="false">占位 · 后续绑定真实会话状态机</NTag>
    </div>
    <p class="flow-panel__desc">
      对照 vPIN 论文协议：Setup → Commit → Infer（含截断）→ Challenge → Prove → Verify。
      不含隐语云大模型 KMS/TEE 解密流程。
    </p>
    <NSteps vertical :current="4" class="flow-steps">
      <NStep
        v-for="(step, index) in props.steps"
        :key="index"
        :title="step.title"
        :description="step.desc"
        :status="stepStatus(step.status)"
      />
    </NSteps>
  </div>
</template>

<style scoped>
.flow-panel__head {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-bottom: var(--space-2);
}

.flow-panel__title {
  font-weight: 600;
  font-size: var(--text-base);
  color: var(--color-text-primary);
}

.flow-panel__desc {
  margin: 0 0 var(--space-4);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  line-height: 1.6;
}

.flow-steps {
  padding: var(--space-2) 0;
}
</style>
