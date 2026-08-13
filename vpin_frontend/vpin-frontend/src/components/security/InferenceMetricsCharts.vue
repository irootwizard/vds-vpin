<script setup>
import { computed } from "vue";
import { Line, Bar } from "vue-chartjs";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Title,
  Tooltip,
  Legend,
  Filler,
} from "chart.js";
import { NCard, NSkeleton, NTag } from "naive-ui";

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Title,
  Tooltip,
  Legend,
  Filler,
);

const props = defineProps({
  metrics: { type: Object, default: null },
  loading: { type: Boolean, default: false },
  mock: { type: Boolean, default: false },
});

const chartOptions = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { position: "bottom", labels: { boxWidth: 12, font: { size: 11 } } },
  },
  scales: {
    x: { grid: { display: false }, ticks: { font: { size: 10 }, maxRotation: 0 } },
    y: { beginAtZero: true, ticks: { font: { size: 10 } } },
  },
};

const labels = computed(() => props.metrics?.usage?.by_day?.map((d) => d.date.slice(5)) ?? []);

const inferencesChart = computed(() => ({
  labels: labels.value,
  datasets: [
    {
      label: "推理次数",
      data: props.metrics?.usage?.by_day?.map((d) => d.inferences) ?? [],
      borderColor: "#4f6ef7",
      backgroundColor: "rgba(79, 110, 247, 0.12)",
      fill: true,
      tension: 0.3,
    },
  ],
}));

const usageChart = computed(() => ({
  labels: labels.value,
  datasets: [
    {
      label: "pt_add",
      data: props.metrics?.usage?.by_day?.map((d) => d.pt_add) ?? [],
      backgroundColor: "rgba(82, 196, 26, 0.75)",
      stack: "usage",
    },
    {
      label: "pt_mult",
      data: props.metrics?.usage?.by_day?.map((d) => d.pt_mult) ?? [],
      backgroundColor: "rgba(24, 144, 255, 0.75)",
      stack: "usage",
    },
  ],
}));

const usageChartOptions = computed(() => ({
  ...chartOptions,
  scales: {
    ...chartOptions.scales,
    x: { ...chartOptions.scales.x, stacked: true },
    y: { ...chartOptions.scales.y, stacked: true },
  },
}));

const overheadChart = computed(() => ({
  labels: labels.value,
  datasets: [
    {
      label: "证明耗时 (ms)",
      data: props.metrics?.proof_overhead?.by_day?.map((d) => d.prove_ms) ?? [],
      borderColor: "#fa8c16",
      backgroundColor: "rgba(250, 140, 22, 0.15)",
      yAxisID: "y",
      tension: 0.3,
    },
    {
      label: "验证耗时 (ms)",
      data: props.metrics?.proof_overhead?.by_day?.map((d) => d.verify_ms) ?? [],
      borderColor: "#13c2c2",
      backgroundColor: "rgba(19, 194, 194, 0.15)",
      yAxisID: "y",
      tension: 0.3,
    },
  ],
}));

const overheadChartOptions = computed(() => ({
  ...chartOptions,
  scales: {
    x: chartOptions.scales.x,
    y: {
      type: "linear",
      position: "left",
      beginAtZero: true,
      title: { display: true, text: "ms", font: { size: 10 } },
      ticks: { font: { size: 10 } },
    },
  },
  plugins: {
    ...chartOptions.plugins,
  },
}));

const overheadSummary = computed(() => {
  const o = props.metrics?.proof_overhead;
  if (!o) return null;
  return {
    prove: o.prove_ms_avg,
    verify: o.verify_ms_avg,
    ratio: o.overhead_ratio,
  };
});
</script>

<template>
  <NCard class="charts-panel" :bordered="true">
    <template #header>
      <div class="panel-header">
        <span>推理用量与证明开销</span>
        <NTag v-if="mock" size="small" type="warning" :bordered="false">演示数据</NTag>
      </div>
    </template>

    <NSkeleton v-if="loading" height="280px" :sharp="false" />

    <template v-else-if="metrics">
      <div v-if="overheadSummary" class="overhead-stats">
        <span>证明均耗 {{ overheadSummary.prove }} ms</span>
        <span>验证均耗 {{ overheadSummary.verify }} ms</span>
        <span>开销倍率 {{ overheadSummary.ratio?.toFixed(2) }}×</span>
      </div>

      <div class="charts-grid">
        <div class="chart-box">
          <h4>总推理次数</h4>
          <div class="chart-canvas">
            <Line :data="inferencesChart" :options="chartOptions" />
          </div>
        </div>
        <div class="chart-box">
          <h4>推理用量 (pt_add / pt_mult)</h4>
          <div class="chart-canvas">
            <Bar :data="usageChart" :options="usageChartOptions" />
          </div>
        </div>
        <div class="chart-box">
          <h4>计算量证明开销</h4>
          <div class="chart-canvas">
            <Line :data="overheadChart" :options="overheadChartOptions" />
          </div>
        </div>
      </div>
    </template>
  </NCard>
</template>

<style scoped>
.charts-panel {
  margin-top: var(--space-5);
}

.panel-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
}

.overhead-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  font-size: 13px;
  color: var(--color-text-secondary);
  margin-bottom: 16px;
}

.charts-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
}

.chart-box h4 {
  font-size: 13px;
  font-weight: 600;
  margin: 0 0 8px;
  color: var(--color-text-primary);
}

.chart-canvas {
  height: 220px;
  position: relative;
}

@media (max-width: 960px) {
  .charts-grid {
    grid-template-columns: 1fr;
  }
}
</style>
