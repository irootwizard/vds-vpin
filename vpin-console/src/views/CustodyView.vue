<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useMessage } from "naive-ui";
import {
  NAlert,
  NButton,
  NCard,
  NDescriptions,
  NDescriptionsItem,
  NList,
  NListItem,
  NSpace,
  NSteps,
  NStep,
  NTag,
} from "naive-ui";
import { getBridge } from "@/bridge/client";
import { fetchDatasetCatalog, type DatasetEntry } from "@/services/datasetsApi";
import type { CustodyCapabilities } from "@/bridge/types";
import type {
  CustodyCommitResult,
  CustodyDefaultsView,
  CustodyUploadSession,
  DataBindingRecord,
  IntegrityVerifyResult,
} from "@/custody/types";
import {
  custodySampleLabel,
  isPreviewableIndexedDataset,
  isUploadDataset,
} from "@/services/custodyDataset";
import { loadSamplePreview } from "@/services/datasetPreview";
import CustodyDatasetPicker from "@/components/custody/CustodyDatasetPicker.vue";
import PageCard from "@/components/PageCard.vue";
import { isTauri } from "@/services/aheClient";

const message = useMessage();
const caps = ref<CustodyCapabilities | null>(null);
const defaults = ref<CustodyDefaultsView | null>(null);
const localDatasets = ref<DatasetEntry[]>([]);
const bindings = ref<DataBindingRecord[]>([]);

const step = ref(1);
const busy = ref(false);
const datasetId = ref("mnist-test");
const sampleIndex = ref(0);
const uploadFile = ref<File | null>(null);
const catalogLoading = ref(true);

const session = ref<CustodyUploadSession | null>(null);
const commit = ref<CustodyCommitResult | null>(null);
const binding = ref<DataBindingRecord | null>(null);
const verify = ref<IntegrityVerifyResult | null>(null);
const chunkPreview = ref<{ chunk_index: number; vads_index: number; digest_hex: string }[]>([]);

const selectedDataset = computed(
  () => localDatasets.value.find((d) => d.id === datasetId.value) ?? null,
);

async function refreshMeta() {
  catalogLoading.value = true;
  const bridge = getBridge();
  const [capRes, defRes, listRes, catalog] = await Promise.all([
    bridge.bridgeCustodyGetCapabilities(),
    bridge.bridgeCustodyGetDefaults(),
    bridge.bridgeCustodyListBindings(),
    fetchDatasetCatalog(),
  ]);
  if (capRes.ok && capRes.data) caps.value = capRes.data;
  if (defRes.ok && defRes.data) defaults.value = defRes.data;
  if (listRes.ok && listRes.data) bindings.value = listRes.data;
  localDatasets.value = catalog?.local ?? [];
  catalogLoading.value = false;
}

onMounted(refreshMeta);

async function startCustody() {
  const entry = selectedDataset.value;
  if (!entry) {
    message.error("请选择数据集");
    return;
  }

  busy.value = true;
  verify.value = null;
  commit.value = null;
  binding.value = null;
  try {
    let createRes;
    let rustDigest: string | undefined;
    let preprocessLane: "rust" | "js" = "js";

    if (isUploadDataset(entry) && uploadFile.value) {
      const buf = new Uint8Array(await uploadFile.value.arrayBuffer());
      createRes = await getBridge().bridgeCustodyCreateUploadSession({
        dataset_id: entry.id,
        file_name: uploadFile.value.name,
        file_bytes: [...buf],
        preprocess_lane: "js",
      });
    } else if (isTauri() && isPreviewableIndexedDataset(entry.id)) {
      const prep = await loadSamplePreview(entry.id, sampleIndex.value);
      rustDigest = prep?.input_digest_hex;
      preprocessLane = rustDigest ? "rust" : "js";
      createRes = await getBridge().bridgeCustodyCreateUploadSession({
        dataset_id: entry.id,
        sample_index: sampleIndex.value,
        rust_input_digest_hex: rustDigest,
        preprocess_lane: preprocessLane,
      });
    } else {
      createRes = await getBridge().bridgeCustodyCreateUploadSession({
        dataset_id: entry.id,
        sample_index: sampleIndex.value,
        preprocess_lane: "js",
      });
    }

    if (!createRes.ok || !createRes.data) {
      message.error(createRes.error?.message ?? "创建会话失败");
      return;
    }
    session.value = createRes.data.session;
    chunkPreview.value = createRes.data.chunks;
    step.value = 2;

    const commitRes = await getBridge().bridgeCustodyCommit(session.value.session_id);
    if (!commitRes.ok || !commitRes.data) {
      message.error(commitRes.error?.message ?? "commit 失败");
      return;
    }
    commit.value = commitRes.data;
    step.value = 3;

    const label = custodySampleLabel(entry, {
      index: isUploadDataset(entry) ? undefined : sampleIndex.value,
      fileName: uploadFile.value?.name,
    });
    const bindRes = await getBridge().bridgeCustodyCreateBinding(
      session.value.session_id,
      label,
    );
    if (!bindRes.ok || !bindRes.data) {
      message.error(bindRes.error?.message ?? "binding 失败");
      return;
    }
    binding.value = bindRes.data;
    step.value = 4;
    await refreshMeta();
    message.success(`托管完成：${label}`);
  } finally {
    busy.value = false;
  }
}

