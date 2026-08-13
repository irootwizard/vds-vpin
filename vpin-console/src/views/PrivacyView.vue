<script setup lang="ts">
import { onMounted, ref } from "vue";
import { NCard, NDescriptions, NDescriptionsItem, NTag } from "naive-ui";
import { loadLlmReceiptSnapshot, type LlmReceiptSnapshot } from "@/demo/llmReceiptStore";
import PageCard from "@/components/PageCard.vue";

const llmSnap = ref<LlmReceiptSnapshot | null>(null);

onMounted(() => {
  llmSnap.value = loadLlmReceiptSnapshot();
});
</script>

<template>
  <PageCard>
    <h1 class="page-title">隐私与策略</h1>
    <p class="page-subtitle">计算量承诺与审计策略</p>

    <n-card size="small" title="大模型计算量承诺" :bordered="false" class="section">
      <template v-if="llmSnap">
        <NTag type="success">verified · rational-audit</NTag>
        <NDescriptions :column="1" label-placement="left" size="small" style="margin-top: 12px">
          <NDescriptionsItem label="session">
            {{ llmSnap.receipt.session_id }}
          </NDescriptionsItem>
          <NDescriptionsItem label="model">
            {{ llmSnap.receipt.model_label }}
          </NDescriptionsItem>
          <NDescriptionsItem label="验证时间">
            {{ llmSnap.saved_at }}
          </NDescriptionsItem>
          <NDescriptionsItem label="verifier">
            {{ llmSnap.verify.verifier_ms }} ms · p_hit≈{{ llmSnap.verify.p_hit }}
          </NDescriptionsItem>
        </NDescriptions>
      </template>
      <p v-else class="muted">
        在「大模型推理」页完成一轮对话后，客户端将本地生成 receipt 并自动完成验证。
      </p>
    </n-card>

    <n-card size="small" title="CNN 密态推理" :bordered="false" class="section">
      <p class="muted">
        Network A 推理验证在任务驾驶舱与验证页查看；密态计算经 WebSocket 会话完成。
      </p>
    </n-card>
  </PageCard>
</template>

<style scoped>
.section {
  margin-bottom: var(--space-4);
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-2);
}

.page-subtitle {
  margin-bottom: var(--space-4);
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}

.muted {
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  line-height: 1.6;
}
</style>
