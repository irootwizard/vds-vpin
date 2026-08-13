<script setup>
import { onMounted, ref } from "vue";
import TransportStatusCard from "../components/security/TransportStatusCard.vue";
import InferenceUsageSummaryCard from "../components/security/InferenceUsageSummaryCard.vue";
import ComputationProofCard from "../components/security/ComputationProofCard.vue";
import InferenceMetricsCharts from "../components/security/InferenceMetricsCharts.vue";
import {
  fetchSecurityTransport,
  fetchInferenceMetrics,
  fetchComputationProof,
} from "../services/securityApi.js";

const loading = ref(true);
const transport = ref(null);
const metrics = ref(null);
const proof = ref(null);
const metricsMock = ref(false);

onMounted(async () => {
  loading.value = true;
  const [t, m, p] = await Promise.all([
    fetchSecurityTransport(),
    fetchInferenceMetrics(),
    fetchComputationProof(),
  ]);
  transport.value = t.data;
  metrics.value = m.data;
  metricsMock.value = m.mock;
  proof.value = p.data;
  loading.value = false;
});
</script>

<template>
  <div class="security-center">
    <header class="page-header">
      <div>
        <h1>安全中心</h1>
        <p>通信与推理用量监控</p>
      </div>
    </header>

    <div class="status-grid">
      <TransportStatusCard :transport="transport" :loading="loading" />
      <InferenceUsageSummaryCard :metrics="metrics" :loading="loading" :mock="metricsMock" />
      <ComputationProofCard :proof="proof" :loading="loading" />
    </div>

    <InferenceMetricsCharts :metrics="metrics" :loading="loading" :mock="metricsMock" />
  </div>
</template>

<style scoped>
.security-center {
  padding-bottom: var(--space-6);
}

.page-header {
  margin-bottom: var(--space-5);
}

.page-header h1 {
  font-size: 22px;
  font-weight: 700;
  margin: 0 0 4px;
  color: var(--color-text-primary);
}

.page-header p {
  margin: 0;
  font-size: 14px;
  color: var(--color-text-secondary);
}

.status-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--space-4);
}

@media (max-width: 1024px) {
  .status-grid {
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  }
}
</style>
