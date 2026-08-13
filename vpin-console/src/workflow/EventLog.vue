<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";
import { NInput, NButton, NSpace, NTag } from "naive-ui";
import type { EventLogEntry } from "@/bridge/types";
import { getBridge } from "@/bridge/client";

const logs = ref<EventLogEntry[]>([]);
const keyword = ref("");
let unsub: (() => void) | undefined;

const filtered = ref<EventLogEntry[]>([]);

function refreshFiltered() {
  const kw = keyword.value.trim().toLowerCase();
  filtered.value = kw
    ? logs.value.filter(
        (e) =>
          e.message.toLowerCase().includes(kw) ||
          e.channel.toLowerCase().includes(kw),
      )
    : logs.value;
}

onMounted(() => {
  unsub = getBridge().subscribeEventLog((e) => {
    logs.value = [e, ...logs.value].slice(0, 200);
    refreshFiltered();
  });
});

onUnmounted(() => unsub?.());

function onKeyword() {
  refreshFiltered();
}
</script>

<template>
  <div class="log-panel">
    <div class="log-panel__toolbar">
      <NTag size="small" type="info" :bordered="false">EventLog · Bridge 事件</NTag>
      <NSpace>
        <NInput
          v-model:value="keyword"
          size="small"
          placeholder="查找日志"
          clearable
          style="width: 200px"
          @update:value="onKeyword"
        />
        <NButton size="small" secondary disabled>下载</NButton>
      </NSpace>
    </div>
    <div class="log-panel__body">
      <div v-for="row in filtered" :key="row.id" class="log-line" :data-level="row.level">
        <span class="ln">{{ row.ts }}</span>
        <span class="ch mono">{{ row.channel }}</span>
        <span class="msg">{{ row.message }}</span>
      </div>
      <div v-if="!filtered.length" class="empty">等待 bridge 事件…</div>
    </div>
  </div>
</template>

<style scoped>
.log-panel {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  overflow: hidden;
  background: #fafbfc;
  flex: 0 0 140px;
  height: 140px;
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
  height: calc(140px - 52px);
  overflow: auto;
  padding: var(--space-2) 0;
  font-size: 12px;
}

.log-line {
  display: grid;
  grid-template-columns: 90px 180px 1fr;
  gap: 8px;
  padding: 2px var(--space-4);
  align-items: baseline;
}

.log-line:hover {
  background: rgba(37, 99, 235, 0.06);
}

.log-line[data-level="success"] .msg {
  color: var(--color-success);
}

.log-line[data-level="warn"] .msg {
  color: var(--color-warning);
}

.log-line[data-level="error"] .msg {
  color: var(--color-error);
}

.ln {
  color: var(--color-text-muted);
  font-family: var(--font-mono);
  font-size: 11px;
}

.ch {
  color: var(--color-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.msg {
  color: var(--color-text-primary);
}

.empty {
  padding: var(--space-3) var(--space-4);
  color: var(--color-text-muted);
  font-size: var(--text-sm);
}
</style>