async function runVerify() {
  if (!binding.value) return;
  busy.value = true;
  try {
    const res = await getBridge().bridgeCustodyVerifyIntegrity(binding.value.binding_id);
    if (res.ok && res.data) {
      verify.value = res.data;
      if (res.data.ok) message.success("验证通过：数据未篡改");
      else message.error(res.data.message);
    }
  } finally {
    busy.value = false;
  }
}

async function runTamperDemo() {
  if (!session.value) return;
  busy.value = true;
  try {
    await getBridge().bridgeCustodySimulateTamper(session.value.session_id, 0);
    message.info("已注入异常分片，请再次点击验证");
    verify.value = null;
  } finally {
    busy.value = false;
  }
}

async function runRestoreIntegrity() {
  if (!session.value) return;
  busy.value = true;
  try {
    const res = await getBridge().bridgeCustodyRestoreIntegrity(session.value.session_id);
    if (!res.ok || !res.data?.ok) {
      message.error("恢复分片失败");
      return;
    }
    verify.value = null;
    message.success("分片已恢复，可重新验证");
  } finally {
    busy.value = false;
  }
}

function clearWorkflowUi() {
  session.value = null;
  commit.value = null;
  binding.value = null;
  verify.value = null;
  chunkPreview.value = [];
  step.value = 1;
}

async function resetCustodyWorkflow() {
  if (!session.value) {
    clearWorkflowUi();
    return;
  }
  busy.value = true;
  try {
    await getBridge().bridgeCustodyDiscardWorkflow({
      session_id: session.value.session_id,
      binding_id: binding.value?.binding_id,
    });
    clearWorkflowUi();
    await refreshMeta();
    message.success("已重置托管流程，可重新选择数据");
  } finally {
    busy.value = false;
  }
}

