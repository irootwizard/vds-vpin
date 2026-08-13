<script setup lang="ts">
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
import { NCard, NSkeleton } from "naive-ui";
import type { InferenceMetrics } from "@/services/securityApi";

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

const props = defineProps<{
  metrics: InferenceMetrics | null;
  loading?: boolean;
}>();

const chartOptions = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { position: "bottom" as const, labels: { boxWidth: 12, font: { size: 11 } } },
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
      label: "同态加",
      data: props.metrics?.usage?.by_day?.map((d) => d.pt_add) ?? [],
      backgroundColor: "rgba(82, 196, 26, 0.75)",
      stack: "usage",
    },
    {
      label: "同态乘",
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
</script>

<template>
  <NCard size="small" title="推理用量趋势" :bordered="false" class="charts-panel">
    <NSkeleton v-if="loading" height="220px" :sharp="false" />
    <template v-else-if="metrics">
      <div class="charts-grid">
        <div class="chart-box">
          <h4>总推理次数</h4>
          <div class="chart-canvas">
            <Line :data="inferencesChart" :options="chartOptions" />
          </div>
        </div>
        <div class="chart-box">
          <h4>同态算子用量</h4>
          <div class="chart-canvas">
            <Bar :data="usageChart" :options="usageChartOptions" />
          </div>
        </div>
      </div>
    </template>
    <p v-else class="muted">暂无趋势数据</p>
  </NCard>
</template>

<style scoped>
.charts-panel {
  margin-top: var(--space-4);
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
}

.charts-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 20px;
}

.chart-box h4 {
  font-size: 13px;
  font-weight: 600;
  margin: 0 0 8px;
}

.chart-canvas {
  height: 220px;
  position: relative;
}

.muted {
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}

@media (max-width: 960px) {
  .charts-grid {
    grid-template-columns: 1fr;
  }
}
</style>
