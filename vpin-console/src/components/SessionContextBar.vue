<script setup lang="ts">
import { NTag } from "naive-ui";
import type { LinkStatus } from "@/services/backendApi";
import { linkStatusLabel } from "@/utils/productLabels";

defineProps<{
  sessionId?: string;
  backendUrl?: string;
  aheUrl?: string;
  backendStatus?: LinkStatus;
  aheStatus?: LinkStatus;
  bridgeReady?: boolean;
  runId?: string;
}>();

function dotClass(status?: LinkStatus) {
  if (status === "connected" || status === "standalone") return "connected";
  if (status === "disconnected") return "disconnected";
  return "checking";
}
</script>

<template>
  <div class="session-bar">
    <div class="session-bar__row">
      <div class="session-bar__item">
        <span class="label">会话</span>
        <code class="mono">{{ runId || sessionId || "—" }}</code>
      </div>
      <div class="session-bar__item">
        <span class="label">Backend</span>
        <span class="status-dot" :class="dotClass(backendStatus)" />
        <code class="mono backend">{{ backendUrl || "—" }}</code>
      </div>
      <div class="session-bar__item">
        <span class="label">AHE</span>
        <span class="status-dot" :class="dotClass(aheStatus)" />
        <code class="mono backend">{{ aheUrl || "—" }}</code>
      </div>
      <div class="session-bar__item">
        <span class="label">Bridge</span>
        <span class="status-dot" :class="bridgeReady ? 'connected' : 'checking'" />
        <code class="mono">Client Bridge</code>
      </div>
    </div>
    <div class="session-bar__badges">
      <NTag
        size="small"
        :type="
          backendStatus === 'connected' || backendStatus === 'standalone'
            ? 'success'
            : backendStatus === 'disconnected'
              ? 'warning'
              : 'default'
        "
        round
      >
        Backend {{ linkStatusLabel(backendStatus, "backend") }}
      </NTag>
      <NTag
        size="small"
        :type="
          aheStatus === 'connected'
            ? 'success'
            : aheStatus === 'disconnected'
              ? 'error'
              : 'default'
        "
        round
      >
        ahe-server {{ linkStatusLabel(aheStatus, "ahe") }}
      </NTag>
      <NTag size="small" :type="bridgeReady ? 'success' : 'default'" round>
        Bridge {{ bridgeReady ? "就绪" : "初始化" }}
      </NTag>
    </div>
  </div>
</template>

<style scoped>
.session-bar {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--space-3) var(--space-4);
  margin-bottom: var(--space-3);
  box-shadow: var(--shadow-sm);
}

.session-bar__row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-4) var(--space-5);
  align-items: center;
  margin-bottom: var(--space-2);
}

.session-bar__item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-sm);
}

.label {
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
  min-width: 3em;
}

.mono {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  background: var(--color-bg);
  padding: 2px 6px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-border);
}

.backend {
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.status-dot.connected {
  background: var(--color-success);
}

.status-dot.disconnected {
  background: var(--color-error);
}

.status-dot.checking {
  background: var(--color-warning);
}

.session-bar__badges {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: center;
}
</style>
