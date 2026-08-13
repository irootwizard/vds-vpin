<script setup lang="ts">
import { computed, ref } from "vue";
import { useMessage } from "naive-ui";
import {
  NAlert,
  NButton,
  NCard,
  NCollapse,
  NCollapseItem,
  NDescriptions,
  NDescriptionsItem,
  NInput,
  NProgress,
  NSpace,
  NStep,
  NSteps,
  NTag,
  NTooltip,
} from "naive-ui";
import type { ComputationProofState } from "@/bridge/types";
import { supportsComputationProof } from "@/config/networkAProof";
import { saveProofToPath } from "@/services/proofClient";

const props = defineProps<{
  modelId: string;
  batchSize: number;
  proof?: ComputationProofState;
}>();

const emit = defineEmits<{
  retry: [];
  verify: [];
}>();

const message = useMessage();
const savePath = ref("");
const verifying = ref(false);
const saving = ref(false);

const eligible = computed(() =>
  supportsComputationProof(props.modelId) && props.batchSize === 1,
);

const stepIndex = computed(() => {
  const p = props.proof?.phase;
  if (!p || p === "idle" || p === "skipped") return 0;
  if (p === "plan") return 1;
  if (p === "challenge") return 2;
  if (p === "prove") return 3;
  if (p === "verify") return 4;
  if (p === "done") return 5;
  if (p === "failed") return 3;
  return 0;
});

const running = computed(() =>
  ["plan", "challenge", "prove", "verify"].includes(props.proof?.phase ?? ""),
);

const hasArtifact = computed(
  () => Boolean(props.proof?.artifact_path) || props.proof?.phase === "done",
);

const statusType = computed(() => {
  if (props.proof?.phase === "done" && props.proof.verify_ok) return "success";
  if (props.proof?.phase === "failed") return "error";
  if (running.value || verifying.value) return "info";
  return "default";
});

const coverageLabel = computed(() => {
  const c = props.proof?.proof_coverage ?? "";
  if (!c) return "—";
  return c.replace(/_/g, " ");
});

const defaultSavePath = computed(() => {
  const name = `protocol-${props.modelId}-${Date.now()}.json`;
  return savePath.value || name;
});

async function onSave() {
  saving.value = true;
  try {
    const res = await saveProofToPath(
      savePath.value.trim() || defaultSavePath.value,
      props.proof?.artifact_path,
      "A",
    );
    if (res.ok) message.success(res.message);
    else message.error(res.message);
  } catch (e) {
    message.error(e instanceof Error ? e.message : String(e));
  } finally {
    saving.value = false;
  }
}

async function onVerify() {
  verifying.value = true;
  try {
    emit("verify");
  } finally {
    verifying.value = false;
  }
}
</script>

