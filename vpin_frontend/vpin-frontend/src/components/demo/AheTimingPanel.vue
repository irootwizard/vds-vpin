<template>
  <div v-if="timing" class="timing-panel">
    <n-text depth="3" style="font-size: 12px; display: block; margin-bottom: 8px">
      耗时分解 · {{ engineLabel }}
    </n-text>
    <div class="timing-bars">
      <div v-for="row in rows" :key="row.key" class="timing-row">
        <span class="timing-label">{{ row.label }}</span>
        <n-progress
          type="line"
          :percentage="row.pct"
          :height="8"
          :show-indicator="false"
          :color="row.color"
        />
        <span class="timing-ms">{{ row.ms.toFixed(0) }} ms</span>
      </div>
    </div>
    <n-text depth="3" style="font-size: 12px; margin-top: 6px">
      端到端 total: <strong>{{ totalMs.toFixed(0) }} ms</strong>
      <span v-if="timing.crypto_infer_ms != null">
        · crypto_infer: {{ timing.crypto_infer_ms.toFixed(0) }} ms
      </span>
    </n-text>
  </div>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  timing: { type: Object, default: null },
  engineLabel: { type: String, default: "" },
});

const totalMs = computed(() => {
  const t = props.timing;
  if (!t) return 0;
  return t.total_ms ?? t.crypto_infer_ms ?? 0;
});

const rows = computed(() => {
  const t = props.timing;
  if (!t) return [];
  const total = totalMs.value || 1;
  const candidates = [
    { key: "preprocess_ms", label: "预处理", color: "#8c8c8c" },
    { key: "encrypt_ms", label: "加密", color: "#2080f0" },
    { key: "decrypt_ms", label: "解密 (BSGS)", color: "#f0a020" },
    { key: "server_wait_ms", label: "服务端同态", color: "#18a058" },
    { key: "ws_ms", label: "WebSocket", color: "#722ed1" },
  ];
  return candidates
    .map((c) => ({
      ...c,
      ms: t[c.key] ?? 0,
      pct: Math.min(100, ((t[c.key] ?? 0) / total) * 100),
    }))
    .filter((r) => r.ms > 0);
});
</script>

<style scoped>
.timing-panel {
  margin-top: 8px;
  padding: 10px 12px;
  background: #fafafa;
  border-radius: 8px;
  border: 1px solid #eee;
}

.timing-row {
  display: grid;
  grid-template-columns: 72px 1fr 56px;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.timing-label {
  font-size: 12px;
  color: #666;
}

.timing-ms {
  font-size: 11px;
  color: #888;
  text-align: right;
  font-variant-numeric: tabular-nums;
}
</style>
