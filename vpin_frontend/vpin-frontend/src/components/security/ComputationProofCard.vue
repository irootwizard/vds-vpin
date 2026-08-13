<script setup>
import { computed } from "vue";
import { useRouter } from "vue-router";
import { NButton, NTag, NSkeleton, NIcon } from "naive-ui";
import { CalculatorOutline } from "@vicons/ionicons5";

const props = defineProps({
  proof: { type: Object, default: null },
  loading: { type: Boolean, default: false },
});

const router = useRouter();

const lastVerified = computed(() => {
  if (!props.proof?.last_verified_at) return "—";
  return props.proof.last_verified_at;
});

const statusTag = computed(() => {
  const s = props.proof?.status;
  if (s === "verified") return { type: "success", label: "已校验" };
  if (s === "failed") return { type: "error", label: "校验失败" };
  return { type: "default", label: "待接入" };
});

function openReport() {
  router.push("/security/verification");
}
</script>

<template>
  <div class="status-card info">
    <div class="status-icon">
      <NIcon :size="22" color="#1890ff"><CalculatorOutline /></NIcon>
    </div>
    <div class="status-content">
      <h3>计算量证明校验</h3>
      <NSkeleton v-if="loading" text :repeat="3" />
      <template v-else>
        <p>{{ proof?.message || "待接入 server-crypto / CP-SNARK 校验流程" }}</p>
        <div class="status-details">
          <span class="detail-item">
            <NTag size="small" :type="statusTag.type" :bordered="false">{{ statusTag.label }}</NTag>
            最近一次校验：{{ lastVerified }}
          </span>
          <span v-if="proof?.coverage" class="detail-item">证明覆盖：{{ proof.coverage }}</span>
          <NButton text type="primary" size="small" @click="openReport">查看报告</NButton>
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
  border-left: 4px solid #1890ff;
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
  background: rgba(24, 144, 255, 0.1);
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

.detail-item {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
</style>