<template>
  <NCard
    v-if="eligible"
    size="small"
    :bordered="false"
    class="proof-card"
    title="计算量证明（CP-SNARK · Network A）"
  >
    <template #header-extra>
      <NSpace :size="8" align="center">
        <NTag size="small" type="warning">独立于 AHE</NTag>
        <NTag v-if="proof?.n2_eq_q1" size="small" type="success">n₂ = q₁</NTag>
        <NTag v-if="proof?.verify_ok" size="small" type="success">P6 已验证</NTag>
        <NTag v-else-if="proof?.phase === 'failed'" size="small" type="error">失败</NTag>
        <NTag v-else-if="running" size="small" type="info">证明中</NTag>
      </NSpace>
    </template>

    <p class="lead">
      P4 由<strong>客户端 CSPRNG</strong> 采样 γ / γ′（prove 前服务器不可见）；P5 生成
      <code>protocol.json</code>；可保存到本地并随时点击 Verify 复验。
    </p>

    <NSteps :current="stepIndex" size="small" style="margin: 16px 0">
      <NStep title="ProofPlan" description="178 PtMul / 2144 PtAdd" />
      <NStep title="P4 γ" description="客户端随机挑战" />
      <NStep title="P5 Prove" description="B′ + M1 + EC" />
      <NStep title="P6 Verify" description="verify-file / M1" />
      <NStep title="完成" />
    </NSteps>

    <NProgress
      v-if="running"
      type="line"
      :percentage="stepIndex * 20"
      :show-indicator="false"
      status="info"
      style="margin-bottom: 12px"
    />

    <NCollapse v-if="proof?.challenge" style="margin-bottom: 12px">
      <NCollapseItem title="P4 客户端挑战（完整 γ）" name="challenge">
        <NDescriptions :column="1" label-placement="left" size="small" bordered>
          <NDescriptionsItem label="γ (conv RLC)">
            <code class="mono break">{{ proof.challenge.gamma }}</code>
          </NDescriptionsItem>
          <NDescriptionsItem label="γ_add (PtAdd)">
            <code class="mono break">{{ proof.challenge.gamma_add }}</code>
          </NDescriptionsItem>
          <NDescriptionsItem label="γ′ / gamma_mult (FC RLC)">
            <code class="mono break">{{ proof.challenge.gamma_mult }}</code>
          </NDescriptionsItem>
          <NDescriptionsItem label="计数">
            PtAdd {{ proof.challenge.num_pt_add }} · PtMul {{ proof.challenge.num_pt_mult }}
          </NDescriptionsItem>
        </NDescriptions>
      </NCollapseItem>
    </NCollapse>

    <NCollapse v-if="proof?.cm_w_hex || proof?.cm_x_hex || proof?.cps_cm_hex" style="margin-bottom: 12px">
      <NCollapseItem title="承诺（Commitments）" name="commitments">
        <NDescriptions :column="1" label-placement="left" size="small" bordered>
          <NDescriptionsItem label="cm_W (Pedersen)">
            <code class="mono break">{{ proof.cm_w_hex || "—" }}</code>
          </NDescriptionsItem>
          <NDescriptionsItem v-if="proof.cm_w_digest_hex" label="cm_W digest">
            <code class="mono break">{{ proof.cm_w_digest_hex }}</code>
          </NDescriptionsItem>
          <NDescriptionsItem label="cm_x (输入)">
            <code class="mono break">{{ proof.cm_x_hex || "—" }}</code>
          </NDescriptionsItem>
          <NDescriptionsItem v-if="proof.cm_x_digest_hex" label="cm_x digest">
            <code class="mono break">{{ proof.cm_x_digest_hex }}</code>
          </NDescriptionsItem>
          <NDescriptionsItem label="CPS cm (Spartan PC · W*)">
            <code class="mono break">{{ proof.cps_cm_hex || "—" }}</code>
          </NDescriptionsItem>
        </NDescriptions>
      </NCollapseItem>
    </NCollapse>

    <NDescriptions
      v-if="proof && proof.phase !== 'idle'"
      :column="2"
      label-placement="left"
      size="small"
      bordered
    >
      <NDescriptionsItem label="覆盖">
        <NTooltip v-if="coverageLabel !== '—'">
          <template #trigger>
            <code class="mono">{{ coverageLabel }}</code>
          </template>
          {{ proof.proof_coverage }}
        </NTooltip>
        <span v-else>—</span>
      </NDescriptionsItem>
      <NDescriptionsItem label="N_W">{{ proof.n_w ?? 1219 }}</NDescriptionsItem>
      <NDescriptionsItem label="PtMul / PtAdd">
        {{ proof.total_pt_mul ?? "—" }} / {{ proof.total_pt_add ?? "—" }}
      </NDescriptionsItem>
      <NDescriptionsItem v-if="proof.prove_ms" label="prove 耗时">
        {{ (proof.prove_ms / 1000).toFixed(1) }}s
      </NDescriptionsItem>
      <NDescriptionsItem label="trace digest" :span="2">
        <code v-if="proof.scalar_trace_digest_hex" class="mono break">
          {{ proof.scalar_trace_digest_hex }}
        </code>
        <span v-else>—</span>
      </NDescriptionsItem>
      <NDescriptionsItem label="protocol.json" :span="2">
        <code v-if="proof.artifact_path" class="mono break">{{ proof.artifact_path }}</code>
        <span v-else>—</span>
      </NDescriptionsItem>
      <NDescriptionsItem v-if="proof.verify_message" label="P6 结果" :span="2">
        {{ proof.verify_message }}
      </NDescriptionsItem>
    </NDescriptions>

    <div v-if="hasArtifact" class="actions">
      <NInput
        v-model:value="savePath"
        size="small"
        :placeholder="`保存路径，如 D:\\proofs\\${defaultSavePath}`"
        clearable
      />
      <NSpace style="margin-top: 8px">
        <NButton size="small" type="primary" :loading="saving" @click="onSave">
          保存 proof 文件
        </NButton>
        <NButton size="small" :loading="verifying" @click="onVerify">
          手动 Verify (P6)
        </NButton>
        <NButton
          v-if="proof?.phase === 'failed'"
          size="small"
          @click="emit('retry')"
        >
          重试 Prove
        </NButton>
      </NSpace>
    </div>

    <NAlert
      v-if="proof?.message"
      :type="statusType === 'default' ? 'info' : statusType"
      :bordered="false"
      style="margin-top: 12px"
    >
      {{ proof.message }}
    </NAlert>
  </NCard>

  <NAlert v-else-if="supportsComputationProof(modelId) && batchSize > 1" type="info" :bordered="false">
    批量推理暂不自动串联计算量证明（单图 run 可展示完整 P4–P6）。
  </NAlert>
</template>

<style scoped>
.proof-card {
  margin-top: var(--space-4);
  background: linear-gradient(
    135deg,
    color-mix(in srgb, var(--color-primary) 6%, var(--color-bg)),
    var(--color-bg)
  );
  border: 1px solid color-mix(in srgb, var(--color-primary) 25%, var(--color-border));
  border-radius: var(--radius-md);
}

.lead {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  line-height: 1.5;
}

.mono {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
}

.break {
  word-break: break-all;
  white-space: pre-wrap;
}

.actions {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px dashed var(--color-border);
}
</style>
