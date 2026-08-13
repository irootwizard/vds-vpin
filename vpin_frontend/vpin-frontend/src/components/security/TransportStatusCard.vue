<script setup>
import { computed } from "vue";
import { NTag, NSkeleton } from "naive-ui";
import { LockClosedOutline } from "@vicons/ionicons5";
import { NIcon } from "naive-ui";

const props = defineProps({
  transport: { type: Object, default: null },
  loading: { type: Boolean, default: false },
});

const transportLabel = computed(() => {
  if (!props.transport) return "—";
  const { http_scheme, ws_scheme } = props.transport;
  return `${http_scheme.toUpperCase()} / ${ws_scheme.toUpperCase()}${props.transport.tls_enabled ? "" : " 明文"}`;
});

const payloadLabel = computed(() => {
  const enc = props.transport?.payload_encryption;
  if (enc === "ahe_ciphertext") return "AHE 密文载荷";
  return enc || "—";
});
</script>

<template>
  <div class="status-card secure">
    <div class="status-icon">
      <NIcon :size="22" color="#52c41a"><LockClosedOutline /></NIcon>
    </div>
    <div class="status-content">
      <h3>加密通信</h3>
      <NSkeleton v-if="loading" text :repeat="3" />
      <template v-else-if="transport">
        <p>{{ transport.tls_enabled ? "端到端 TLS 加密" : "开发环境明文传输（HTTP / WS）" }}</p>
        <div class="status-details">
          <span class="detail-item">
            <NTag size="small" :type="transport.tls_enabled ? 'success' : 'warning'" :bordered="false">
              传输层：{{ transportLabel }}
            </NTag>
          </span>
          <span class="detail-item detail-mono">API：{{ transport.api_base }}</span>
          <span class="detail-item detail-mono">会话：{{ transport.session_ws }}</span>
          <span class="detail-item">
            <NTag size="small" type="info" :bordered="false">{{ payloadLabel }}</NTag>
          </span>
          <template v-if="transport.tls_enabled && transport.certificate">
            <span class="detail-item">
              证书：{{ transport.certificate.subject }}
              <NTag
                size="tiny"
                :type="transport.certificate.verified ? 'success' : 'error'"
                :bordered="false"
              >
                {{ transport.certificate.verified ? "校验通过" : "校验失败" }}
              </NTag>
            </span>
            <span class="detail-item">颁发者：{{ transport.certificate.issuer }}</span>
            <span class="detail-item">
              有效期：{{ transport.certificate.valid_from }} — {{ transport.certificate.valid_to }}
            </span>
            <span v-if="transport.forward_secrecy" class="detail-item">前向保密：已启用</span>
          </template>
          <span v-else class="detail-item">
            <NTag size="small" :bordered="false">证书：未配置</NTag>
          </span>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.status-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--space-5);
  border-left: 4px solid #52c41a;
  height: 100%;
}

.status-icon {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: var(--space-3);
  background: rgba(82, 196, 26, 0.1);
}

.status-content h3 {
  font-size: 16px;
  font-weight: 600;
  margin: 0 0 6px;
}

.status-content p {
  color: var(--color-text-secondary);
  font-size: 14px;
  margin: 0 0 12px;
}

.status-details {
  display: flex;
  flex-direction: column;
  gap: 8px;
  font-size: 13px;
  color: var(--color-text-secondary);
}

.detail-mono {
  font-family: ui-monospace, monospace;
  font-size: 12px;
  word-break: break-all;
}
</style>
