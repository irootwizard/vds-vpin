<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";
import { NSteps, NStep } from "naive-ui";
import type { WorkflowNode } from "@/bridge/types";

const props = defineProps<{
  nodes: WorkflowNode[];
  compact?: boolean;
}>();

const route = useRoute();

const stageLabels = [
  { stage: "0", label: "Bootstrap" },
  { stage: "A", label: "Custody" },
  { stage: "B", label: "Inference" },
  { stage: "C", label: "Verify" },
];

const currentStep = computed(() => {
  const p = route.path;
  if (p.includes("/verification")) return 4;
  if (p.includes("/runs")) return 3;
  if (p.includes("/data")) return 2;
  return 1;
});

function nodeForStage(stage: string): WorkflowNode | undefined {
  return props.nodes.find((n) => n.stage === stage);
}
</script>

<template>
  <div class="workflow-nav" :class="{ compact }">
    <template v-if="compact">
      <div v-for="s in stageLabels" :key="s.stage" class="wf-row">
        <span class="wf-dot" :data-status="nodeForStage(s.stage)?.status ?? 'pending'" />
        <span class="wf-stage">{{ s.stage }}</span>
        <span class="wf-label">{{ s.label }}</span>
      </div>
    </template>
    <template v-else>
      <div class="protocol-bar__head">
        <span class="protocol-bar__title">工作流阶段</span>
        <span class="protocol-bar__hint">阶段 0 → A → B → C</span>
      </div>
      <NSteps :current="currentStep" size="small">
        <NStep v-for="s in stageLabels" :key="s.stage" :title="`${s.stage} ${s.label}`" />
      </NSteps>
    </template>
  </div>
</template>

<style scoped>
.workflow-nav.compact .wf-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 0;
  font-size: 11px;
}

.wf-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-text-muted);
  flex-shrink: 0;
}

.wf-dot[data-status="active"] {
  background: var(--color-primary);
  box-shadow: 0 0 0 3px rgba(79, 110, 247, 0.2);
}

.wf-dot[data-status="done"] {
  background: var(--color-success);
}

.wf-stage {
  font-family: var(--font-mono);
  color: var(--color-primary);
  font-weight: 600;
}

.wf-label {
  color: var(--color-text-secondary);
}

.protocol-bar__head {
  display: flex;
  align-items: baseline;
  gap: var(--space-3);
  margin-bottom: var(--space-2);
}

.protocol-bar__title {
  font-size: var(--text-sm);
  font-weight: 600;
}

.protocol-bar__hint {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
}

.workflow-nav:not(.compact) {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--space-3) var(--space-4);
  margin-bottom: var(--space-4);
  box-shadow: var(--shadow-sm);
}
</style>
