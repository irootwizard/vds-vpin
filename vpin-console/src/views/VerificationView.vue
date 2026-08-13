<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { NAlert, NCard, NDescriptions, NDescriptionsItem, NSpace, NTag } from "naive-ui";
import { getBridge } from "@/bridge/client";
import { driveComputationProof } from "@/bridge/proofDriver";
import type { RunRecord } from "@/bridge/types";
import ComputationProofPanel from "@/components/security/ComputationProofPanel.vue";
import PageCard from "@/components/PageCard.vue";
import { inferenceEngineLabel } from "@/utils/productLabels";

const route = useRoute();
const run = ref<RunRecord | null>(null);

const runId = computed(() => String(route.params.runId));
const isHomomorphic = computed(
  () =>
    run.value?.inference_engine === "rust-ark" ||
    run.value?.inference_engine === "rust-ec" ||
    run.value?.inference_engine === "timing-demo",
);
const engineDisplay = computed(() => inferenceEngineLabel(run.value?.inference_engine));
const inferPass = computed(() => run.value?.status === "completed");
const proofPass = computed(() => run.value?.computation_proof?.ok === true);

onMounted(async () => {
  const res = await getBridge().bridgeRunGet(runId.value);
  if (res.ok && res.data) run.value = res.data;
});

async function retryProof() {
  if (!run.value) return;
  await driveComputationProof(run.value);
  const res = await getBridge().bridgeRunGet(runId.value);
  if (res.ok && res.data) run.value = res.data;
}
</script>

<template>
  <PageCard>
    <h1 class="page-title">验证报告</h1>
    <p class="page-subtitle">P3 密态推理 · P4–P6 计算量证明（Network A）</p>

    <n-spin :show="!run">
      <NCard v-if="run" size="small" :bordered="false" class="section">
        <div class="head">
          <code class="mono">{{ run.run_id }}</code>
          <NSpace>
            <NTag :type="inferPass ? 'success' : run.status === 'failed' ? 'error' : 'default'">
              推理 {{ inferPass ? "PASS" : run.status.toUpperCase() }}
            </NTag>
            <NTag v-if="run.computation_proof?.enabled" :type="proofPass ? 'success' : 'default'">
              计算量 {{ proofPass ? "PASS" : run.computation_proof?.phase ?? "—" }}
            </NTag>
          </NSpace>
        </div>

        <NDescriptions :column="2" label-placement="left" size="small" style="margin-top: 12px">
          <NDescriptionsItem label="模型">{{ run.config.model_id }}</NDescriptionsItem>
          <NDescriptionsItem label="引擎">{{ engineDisplay }}</NDescriptionsItem>
          <NDescriptionsItem label="批量">{{ run.config.batch_size }}</NDescriptionsItem>
          <NDescriptionsItem label="推理耗时">
            {{ run.elapsed_ms != null ? `${(run.elapsed_ms / 1000).toFixed(1)}s` : "—" }}
          </NDescriptionsItem>
          <NDescriptionsItem v-if="run.prediction != null" label="预测">
            {{ run.prediction }}
          </NDescriptionsItem>
          <NDescriptionsItem v-if="run.label != null" label="标签">
            {{ run.label }}
          </NDescriptionsItem>
          <NDescriptionsItem v-if="run.display_accuracy != null" label="批量准确度">
            {{ (run.display_accuracy * 100).toFixed(2) }}%
            ({{ run.correct_count }}/{{ run.config.batch_size }})
          </NDescriptionsItem>
        </NDescriptions>

        <NAlert v-if="isHomomorphic && inferPass" type="success" :bordered="false" style="margin-top: 12px">
          密态推理已完成；单图任务可对照 MNIST 标签复核预测结果。
        </NAlert>
        <NAlert v-else-if="run.status === 'failed'" type="error" :bordered="false" style="margin-top: 12px">
          推理未完成，无验证结论。
        </NAlert>
      </NCard>

      <ComputationProofPanel
        v-if="run"
        :model-id="run.config.model_id"
        :batch-size="run.config.batch_size"
        :proof="run.computation_proof"
        @retry="retryProof"
      />
    </n-spin>
  </PageCard>
</template>

<style scoped>
.section {
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-4);
}

.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}

.mono {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
}

.page-subtitle {
  margin-bottom: var(--space-4);
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}
</style>
