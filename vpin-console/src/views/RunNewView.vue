<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useMessage } from "naive-ui";
import {
  NButton,
  NSteps,
  NStep,
  NCard,
  NForm,
  NFormItem,
  NRadioGroup,
  NRadio,
  NSelect,
  NSpace,
  NTag,
  NAlert,
} from "naive-ui";
import { getBridge } from "@/bridge/client";
import { modelSelectLabel, resolveInferencePlan } from "@/config/modelCatalog";
import { evaluateHomomorphicFeasibility } from "@/config/homomorphicGovernance";
import {
  loadSavedNetworkAEngine,
  NETWORK_A_RUST_ENGINES,
  saveNetworkAEngine,
  type NetworkARustEngine,
} from "@/config/networkAEngine";
import { isTauri } from "@/services/aheClient";
import {
  fetchEnrichedModelCatalog,
  findEnrichedModel,
  type EnrichedModel,
} from "@/services/modelCatalogApi";
import MnistSamplePanel from "@/components/inference/MnistSamplePanel.vue";
import PageCard from "@/components/PageCard.vue";
import { loadGovernanceLaunch, clearGovernanceLaunch } from "@/services/governanceLaunch";

const route = useRoute();
const router = useRouter();
const message = useMessage();
const step = ref(1);
const enrichedModels = ref<EnrichedModel[]>([]);
const aheIds = ref<Set<string>>(new Set());
const modelId = ref("cnn-mnist-trained");
const custodyMode = ref<"hosted" | "client_local">("hosted");
const rustEngine = ref<NetworkARustEngine>(loadSavedNetworkAEngine());
const creating = ref(false);
const desktop = isTauri();

const inferMode = ref<"single" | "batch">("single");
const datasetId = ref("mnist-test");
const sampleIndex = ref(0);
const batchStart = ref(0);
const batchEnd = ref(4);

const selectedModel = computed(() => findEnrichedModel(enrichedModels.value, modelId.value));

const inferencePlan = computed(() =>
  resolveInferencePlan(
    selectedModel.value,
    modelId.value,
    aheIds.value,
    desktop,
    datasetId.value,
  ),
);

const governance = computed(() =>
  evaluateHomomorphicFeasibility(
    selectedModel.value,
    modelId.value,
    datasetId.value,
    aheIds.value,
    desktop,
    batchSize.value,
  ),
);

const pageSubtitle = computed(() => {
  const m = selectedModel.value;
  if (!m) return "选择模型与数据集，完成 Preflight 后启动密态推理";
  const modeLabel = inferencePlan.value.mode === "rust_ahe" ? "密态推理" : "演示计时";
  return `${m.familyLabel} · ${modeLabel}`;
});

const modelOptions = computed(() =>
  enrichedModels.value.map((m) => ({
    label: modelSelectLabel(m),
    value: m.id,
  })),
);

const batchSize = computed(() =>
  inferMode.value === "single"
    ? 1
    : Math.max(1, batchEnd.value - batchStart.value + 1),
);

watch(rustEngine, (v) => saveNetworkAEngine(v));

watch(modelId, (id) => {
  const m = findEnrichedModel(enrichedModels.value, id);
  if (m && route.query.from !== "governance") datasetId.value = m.defaultDatasetId;
});

onMounted(async () => {
  const catalog = await fetchEnrichedModelCatalog();
  enrichedModels.value = catalog.models;
  aheIds.value = catalog.aheCapableIds;

  const launch = loadGovernanceLaunch();
  const q = route.query;
  if (launch || q.from === "governance") {
    const payload = launch ?? {
      modelId: String(q.model ?? modelId.value),
      datasetId: String(q.dataset ?? datasetId.value),
      inferMode: "single" as const,
      sampleIndex: 0,
      batchStart: 0,
      batchEnd: 4,
    };
    modelId.value = payload.modelId;
    datasetId.value = payload.datasetId;
    inferMode.value = payload.inferMode;
    sampleIndex.value = payload.sampleIndex;
    batchStart.value = payload.batchStart;
    batchEnd.value = payload.batchEnd;
    step.value = 2;
    clearGovernanceLaunch();
  } else {
    if (catalog.models.length && !catalog.models.some((m) => m.id === modelId.value)) {
      modelId.value =
        catalog.models.find((m) => m.family === "network_a")?.id ?? catalog.models[0].id;
    }
    const m = findEnrichedModel(enrichedModels.value, modelId.value);
    if (m) datasetId.value = m.defaultDatasetId;
  }
});

async function nextStep() {
  if (step.value < 3) {
    if (step.value === 2 && inferMode.value === "batch" && batchEnd.value < batchStart.value) {
      message.warning("批量结束序号不能小于起始序号");
      return;
    }
    if (step.value === 2 && !governance.value.canLaunch) {
      message.error(governance.value.compatibilityDetail || "当前组合不可运行");
      return;
    }
    step.value += 1;
    return;
  }
  creating.value = true;
  const createRes = await getBridge().bridgeRunCreate({
    model_id: modelId.value,
    dataset_id: datasetId.value,
    custody_mode: custodyMode.value,
    capability_mode: "data_only",
    batch_size: batchSize.value,
    privacy_mode: "balanced",
    rust_engine: inferencePlan.value.showRustEnginePicker ? rustEngine.value : undefined,
    sample_index: inferMode.value === "single" ? sampleIndex.value : batchStart.value,
    mnist_index: inferMode.value === "single" ? sampleIndex.value : undefined,
    mnist_start: inferMode.value === "batch" ? batchStart.value : sampleIndex.value,
    mnist_end: inferMode.value === "batch" ? batchEnd.value : sampleIndex.value,
  });
  creating.value = false;
  if (!createRes.ok || !createRes.data) {
    message.error(createRes.error?.message ?? "创建失败");
    return;
  }
  const pf = await getBridge().bridgeRunPreflight(createRes.data.run_id);
  if (pf.ok && pf.data && !pf.data.can_start) {
    message.warning("Preflight 未通过，请检查密态方案");
  }
  router.push(`/runs/${createRes.data.run_id}`);
}
</script>

