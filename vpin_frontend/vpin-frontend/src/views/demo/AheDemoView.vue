<template>
  <div class="ahe-demo">
    <n-page-header title="AHE 密态推理实验室" subtitle="Tauri 桌面端 · pipeline → WebSocket P0–P3" />

    <n-alert
      v-if="!isDesktop"
      type="warning"
      title="推理需桌面端"
      style="margin-bottom: 12px"
    >
      浏览器模式仅支持数据预处理预览。AHE 推理请在 Tauri 中运行（<code>npm run tauri dev</code>），私钥不离开本机。
    </n-alert>

    <n-grid :cols="2" :x-gap="16" responsive="screen">
      <n-gi>
        <n-card title="官方 MNIST">
          <n-space vertical>
            <n-input-number v-model:value="index" :min="0" :max="9999" />
            <n-space>
              <n-button :loading="busy" @click="preprocess">预处理当前序号</n-button>
              <n-button :loading="galleryLoading" quaternary @click="loadGallery">刷新预览</n-button>
            </n-space>
          </n-space>
        </n-card>

        <n-card title="上传图片" style="margin-top: 12px">
          <n-space vertical>
            <n-upload
              :show-file-list="false"
              accept="image/*"
              :disabled="uploadLoading"
              @change="onUploadChange"
            >
              <n-button :loading="uploadLoading">选择图片并预处理</n-button>
            </n-upload>
            <n-text depth="3" style="font-size: 12px">
              浏览器：服务端预处理并存储；Tauri：本地 vpin_client 预处理
            </n-text>
          </n-space>
        </n-card>

        <n-card title="样本预览" style="margin-top: 12px">
          <n-spin :show="galleryLoading && !gallery.length">
            <div v-if="gallery.length" class="gallery">
              <button
                v-for="item in gallery"
                :key="sampleKey(item)"
                type="button"
                class="gallery-item"
                :class="{ selected: isSelected(item) }"
                @click="selectSample(item)"
              >
                <img
                  :src="`data:image/png;base64,${item.preview_png_base64}`"
                  :alt="item.filename || `mnist ${item.mnist_index}`"
                />
                <span class="gallery-meta">{{ formatMeta(item) }}</span>
              </button>
            </div>
            <n-empty v-else-if="!galleryLoading" description="暂无预览" size="small" />
          </n-spin>
        </n-card>
      </n-gi>
      <n-gi>
        <n-card title="推理">
          <n-space vertical>
            <n-select
              v-model:value="modelId"
              :options="modelOptions"
              placeholder="选择模型"
              :loading="modelsLoading"
            />
            <n-button
              type="primary"
              :loading="busy"
              :disabled="!canRunAheInfer"
              @click="runInfer"
            >
              运行 AHE 推理（{{ inferLabel }}）
            </n-button>
            <n-text v-if="!canRunAheInfer && !modelsLoading" depth="3" style="font-size: 12px">
              <template v-if="!isDesktop">请使用 Tauri 桌面端以运行推理。</template>
              <template v-else>请先选择样本；若无可用模型，请确认后端已启动且权重已注册。</template>
            </n-text>
            <div v-if="result">
              <p>预测: {{ result.prediction }}<span v-if="result.label != null"> / 标签: {{ result.label }}</span></p>
              <p v-if="timing">crypto_infer_ms: {{ timing.crypto_infer_ms?.toFixed(0) }}</p>
            </div>
            <n-alert v-if="error" type="error">{{ error }}</n-alert>
          </n-space>
        </n-card>
      </n-gi>
    </n-grid>

    <n-card title="推理流程时间线" style="margin-top: 16px">
      <template #header-extra>
        <n-text depth="3" style="font-size: 12px">点击各阶段查看张量形状、密文形式与截断参数</n-text>
      </template>
      <AheFlowTimeline
        :steps="flowSteps"
        :running="busy"
        :running-phase="runningPhase"
        @select="openStepDetail"
      />
    </n-card>

    <AheTraceDrawer v-model:show="drawerOpen" :step="selectedStep" />
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { useAheDemoSession } from "../../composables/useAheDemoSession.js";
import AheFlowTimeline from "../../components/demo/AheFlowTimeline.vue";
import AheTraceDrawer from "../../components/demo/AheTraceDrawer.vue";
import { AHE_PHASES } from "../../constants/aheFlow.js";
import {
  aheInfer,
  ahePreprocess,
  ahePreprocessBatch,
  fetchAheModels,
  isTauri,
} from "../../services/aheClient.js";
import { listUploads, uploadAndPreprocess } from "../../services/dataApi.js";

