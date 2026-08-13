<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useMessage } from "naive-ui";
import { getBridge } from "@/bridge/client";
import type { InferenceEvent, RunRecord } from "@/bridge/types";
import PageCard from "@/components/PageCard.vue";
import InferenceTimeline from "@/components/inference/InferenceTimeline.vue";
import BatchProgressHeader from "@/components/inference/BatchProgressHeader.vue";
import BatchResultSummary from "@/components/inference/BatchResultSummary.vue";
import ComputationProofPanel from "@/components/security/ComputationProofPanel.vue";
import { driveComputationProof } from "@/bridge/proofDriver";
import type { TimelineStep } from "@/components/inference/InferenceTimeline.vue";
import { AHE_PHASE_WEIGHTS } from "@/demo/demoTiming";
import { inferenceEngineLabel, linkStatusLabel } from "@/utils/productLabels";

const route = useRoute();
const router = useRouter();
const message = useMessage();
const run = ref<RunRecord | null>(null);
const running = ref(false);
const steps = ref<TimelineStep[]>([]);
const activePhaseIndex = ref(0);
const batchCompleted = ref(0);

const runId = computed(() => String(route.params.id));
const isBatch = computed(() => (run.value?.config.batch_size ?? 1) > 1);
const showAccuracy = computed(
  () => isBatch.value && run.value?.status === "completed" && run.value.display_accuracy != null,
);

const engineLabel = computed(() => {
  if (!run.value) return "Network A";
  if (run.value.inference_engine === "rust-ec") return "Network A · EC :8002";
  if (run.value.inference_engine === "rust-ark") return "Network A · Arkworks :8001";
  const re = run.value.config.rust_engine;
  if (re === "rust-ec") return "Network A · EC :8002";
  if (re === "rust-ark") return "Network A · Arkworks :8001";
  return inferenceEngineLabel(run.value.inference_engine);
});

let unsub: (() => void) | undefined;
let pollTimer: ReturnType<typeof setInterval> | undefined;

function phaseIndex(phaseId?: string): number {
  if (!phaseId) return 0;
  return AHE_PHASE_WEIGHTS.findIndex((p) => p.phase_id === phaseId);
}

function onInferenceEvent(ev: InferenceEvent) {
  if (ev.run_id !== runId.value) return;
  if (ev.event === "phase_started" && ev.phase_id) {
    running.value = true;
    activePhaseIndex.value = phaseIndex(ev.phase_id);
    const label = AHE_PHASE_WEIGHTS.find((p) => p.phase_id === ev.phase_id)?.label ?? ev.phase_id;
    steps.value.push({
      id: `${ev.phase_id}-${Date.now()}`,
      phase_id: ev.phase_id,
      title: label,
      category: "P3",
      summary: ev.message ?? "阶段开始",
      at: new Date().toLocaleTimeString(),
      status: "active",
    });
  }
  if (ev.event === "phase_completed" && ev.phase_id) {
    const last = [...steps.value].reverse().find((s) => s.phase_id === ev.phase_id && s.status === "active");
    if (last) {
      last.status = "done";
      last.elapsed_ms = ev.elapsed_ms;
    }
  }
  if (ev.event === "batch_progress") {
    batchCompleted.value = ev.batch_index ?? 0;
  }
  if (ev.event === "run_completed") {
    running.value = false;
    void refreshRun();
  }
  if (ev.event === "run_failed") {
    running.value = false;
    message.error(ev.message ?? "推理失败");
    void refreshRun();
  }
  if (
    (ev.event === "proof_progress" || ev.event === "proof_completed" || ev.event === "proof_failed") &&
    ev.proof &&
    run.value
  ) {
    run.value.computation_proof = { ...ev.proof };
  }
  if (ev.event === "proof_completed") {
    message.success("计算量证明完成");
    void refreshRun();
  }
  if (ev.event === "proof_failed") {
    message.warning(ev.message ?? "计算量证明失败");
    void refreshRun();
  }
}

async function refreshRun() {
  const res = await getBridge().bridgeRunGet(runId.value);
  if (res.ok && res.data) run.value = res.data;
}

async function retryProof() {
  if (!run.value) return;
  await driveComputationProof(run.value);
  await refreshRun();
}

async function startRun() {
  const res = await getBridge().bridgeRunStart(runId.value);
  if (!res.ok) {
    message.error(res.error?.message ?? "启动失败");
    return;
  }
  run.value = res.data ?? run.value;
  steps.value = [];
  running.value = true;
}

onMounted(async () => {
  await refreshRun();
  unsub = getBridge().subscribeInference(onInferenceEvent);
  pollTimer = setInterval(refreshRun, 2000);
});

onUnmounted(() => {
  unsub?.();
  if (pollTimer) clearInterval(pollTimer);
});
</script>

<template>
  <div v-if="run">
    <PageCard>
      <div class="head">
      <div>
        <h1 class="page-title">运行现场</h1>
        <div class="mono sub">{{ run.run_id }} · {{ run.config.model_id }} · batch {{ run.config.batch_size }}</div>
      </div>
      <n-space>
        <n-tag>{{ run.status }}</n-tag>
        <n-button
          type="primary"
          :disabled="run.status === 'running' || run.status === 'completed'"
          :loading="running"
          @click="startRun"
        >
          启动推理
        </n-button>
        <n-button v-if="run.status === 'completed'" @click="router.push(`/verification/${run.run_id}`)">
          验证报告
        </n-button>
      </n-space>
    </div>

    <BatchProgressHeader
      v-if="isBatch"
      :completed="batchCompleted || run.batch_completed || 0"
      :total="run.config.batch_size"
      :running="running"
      :active-phase-index="activePhaseIndex"
    />

    <n-card size="small" title="P3 密态推理时间线" style="margin-top: 12px" :bordered="false" class="inner-card">
      <InferenceTimeline
        :steps="steps"
        :running="running"
        :running-phase="activePhaseIndex + 1"
        :engine-label="engineLabel"
      />
    </n-card>

    <BatchResultSummary
      v-if="showAccuracy"
      style="margin-top: 12px"
      :display-accuracy="run.display_accuracy"
      :correct-count="run.correct_count"
      :wrong-count="run.wrong_count"
      :total="run.config.batch_size"
    />

        <ComputationProofPanel
      :model-id="run.config.model_id"
      :batch-size="run.config.batch_size"
      :proof="run.computation_proof"
      @retry="retryProof"
    />
    </PageCard>
  </div>
  <n-spin v-else />
</template>

<style scoped>
.head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: var(--space-4);
}

.sub {
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
  margin-top: 4px;
}

.inner-card {
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
}
</style>