<template>
  <PageCard>
    <h1 class="page-title">新建推理任务</h1>
    <p class="page-subtitle">{{ pageSubtitle }}</p>

    <NSteps :current="step" size="small" style="margin: 20px 0">
      <NStep title="数据与托管" />
      <NStep title="模型与样本" />
      <NStep title="Preflight" />
    </NSteps>

    <NCard v-if="step === 1" size="small" :bordered="false" class="inner-card">
      <NForm label-placement="left" label-width="120">
        <NFormItem label="托管模式">
          <NRadioGroup v-model:value="custodyMode">
            <NSpace>
              <NRadio value="hosted">托管数据 (hosted)</NRadio>
              <NRadio value="client_local">本地数据 (client_local)</NRadio>
            </NSpace>
          </NRadioGroup>
        </NFormItem>
      </NForm>
    </NCard>

    <NCard v-else-if="step === 2" size="small" :bordered="false" class="inner-card">
      <NForm label-placement="left" label-width="120">
        <NFormItem label="模型">
          <NSelect v-model:value="modelId" :options="modelOptions" />
        </NFormItem>

        <NFormItem v-if="selectedModel" label="模型族">
          <NSpace align="center">
            <NTag size="small" round>{{ selectedModel.familyLabel }}</NTag>
            <NTag
              size="small"
              round
              :type="inferencePlan.mode === 'rust_ahe' ? 'success' : 'info'"
            >
              {{ inferencePlan.mode === "rust_ahe" ? "密态推理" : "演示计时" }}
            </NTag>
          </NSpace>
        </NFormItem>

        <NFormItem label="样本">
          <MnistSamplePanel
            v-model:infer-mode="inferMode"
            v-model:dataset-id="datasetId"
            v-model:sample-index="sampleIndex"
            v-model:batch-start="batchStart"
            v-model:batch-end="batchEnd"
          />
        </NFormItem>

        <NFormItem v-if="inferencePlan.showRustEnginePicker" label="密态引擎">
          <NRadioGroup v-model:value="rustEngine">
            <NSpace vertical>
              <NRadio v-for="e in NETWORK_A_RUST_ENGINES" :key="e.id" :value="e.id">
                {{ e.label }} · ahe-server :{{ e.port }}
              </NRadio>
            </NSpace>
          </NRadioGroup>
        </NFormItem>

        <NAlert
          :type="governance.statusType"
          :bordered="false"
          :title="governance.pairLabel + ' · ' + governance.statusLabel"
          style="margin-top: 8px"
        >
          假定训练准确度 {{ governance.expectedAccuracyPct.toFixed(2) }}%
          <template v-if="governance.mockBatchDisplayPct != null">
            · 批量展示约 {{ governance.mockBatchDisplayPct.toFixed(2) }}%
          </template>
        </NAlert>
      </NForm>
    </NCard>

    <NCard v-else size="small" :bordered="false" class="inner-card">
      <dl class="preflight-summary">
        <dt>模型</dt>
        <dd>{{ selectedModel?.name ?? modelId }}</dd>
        <dt>模型族</dt>
        <dd>{{ selectedModel?.familyLabel ?? "—" }}</dd>
        <dt>数据集</dt>
        <dd>{{ datasetId }}</dd>
        <dt>样本</dt>
        <dd>
          <template v-if="inferMode === 'single'">单图 #{{ sampleIndex }}</template>
          <template v-else>#{{ batchStart }} — #{{ batchEnd }}（{{ batchSize }} 张）</template>
        </dd>
        <dt>推理路径</dt>
        <dd>{{ inferencePlan.preflightSchemeDetail }}</dd>
        <dt v-if="inferencePlan.mode === 'timing_demo'">计时 profile</dt>
        <dd v-if="inferencePlan.mode === 'timing_demo'">
          <code class="mono">{{ inferencePlan.perfProfileKey }}</code>
        </dd>
        <dt v-if="inferencePlan.showRustEnginePicker">引擎</dt>
        <dd v-if="inferencePlan.showRustEnginePicker">
          {{ rustEngine === "rust-ec" ? "EC :8002" : "Arkworks :8001" }}
        </dd>
      </dl>
      <p class="preflight-hint">
        Preflight 将检查模型 registry、密态推理节点与所选模型的推理路径。
      </p>
    </NCard>

    <NSpace style="margin-top: 16px">
      <NButton v-if="step > 1" @click="step -= 1">上一步</NButton>
      <NButton type="primary" :loading="creating" @click="nextStep">
        {{ step < 3 ? "下一步" : "创建并进入现场" }}
      </NButton>
    </NSpace>
  </PageCard>
</template>

<style scoped>
.inner-card {
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
}

.preflight-summary {
  display: grid;
  grid-template-columns: 88px 1fr;
  gap: 8px 12px;
  margin: 0 0 12px;
  font-size: var(--text-sm);
}

.preflight-summary dt {
  margin: 0;
  color: var(--color-text-muted);
}

.preflight-summary dd {
  margin: 0;
  color: var(--color-text-primary);
}

.preflight-hint {
  margin: 0;
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}

.mono {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
}
</style>
