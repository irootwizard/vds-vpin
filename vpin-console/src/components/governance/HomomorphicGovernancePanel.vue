<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import {
  NAlert,
  NButton,
  NCard,
  NDescriptions,
  NDescriptionsItem,
  NForm,
  NFormItem,
  NList,
  NListItem,
  NSelect,
  NSpace,
  NTag,
} from "naive-ui";
import { evaluateHomomorphicFeasibility } from "@/config/homomorphicGovernance";
import { modelSelectLabel } from "@/config/modelCatalog";
import { isTauri } from "@/services/aheClient";
import {
  fetchEnrichedModelCatalog,
  findEnrichedModel,
  type EnrichedModel,
} from "@/services/modelCatalogApi";
import { fetchDatasetCatalog } from "@/services/datasetsApi";
import { custodySelectableDatasets } from "@/services/custodyDataset";
import { saveGovernanceLaunch } from "@/services/governanceLaunch";

const router = useRouter();
const desktop = isTauri();

const enrichedModels = ref<EnrichedModel[]>([]);
const aheIds = ref<Set<string>>(new Set());
const modelId = ref("cnn-mnist-trained");
const datasetId = ref("mnist-test");
const loading = ref(true);

const datasetOptions = ref<{ label: string; value: string }[]>([]);

const selectedModel = computed(() => findEnrichedModel(enrichedModels.value, modelId.value));

/** 治理平面仅评估模型×数据集，批量样本范围在「新建运行」中配置 */
const feasibility = computed(() =>
  evaluateHomomorphicFeasibility(
    selectedModel.value,
    modelId.value,
    datasetId.value,
    aheIds.value,
    desktop,
    1,
  ),
);

const modelOptions = computed(() =>
  enrichedModels.value.map((m) => ({
    label: modelSelectLabel(m),
    value: m.id,
  })),
);

onMounted(async () => {
  loading.value = true;
  const [catalog, dsCatalog] = await Promise.all([
    fetchEnrichedModelCatalog(),
    fetchDatasetCatalog(),
  ]);
  enrichedModels.value = catalog.models;
  aheIds.value = catalog.aheCapableIds;
  datasetOptions.value = custodySelectableDatasets(dsCatalog ?? { local: [] })
    .filter((d) => d.id !== "user-upload-image")
    .map((d) => ({ label: d.name, value: d.id }));
  if (catalog.models.length && !catalog.models.some((m) => m.id === modelId.value)) {
    modelId.value =
      catalog.models.find((m) => m.family === "network_a")?.id ?? catalog.models[0].id;
  }
  loading.value = false;
});

function launchInference() {
  if (!feasibility.value.canLaunch) return;
  saveGovernanceLaunch({
    modelId: modelId.value,
    datasetId: datasetId.value,
    inferMode: "single",
    sampleIndex: 0,
    batchStart: 0,
    batchEnd: 0,
  });
  router.push({
    path: "/runs/new",
    query: {
      from: "governance",
      model: modelId.value,
      dataset: datasetId.value,
    },
  });
}
</script>

<template>
  <NCard title="密态治理平面" :bordered="false" class="gov-card">
    <p class="gov-lead">
      选择<strong>模型</strong>与<strong>数据集</strong>组合，评估能否进行同态推理。
      各组合均视为已具备对应训练权重；仅 <strong>Simple CNN Network A × CIFAR-10</strong> 不可用，其余为演示计时（mock），Network A × MNIST 可走真密态路径。
    </p>

    <NForm label-placement="left" label-width="72" :disabled="loading">
      <NFormItem label="模型">
        <NSelect v-model:value="modelId" :options="modelOptions" filterable />
      </NFormItem>

      <NFormItem label="数据集">
        <NSelect v-model:value="datasetId" :options="datasetOptions" />
      </NFormItem>
    </NForm>

    <NCard size="small" title="同态推理评估" :bordered="false" class="assess-card">
      <NSpace align="center" style="margin-bottom: 12px">
        <NTag round>{{ feasibility.pairLabel }}</NTag>
        <NTag :type="feasibility.statusType" round>
          {{ feasibility.statusLabel }}
        </NTag>
        <NTag v-if="feasibility.status === 'real_ahe'" size="small" type="success">真 AHE</NTag>
        <NTag v-else-if="feasibility.status === 'mock'" size="small" type="info">timing-demo</NTag>
        <NTag v-else size="small" type="error">不可用</NTag>
      </NSpace>

      <NDescriptions :column="2" label-placement="left" size="small">
        <NDescriptionsItem label="组合">
          {{ feasibility.compatibilityDetail }}
        </NDescriptionsItem>
        <NDescriptionsItem label="推理路径">
          {{ feasibility.inferencePlan.preflightSchemeDetail }}
        </NDescriptionsItem>
        <NDescriptionsItem label="假定训练准确度">
          <template v-if="feasibility.expectedAccuracyPct > 0">
            {{ feasibility.expectedAccuracyPct.toFixed(2) }}%
          </template>
          <template v-else>—</template>
        </NDescriptionsItem>
      </NDescriptions>

      <NList size="small" style="margin-top: 12px">
        <NListItem v-for="c in feasibility.checks" :key="c.id">
          <NSpace align="center" :size="8">
            <NTag size="tiny" :type="c.pass ? 'success' : 'error'">
              {{ c.pass ? "通过" : "未通过" }}
            </NTag>
            <span class="check-label">{{ c.label }}</span>
            <span class="check-detail">{{ c.detail }}</span>
          </NSpace>
        </NListItem>
      </NList>

      <NAlert
        v-if="!feasibility.canLaunch"
        type="warning"
        :bordered="false"
        style="margin-top: 12px"
        title="暂不可进入推理"
      >
        <template v-if="feasibility.status === 'blocked'">
          {{ feasibility.compatibilityDetail }}
        </template>
        <template v-else>
          Network A × MNIST 真密态推理需 Tauri 桌面端且 AHE 权重已注册。
        </template>
      </NAlert>
    </NCard>

    <NSpace style="margin-top: 16px">
      <NButton type="primary" :disabled="!feasibility.canLaunch" @click="launchInference">
        进入密态推理
      </NButton>
      <NButton secondary @click="router.push('/models')">模型仓库</NButton>
    </NSpace>
  </NCard>
</template>

<style scoped>
.gov-card {
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm);
}

.gov-lead {
  margin: 0 0 var(--space-4);
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  line-height: 1.6;
}

.gov-lead strong {
  color: var(--color-text-primary);
  font-weight: 600;
}

.assess-card {
  margin-top: var(--space-3);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
}

.check-label {
  font-size: var(--text-sm);
  font-weight: 500;
}

.check-detail {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
}
</style>
