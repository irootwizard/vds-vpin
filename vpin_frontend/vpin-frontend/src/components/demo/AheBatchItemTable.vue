<template>
  <n-data-table
    :columns="columns"
    :data="items"
    :row-key="(row) => row.jobId"
    size="small"
    :max-height="360"
    :virtual-scroll="items.length > 80"
    :row-props="rowProps"
  />
</template>

<script setup>
import { h } from "vue";
import { NTag } from "naive-ui";

const props = defineProps({
  items: { type: Array, default: () => [] },
  focusJobId: { type: String, default: null },
});

const emit = defineEmits(["focus"]);

function statusTag(row) {
  const map = {
    pending: { type: "default", label: "等待" },
    running: { type: "info", label: "运行中" },
    done: { type: "success", label: "完成" },
    error: { type: "error", label: "失败" },
  };
  const s = map[row.status] || map.pending;
  return h(NTag, { size: "tiny", type: s.type }, () => s.label);
}

const columns = [
  {
    title: "Job",
    key: "jobId",
    ellipsis: { tooltip: true },
    width: 120,
  },
  {
    title: "序号",
    key: "mnistIndex",
    width: 72,
    render: (row) => (row.mnistIndex != null ? `#${row.mnistIndex}` : row.uploadId?.slice(0, 8) || "—"),
  },
  {
    title: "标签",
    key: "label",
    width: 56,
    render: (row) => (row.label != null ? row.label : "—"),
  },
  {
    title: "预测",
    key: "prediction",
    width: 56,
    render: (row) => (row.prediction != null ? row.prediction : "—"),
  },
  {
    title: "耗时",
    key: "timing",
    width: 88,
    render: (row) => {
      const ms = row.timing?.total_ms ?? row.timing?.crypto_infer_ms;
      return ms != null ? `${ms.toFixed(0)} ms` : "—";
    },
  },
  {
    title: "状态",
    key: "status",
    width: 72,
    render: (row) => statusTag(row),
  },
];

function rowProps(row) {
  return {
    style: row.jobId === props.focusJobId ? "background: #f0faf4; cursor: pointer" : "cursor: pointer",
    onClick: () => emit("focus", row),
  };
}
</script>
