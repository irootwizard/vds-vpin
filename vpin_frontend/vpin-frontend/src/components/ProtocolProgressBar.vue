<script setup>
import { computed } from "vue";
import { NSteps, NStep, NTooltip } from "naive-ui";
import { PROTOCOL_STEPS, useProtocolSession } from "../composables/useProtocolSession.js";

const { state } = useProtocolSession();

const displayStep = computed(() => state.currentStep + 1);
</script>

<template>
  <div class="protocol-bar">
    <div class="protocol-bar__head">
      <span class="protocol-bar__title">协议进度</span>
      <span class="protocol-bar__hint">vPIN 论文六阶段 · 当前：{{ PROTOCOL_STEPS[state.currentStep]?.label }}</span>
    </div>
    <NSteps :current="displayStep" size="small" class="protocol-bar__steps">
      <NStep v-for="step in PROTOCOL_STEPS" :key="step.key">
        <template #title>
          <NTooltip trigger="hover">
            <template #trigger>{{ step.label }}</template>
            {{ step.desc }}
          </NTooltip>
        </template>
      </NStep>
    </NSteps>
  </div>
</template>

<style scoped>
.protocol-bar {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--space-3) var(--space-4);
  margin-bottom: var(--space-4);
  box-shadow: var(--shadow-sm);
}

.protocol-bar__head {
  display: flex;
  align-items: baseline;
  gap: var(--space-3);
  margin-bottom: var(--space-2);
  flex-wrap: wrap;
}

.protocol-bar__title {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text-primary);
}

.protocol-bar__hint {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
}

.protocol-bar__steps {
  overflow-x: auto;
}
</style>