async function deleteHistoryBinding(bindingId: string) {
  busy.value = true;
  try {
    const res = await getBridge().bridgeCustodyDeleteBinding(bindingId);
    if (res.ok && res.data?.ok) {
      if (binding.value?.binding_id === bindingId) {
        clearWorkflowUi();
      }
      await refreshMeta();
      message.success("已删除历史 Binding");
    }
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <PageCard>
    <h1 class="page-title">数据托管</h1>
    <p class="page-subtitle">upload → commit → binding → 完整性验证</p>

    <NCard v-if="caps" size="small" title="托管方能力" :bordered="false" class="inner-card">
      <NSpace align="center">
        <NTag type="success">托管节点</NTag>
        <NTag size="small" type="info">数据托管</NTag>
      </NSpace>
      <p v-if="defaults" class="muted">
        分片 {{ defaults.chunk_size_bytes }} B · 并行 {{ defaults.max_parallel_uploads }} ·
        {{ defaults.verify_mode }}
      </p>
    </NCard>

    <NSteps :current="step" size="small" style="margin: 16px 0">
      <NStep title="选择数据" />
      <NStep title="上传分片" />
      <NStep title="Commit" />
      <NStep title="Binding" />
    </NSteps>

    <NCard size="small" title="1. 选择托管数据" :bordered="false" class="inner-card">
      <CustodyDatasetPicker
        v-model:dataset-id="datasetId"
        v-model:sample-index="sampleIndex"
        v-model:upload-file="uploadFile"
        :datasets="localDatasets"
        :loading="catalogLoading"
        :starting="busy"
        @start="startCustody"
      />
      <p v-if="busy" class="muted" style="margin-top: 12px">托管进行中…</p>
    </NCard>

    <NCard v-if="session" size="small" title="2. 上传会话" :bordered="false" class="inner-card">
      <NDescriptions :column="2" label-placement="left" size="small">
        <NDescriptionsItem label="session_id">
          <code class="mono">{{ session.session_id }}</code>
        </NDescriptionsItem>
        <NDescriptionsItem label="file_id">{{ session.file_id }}</NDescriptionsItem>
        <NDescriptionsItem label="数据集">{{ selectedDataset?.name ?? datasetId }}</NDescriptionsItem>
        <NDescriptionsItem label="分片数">{{ session.total_chunks }}</NDescriptionsItem>
      </NDescriptions>
      <div class="label" style="margin-top: 8px">VADS 分片摘要</div>
      <NList size="small" bordered>
        <NListItem v-for="c in chunkPreview" :key="c.chunk_index">
          #{{ c.chunk_index }} · vads {{ c.vads_index }} ·
          <code class="mono">{{ c.digest_hex.slice(0, 24) }}…</code>
        </NListItem>
      </NList>
    </NCard>

    <NCard v-if="commit" size="small" title="3. Commit manifest" :bordered="false" class="inner-card">
      <code class="mono block">{{ commit.manifest_digest_hex }}</code>
    </NCard>

    <NCard v-if="binding" size="small" title="4. DataBinding" :bordered="false" class="inner-card">
      <NDescriptions :column="1" label-placement="left" size="small">
        <NDescriptionsItem label="binding_id">
          <code class="mono">{{ binding.binding_id }}</code>
        </NDescriptionsItem>
        <NDescriptionsItem label="样本">
          {{ binding.sample_label ?? session?.file_id }}
        </NDescriptionsItem>
        <NDescriptionsItem label="vads_indices">
          {{ binding.vads_indices.join(", ") }}
        </NDescriptionsItem>
        <NDescriptionsItem v-if="binding.preprocess_lane" label="预处理">
          <NTag size="small" :type="binding.preprocess_lane === 'rust' ? 'success' : 'default'">
            {{ binding.preprocess_lane === "rust" ? "ahe-cli 预处理" : "标准预处理" }}
          </NTag>
        </NDescriptionsItem>
        <NDescriptionsItem v-if="binding.rust_input_digest_hex" label="input_digest">
          <code class="mono">{{ binding.rust_input_digest_hex }}</code>
        </NDescriptionsItem>
      </NDescriptions>
      <NSpace style="margin-top: 12px">
        <NButton type="primary" :loading="busy" @click="runVerify">验证数据未篡改</NButton>
        <NButton secondary :loading="busy" @click="runTamperDemo">完整性抽检</NButton>
        <NButton secondary :loading="busy" @click="runRestoreIntegrity">恢复分片</NButton>
        <NButton quaternary :loading="busy" @click="resetCustodyWorkflow">重置托管</NButton>
      </NSpace>
      <NAlert
        v-if="verify"
        :type="verify.ok ? 'success' : 'error'"
        :bordered="false"
        style="margin-top: 12px"
        :title="verify.ok ? 'PASS' : 'FAIL'"
      >
        {{ verify.message }}
        <div v-if="!verify.ok" class="muted">
          期望 {{ verify.manifest_digest_hex.slice(0, 32) }}…
          <br />
          重算 {{ verify.recomputed_digest_hex.slice(0, 32) }}…
        </div>
      </NAlert>
    </NCard>

    <NCard size="small" title="历史 Binding" :bordered="false" class="inner-card">
      <NList v-if="bindings.length" size="small">
        <NListItem v-for="b in bindings" :key="b.binding_id">
          <div class="history-row">
            <span>
              <code class="mono">{{ b.binding_id }}</code>
              <span class="muted">
                · {{ b.sample_label ?? b.file_id }} · {{ b.created_at.slice(11, 19) }}
              </span>
            </span>
            <NButton
              quaternary
              size="tiny"
              type="error"
              :loading="busy"
              @click="deleteHistoryBinding(b.binding_id)"
            >
              删除
            </NButton>
          </div>
        </NListItem>
      </NList>
      <p v-else class="muted">暂无记录</p>
    </NCard>
  </PageCard>
</template>

<style scoped>
.inner-card {
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  margin-bottom: var(--space-4);
  padding: var(--space-2);
}

.label {
  display: block;
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  margin-bottom: 6px;
}

.muted {
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}

.mono {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
}

.block {
  display: block;
  word-break: break-all;
}

.history-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  width: 100%;
}
</style>