const PREVIEW_COUNT = 10;
const isDesktop = isTauri();

const { state, log: pushLog } = useAheDemoSession();
const index = ref(0);
const modelId = ref("");
const modelOptions = ref([]);
const modelsLoading = ref(false);
const gallery = ref([]);
const galleryLoading = ref(false);
const uploadLoading = ref(false);
const busy = ref(false);
const result = ref(null);
const timing = ref(null);
const error = ref(null);
const flowSteps = ref([]);
const selectedStep = ref(null);
const drawerOpen = ref(false);
const runningPhase = ref(0);
const selectedSample = ref(null);
const lastUploadPath = ref(null);

const canRunAheInfer = computed(
  () =>
    isDesktop &&
    Boolean(selectedSample.value?.input_digest_hex) &&
    Boolean(modelId.value)
);

const inferLabel = computed(() => {
  if (!selectedSample.value) return "—";
  if (selectedSample.value.source === "upload") {
    return selectedSample.value.filename || selectedSample.value.upload_id?.slice(0, 8);
  }
  return `#${selectedSample.value.mnist_index}`;
});

function sampleKey(item) {
  return item.upload_id || `mnist-${item.mnist_index}`;
}

function isSelected(item) {
  const sel = selectedSample.value;
  if (!sel) return false;
  if (item.upload_id && sel.upload_id) return item.upload_id === sel.upload_id;
  return item.mnist_index === sel.mnist_index;
}

function formatMeta(item) {
  if (item.source === "upload") {
    return item.filename || item.upload_id?.slice(0, 8) || "upload";
  }
  return `#${item.mnist_index} · ${item.label}`;
}

function nowStr() {
  return new Date().toLocaleTimeString();
}

function appendSteps(steps) {
  for (const s of steps) {
    flowSteps.value.push({ ...s, at: s.at || nowStr() });
  }
}

function mergePreprocessTrace(prep) {
  if (!prep?.preprocess_trace?.length) return;
  flowSteps.value = flowSteps.value.filter((s) => s.category !== "预处理");
  appendSteps(prep.preprocess_trace);
}

function openStepDetail(step) {
  selectedStep.value = step;
  drawerOpen.value = true;
}

function addLog(title, content) {
  pushLog({ title, content, at: nowStr() });
}

function applySelection(prep) {
  selectedSample.value = prep;
  if (prep.mnist_index != null) {
    index.value = prep.mnist_index;
    state.selectedIndex = prep.mnist_index;
  }
  state.preprocessResult = prep;
  mergePreprocessTrace(prep);
}

function selectSample(item) {
  applySelection(item);
}

async function loadModels() {
  modelsLoading.value = true;
  try {
    const data = await fetchAheModels();
    const models = data.models || [];
    modelOptions.value = models.map((m) => ({
      label: `${m.name} (Network ${m.network})`,
      value: m.id,
    }));
    if (!modelId.value && modelOptions.value.length) {
      const trained = modelOptions.value.find((m) => m.value === "cnn-mnist-trained");
      modelId.value = trained?.value ?? modelOptions.value[0].value;
    }
  } catch (e) {
    modelOptions.value = [
      { label: "cnn-mnist（legacy）", value: "cnn-mnist" },
    ];
    if (!modelId.value) modelId.value = "cnn-mnist-trained";
    error.value = `模型列表加载失败: ${e}`;
  } finally {
    modelsLoading.value = false;
  }
}

async function loadGallery(start = 0) {
  galleryLoading.value = true;
  error.value = null;
  try {
    const batch = await ahePreprocessBatch(start, PREVIEW_COUNT);
    const official = (batch.items || []).map((item) => ({ ...item, source: "official" }));
    let uploads = [];
    if (!isTauri()) {
      try {
        const up = await listUploads(20);
        uploads = (up.items || []).map((item) => ({ ...item, source: "upload" }));
      } catch {
        /* uploads optional */
      }
    }
    gallery.value = [...uploads, ...official];
    if (gallery.value.length) {
      const current = gallery.value.find((item) => item.mnist_index === index.value);
      applySelection(current || gallery.value[0]);
    }
    addLog("数据加载", `官方 ${official.length} 张`);
  } catch (e) {
    error.value = String(e);
    state.connectionStatus = "error";
  } finally {
    galleryLoading.value = false;
  }
}

