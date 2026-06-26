<script setup>
import { ref, computed } from "vue";
import { NInput, NButton, NSpace, NTag } from "naive-ui";
import { mockLogs } from "../../mocks/tasks.js";

const props = defineProps({
  logs: { type: String, default: () => mockLogs },
});

const keyword = ref("");

const lines = computed(() => props.logs.split("\n"));

const filtered = computed(() => {
  const kw = keyword.value.trim().toLowerCase();
  if (!kw) return lines.value;
  return lines.value.filter((line) => line.toLowerCase().includes(kw));
});

function downloadLogs() {
  const blob = new Blob([props.logs], { type: "text/plain;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "vpin-session.log";
  a.click();
  URL.revokeObjectURL(a.href);
}
</script>

<template>
  <div class="log-panel">
    <div class="log-panel__toolbar">
      <NTag size="small" type="warning" :bordered="false">占位 · 后续对接 WSS/会话日志 API</NTag>
      <NSpace>
        <NInput v-model:value="keyword" size="small" placeholder="查找日志" clearable style="width: 200px" />
        <NButton size="small" secondary @click="downloadLogs">下载</NButton>
      </NSpace>
    </div>
    <pre class="log-panel__body"><code><span
      v-for="(line, i) in filtered"
      :key="i"
      class="log-line"
    ><span class="ln">{{ i + 1 }}</span>{{ line }}
</span></code></pre>
  </div>
</template>

<style scoped>
.log-panel {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  overflow: hidden;
  background: #fafbfc;
}

.log-panel__toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-3);
  border-bottom: 1px solid var(--color-border);
  background: var(--color-surface);
  flex-wrap: wrap;
  gap: var(--space-2);
}

.log-panel__body {
  margin: 0;
  max-height: 360px;
  overflow: auto;
  padding: var(--space-3) 0;
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.55;
  color: var(--color-text-primary);
}

.log-line {
  display: block;
  padding: 0 var(--space-4);
}

.log-line:hover {
  background: rgba(37, 99, 235, 0.06);
}

.ln {
  display: inline-block;
  width: 2.5em;
  margin-right: var(--space-3);
  color: var(--color-text-muted);
  user-select: none;
  text-align: right;
}
</style>
