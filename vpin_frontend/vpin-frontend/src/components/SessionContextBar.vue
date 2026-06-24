<script setup>
import { NTag, NButton, NTooltip, useMessage } from "naive-ui";
import { useProtocolSession } from "../composables/useProtocolSession.js";

const message = useMessage();
const { state, connectionLabel } = useProtocolSession();

function copySessionId() {
  const text = state.sessionId || "—";
  if (text === "—") {
    message.info("尚无活跃会话");
    return;
  }
  navigator.clipboard.writeText(text).then(() => {
    message.success("已复制 session_id");
  });
}

function truncateHash(value, head = 8, tail = 6) {
  if (!value) return "—";
  if (value.length <= head + tail + 3) return value;
  return `${value.slice(0, head)}…${value.slice(-tail)}`;
}
</script>

<template>
  <div class="session-bar">
    <div class="session-bar__row">
      <div class="session-bar__item">
        <span class="label">会话</span>
        <code class="mono">{{ state.sessionId || "—" }}</code>
        <NButton size="tiny" quaternary @click="copySessionId">复制</NButton>
      </div>
      <div class="session-bar__item">
        <span class="label">模型</span>
        <span>{{ state.modelName || "未绑定" }}</span>
        <NTooltip v-if="state.modelCmW" trigger="hover">
          <template #trigger>
            <code class="mono cmw">{{ truncateHash(state.modelCmW) }}</code>
          </template>
          cm_W: {{ state.modelCmW }}
        </NTooltip>
      </div>
      <div class="session-bar__item">
        <span class="label">AHE 曲线</span>
        <code class="mono">{{ state.aheCurveId }}</code>
      </div>
      <div class="session-bar__item">
        <span class="label">后端</span>
        <span
          class="status-dot"
          :class="state.connectionStatus"
          :title="connectionLabel"
        />
        <code class="mono backend">{{ state.backendUrl }}</code>
      </div>
    </div>
    <div class="session-bar__badges">
      <NTag size="small" :type="state.aheReady ? 'success' : 'default'" round>
        AHE {{ state.aheReady ? "已就绪" : "未 Setup" }}
      </NTag>
      <NTag size="small" :type="state.precomputeReady ? 'success' : 'warning'" round>
        预计算表 {{ state.precomputeReady ? "已生成" : "待生成" }}
      </NTag>
      <NTag size="small" :type="state.cpSnarkEnabled ? 'info' : 'default'" round>
        CP-SNARK {{ state.cpSnarkEnabled ? "已启用" : "未启用" }}
      </NTag>
      <NTag v-if="state.verifyStatus === 'passed'" size="small" type="success" round>
        Verify 通过
      </NTag>
      <NTag v-else-if="state.verifyStatus === 'failed'" size="small" type="error" round>
        Verify 失败
      </NTag>
      <NTag size="small" type="warning" round :bordered="false">演示 Mock</NTag>
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
  color: var(--color-text-primary);
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

.cmw {
  color: var(--color-primary);
}

.backend {
  max-width: 180px;
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

.status-dot.disconnected {
  background: var(--color-text-muted);
}

.status-dot.connecting {
  background: var(--color-warning);
}

.status-dot.connected {
  background: var(--color-success);
}

.session-bar__badges {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}
</style>