async function preprocess() {
  busy.value = true;
  error.value = null;
  try {
    const prep = await ahePreprocess(index.value);
    const item = { ...prep, source: "official" };
    const existing = gallery.value.findIndex((g) => sampleKey(g) === sampleKey(item));
    if (existing >= 0) {
      gallery.value[existing] = item;
    } else {
      gallery.value.unshift(item);
    }
    applySelection(item);
    mergePreprocessTrace(item);
    addLog("官方预处理", `index=${index.value}`);
  } catch (e) {
    error.value = String(e);
    state.connectionStatus = "error";
  } finally {
    busy.value = false;
  }
}

async function onUploadChange({ file }) {
  const raw = file?.file;
  if (!raw) return;
  uploadLoading.value = true;
  error.value = null;
  try {
    let prep;
    if (isTauri()) {
      const { invoke } = await import("@tauri-apps/api/core");
      const path = raw.path;
      if (!path) {
        throw new Error("Tauri 需要本地文件路径，请使用桌面应用上传");
      }
      lastUploadPath.value = path;
      prep = await invoke("preprocess_upload_file", { path });
    } else {
      prep = await uploadAndPreprocess(raw);
    }
    const item = { ...prep, source: "upload" };
    const existing = gallery.value.findIndex((g) => sampleKey(g) === sampleKey(item));
    if (existing >= 0) {
      gallery.value[existing] = item;
    } else {
      gallery.value.unshift(item);
    }
    applySelection(item);
    mergePreprocessTrace(item);
    addLog("上传预处理", prep.filename || "image");
  } catch (e) {
    error.value = String(e);
  } finally {
    uploadLoading.value = false;
  }
}

async function runInfer() {
  if (!canRunAheInfer.value) return;
  busy.value = true;
  error.value = null;
  state.connectionStatus = "connecting";
  runningPhase.value = 0;
  flowSteps.value = flowSteps.value.filter((s) => s.category === "预处理");
  const phaseTimer = setInterval(() => {
    if (runningPhase.value < AHE_PHASES.length - 1) runningPhase.value += 1;
  }, 8000);
  try {
    const sample = selectedSample.value;
    const inferArgs = { modelId: modelId.value };
    if (sample.source === "upload") {
      if (isTauri() && lastUploadPath.value) {
        inferArgs.imagePath = lastUploadPath.value;
      } else if (sample.upload_id) {
        inferArgs.uploadId = sample.upload_id;
      } else {
        throw new Error("上传样本缺少 upload_id");
      }
    } else {
      inferArgs.mnistIndex = sample.mnist_index ?? index.value;
    }
    const out = await aheInfer(inferArgs);
    result.value = out;
    timing.value = out.timing;
    state.sessionResult = out;
    state.timing = out.timing;
    state.connectionStatus = "connected";
    if (out.trace?.length) {
      appendSteps(out.trace);
    }
    appendSteps([
      {
        id: "ui_result",
        category: "完成",
        title: "推理结果",
        summary: `prediction=${out.prediction}${out.label != null ? ` label=${out.label}` : ""}`,
        detail: {
          prediction: out.prediction,
          label: out.label,
          logits_float: out.logits,
          argmax: out.prediction,
          num_pt_add: out.num_pt_add,
          num_pt_mult: out.num_pt_mult,
          crypto_infer_ms: out.timing?.crypto_infer_ms,
        },
      },
    ]);
    addLog("完成", `prediction=${out.prediction}`);
  } catch (e) {
    error.value = String(e);
    state.connectionStatus = "error";
  } finally {
    clearInterval(phaseTimer);
    runningPhase.value = AHE_PHASES.length;
    busy.value = false;
  }
}

onMounted(async () => {
  await loadModels();
  await loadGallery(0);
});
</script>

<style scoped>
.gallery {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 8px;
  margin-top: 8px;
}

.gallery-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 6px;
  border: 2px solid #e0e0e0;
  border-radius: 6px;
  background: #fafafa;
  cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s;
}

.gallery-item:hover {
  border-color: #18a058;
}

.gallery-item.selected {
  border-color: #18a058;
  box-shadow: 0 0 0 1px #18a058;
  background: #f0faf4;
}

.gallery-item img {
  width: 56px;
  height: 56px;
  image-rendering: pixelated;
}

.gallery-meta {
  margin-top: 4px;
  font-size: 11px;
  color: #666;
  text-align: center;
  word-break: break-all;
}
</style>
