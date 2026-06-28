<template>
  <div class="batch-report">
    <n-descriptions bordered size="small" :column="3">
      <n-descriptions-item label="样本数">{{ report.limit ?? report.total ?? "—" }}</n-descriptions-item>
      <n-descriptions-item label="正确数">{{ report.correct ?? "—" }}</n-descriptions-item>
      <n-descriptions-item label="准确率">
        {{ report.accuracy != null ? `${(report.accuracy * 100).toFixed(2)}%` : "—" }}
      </n-descriptions-item>
      <n-descriptions-item label="总耗时">
        {{ report.elapsed_s != null ? `${report.elapsed_s.toFixed(2)} s` : "—" }}
      </n-descriptions-item>
      <n-descriptions-item label="吞吐">
        {{
          report.elapsed_s > 0 && report.limit
            ? `${(report.limit / report.elapsed_s).toFixed(2)} img/s`
            : "—"
        }}
      </n-descriptions-item>
      <n-descriptions-item label="并发">{{ report.concurrency ?? "—" }}</n-descriptions-item>
    </n-descriptions>

    <n-alert
      v-if="report.errors?.length"
      type="warning"
      style="margin-top: 12px"
      :title="`${report.errors.length} 项失败`"
    >
      <ul class="err-list">
        <li v-for="(e, i) in report.errors" :key="i">{{ e.job_id }}: {{ e.error }}</li>
      </ul>
    </n-alert>

    <n-space style="margin-top: 12px">
      <n-button size="small" @click="exportJson">导出 JSON</n-button>
    </n-space>
  </div>
</template>

<script setup>
const props = defineProps({
  report: { type: Object, required: true },
});

function exportJson() {
  const blob = new Blob([JSON.stringify(props.report, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `ahe_batch_${Date.now()}.json`;
  a.click();
  URL.revokeObjectURL(url);
}
</script>

<style scoped>
.err-list {
  margin: 0;
  padding-left: 18px;
  font-size: 12px;
}
</style>
