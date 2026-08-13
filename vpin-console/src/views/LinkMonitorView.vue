<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";
import { NCard, NDescriptions, NDescriptionsItem, NSpin, NTag } from "naive-ui";
import {
  fetchSecurityTransport,
  type InferenceMetrics,
  type SecurityTransport,
} from "@/services/securityApi";
import {
  refreshInferenceMetrics,
  subscribeInferenceMetrics,
} from "@/services/inferenceMetricsRecorder";
import { inferenceEventBus } from "@/bridge/eventBus";
import { aheServerApiBase } from "@/config/endpoints";
import InferenceMetricsCharts from "@/components/security/InferenceMetricsCharts.vue";
import PageCard from "@/components/PageCard.vue";

const loading = ref(true);
const transport = ref<SecurityTransport | null>(null);
const metrics = ref<InferenceMetrics | null>(null);

let unsubMetrics: (() => void) | null = null;
let unsubRun: (() => void) | null = null;

async function loadAll() {
  loading.value = true;
  const [t, m] = await Promise.all([fetchSecurityTransport(), refreshInferenceMetrics()]);
  transport.value = t;
  metrics.value = m;
  loading.value = false;
}

onMounted(() => {
  void loadAll();
  unsubMetrics = subscribeInferenceMetrics((m) => {
    if (m) metrics.value = m;
  });
  unsubRun = inferenceEventBus.subscribe((ev) => {
    if (ev.event === "run_completed") void refreshInferenceMetrics();
  });
});

onUnmounted(() => {
  unsubMetrics?.();
  unsubRun?.();
});
</script>

<template>
  <PageCard>
    <h1 class="page-title">链路监视</h1>
    <p class="page-subtitle">传输层与会话端点 · 推理用量统计</p>

    <NSpin :show="loading">
      <NCard size="small" title="传输与会话" :bordered="false" class="section">
        <NDescriptions v-if="transport" :column="1" label-placement="left" size="small">
          <NDescriptionsItem label="HTTP">
            <code class="mono">{{ transport.api_base }}</code>
          </NDescriptionsItem>
          <NDescriptionsItem label="Python WS">
            <code class="mono">{{ transport.session_ws }}</code>
          </NDescriptionsItem>
          <NDescriptionsItem label="Rust AHE WS">
            <code class="mono">{{ aheServerApiBase().replace(/^http/, 'ws') }}/session/ws</code>
          </NDescriptionsItem>
          <NDescriptionsItem label="载荷加密">
            <NTag size="small" type="success">{{ transport.payload_encryption ?? "ahe" }}</NTag>
          </NDescriptionsItem>
        </NDescriptions>
      </NCard>

      <NCard size="small" title="推理用量" :bordered="false" class="section">
        <NDescriptions v-if="metrics" :column="2" label-placement="left" size="small">
          <NDescriptionsItem label="累计推理">{{ metrics.total_inferences }}</NDescriptionsItem>
          <NDescriptionsItem label="近 7 日">{{ metrics.delta_7d }}</NDescriptionsItem>
          <NDescriptionsItem label="同态加">
            {{ metrics.usage.pt_add_total.toLocaleString() }}
          </NDescriptionsItem>
          <NDescriptionsItem label="同态乘">
            {{ metrics.usage.pt_mult_total.toLocaleString() }}
          </NDescriptionsItem>
        </NDescriptions>
        <p v-else class="muted">暂无用量统计</p>
      </NCard>

      <InferenceMetricsCharts :metrics="metrics" :loading="loading" />
    </NSpin>
  </PageCard>
</template>

<style scoped>
.section {
  margin-bottom: var(--space-4);
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
}

.page-subtitle {
  margin-bottom: var(--space-4);
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}

.mono {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
}

.muted {
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}
</style>
