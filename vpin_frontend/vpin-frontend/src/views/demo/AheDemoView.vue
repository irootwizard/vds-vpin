<template>

  <div class="ahe-demo">

    <n-page-header title="AHE 密态推理实验室" subtitle="Tauri 桌面端 · pipeline → WebSocket P0–P3" />



    <n-alert

      v-if="!isDesktop"

      type="warning"

      title="推理需桌面端"

      style="margin-bottom: 12px"

    >

      浏览器模式：AHE 预处理与推理均需在 Tauri 桌面端运行（<code>npm run tauri dev</code>）。:8000 仅用于模型列表等元数据 REST。

    </n-alert>



    <n-card title="AHE 密态推理">
      <n-space vertical :size="16">
        <div>
          <n-text strong style="display: block; margin-bottom: 8px">计算栈</n-text>
          <n-radio-group v-model:value="stack" size="medium">
            <n-radio-button value="python">Python · vpin_client</n-radio-button>
            <n-radio-button value="rust">Rust · ahe-cli</n-radio-button>
          </n-radio-group>
        </div>

        <div v-if="stack === 'rust'">
          <n-text strong style="display: block; margin-bottom: 8px">Rust 推理引擎</n-text>
          <n-radio-group v-model:value="rustBackend" size="medium">
            <n-radio-button value="ark">Arkworks · :8001</n-radio-button>
            <n-radio-button value="ec">EC 曲线 · :8002</n-radio-button>
          </n-radio-group>
        </div>

        <n-text depth="3" style="font-size: 12px">{{ enginePreset.description }}</n-text>

        <div>
          <n-text strong style="display: block; margin-bottom: 8px">推理模式</n-text>
          <n-radio-group v-model:value="inferMode" size="medium">
            <n-radio-button value="single">单图</n-radio-button>
            <n-radio-button value="batch">批量</n-radio-button>
          </n-radio-group>
        </div>

        <n-select
          v-model:value="modelId"
          :options="modelOptions"
          placeholder="选择模型"
          :loading="modelsLoading"
        />

        <template v-if="inferMode === 'batch'">
          <n-radio-group v-model:value="batchSource" size="small">
            <n-radio value="range">序号范围</n-radio>
            <n-radio value="multi">画廊多选</n-radio>
          </n-radio-group>
          <n-space v-if="batchSource === 'range'" align="center">
            <n-input-number v-model:value="batchStart" :min="0" :max="9999" size="small" />
            <n-text depth="3">—</n-text>
            <n-input-number v-model:value="batchEnd" :min="0" :max="9999" size="small" />
            <n-text depth="3">共 {{ batchJobCount }} 张</n-text>
          </n-space>
          <n-text v-else depth="3" style="font-size: 12px">
            在下方画廊 Ctrl/Shift 多选样本（已选 {{ multiSelectCount }}）
          </n-text>
          <n-space align="center">
            <span style="font-size: 12px">并发</span>
            <n-input-number v-model:value="batchConcurrency" :min="1" :max="16" size="small" style="width: 100px" />
            <n-text depth="3" style="font-size: 11px">并发 WebSocket 会话数，建议 ≤ 服务端 CPU 核数</n-text>
          </n-space>
          <n-select
            v-model:value="traceMode"
            :options="traceModeOptions"
            size="small"
            placeholder="Trace 模式"
          />
        </template>

        <n-divider style="margin: 4px 0">数据预处理</n-divider>

        <n-space align="center" justify="space-between">
          <n-text depth="3" style="font-size: 12px">
            本地预处理 · 明文不出机 · Tauri 子进程 + WebSocket 推理
          </n-text>
          <n-tag size="small" :type="stack === 'python' ? 'info' : 'warning'">
            {{ preprocessBackendLabel }}
          </n-tag>
        </n-space>

        <n-alert v-if="!isDesktop" type="info" size="small" :bordered="false">
          预处理与推理需在 Tauri 桌面端运行（<code>npm run tauri dev</code>）。
        </n-alert>

        <n-space v-else vertical>
          <n-input-number v-model:value="index" :min="0" :max="9999" />
          <n-space>
            <n-button :loading="preprocessBusy" @click="preprocessCurrent">预处理当前序号</n-button>
            <n-button :loading="galleryLoading" quaternary @click="loadGallery">刷新预览</n-button>
          </n-space>
          <n-upload
            :show-file-list="false"
            accept="image/*"
            :disabled="uploadLoading"
            @change="onUploadChange"
          >
            <n-button :loading="uploadLoading" size="small">上传图片并预处理</n-button>
          </n-upload>
          <PreprocessGallery
            :items="currentGallery"
            :loading="galleryLoading"
            :lane="activeLane"
            :multi-select="inferMode === 'batch' && batchSource === 'multi'"
            :is-selected="(item) => isSelected(activeLane, item)"
            :is-multi-selected="(item) => isMultiSelected(activeLane, item)"
            :format-meta="formatMeta"
            :sample-key="sampleKey"
            @select="(item, mods) => onGallerySelect(activeLane, item, mods)"
          />
        </n-space>

        <n-button
          v-if="inferMode === 'single'"
          type="primary"
          :loading="inferBusy"
          :disabled="!canRunAheInfer || inferBusy || batchBusy"
          @click="runInfer"
        >
          运行 AHE 推理（{{ inferLabel }}）
        </n-button>
        <n-alert
          v-if="inferBusy && inferMode === 'single'"
          type="info"
          :bordered="false"
          size="small"
        >
          推理进行中（约 15–70s），请勿重复点击、切换样本/引擎或离开本页。
        </n-alert>
        <n-button
          v-else-if="inferMode === 'batch'"
          type="primary"
          :loading="batchBusy"
          :disabled="!canRunBatch || batchBusy || inferBusy"
          @click="runBatch"
        >
          运行批量推理 ({{ batchJobCount }} 张)
        </n-button>

        <n-text v-if="!canRunAheInfer && !modelsLoading && inferMode === 'single'" depth="3" style="font-size: 12px">
          <template v-if="!isDesktop">请使用 Tauri 桌面端以运行推理。</template>
          <template v-else-if="!selectedSample?.input_digest_hex">请先在上方预处理并选择样本。</template>
          <template v-else>请确认后端已启动且权重已注册。</template>
        </n-text>

        <div v-if="result && inferMode === 'single'">
          <p>
            预测: {{ result.prediction }}
            <span v-if="result.label != null"> / 标签: {{ result.label }}</span>
            <n-tag v-if="result.infer_engine" size="tiny" style="margin-left: 6px">
              {{ result.infer_engine }}
            </n-tag>
          </p>
        </div>

        <AheTimingPanel v-if="inferMode === 'single'" :timing="timing" :engine-label="enginePreset.label" />
        <n-alert v-if="error" type="error">{{ error }}</n-alert>
      </n-space>
    </n-card>



    <n-card :title="inferMode === 'batch' ? '批量推理进度' : '推理流程时间线'" style="margin-top: 16px">
      <template #header-extra>
        <n-space align="center" :size="8">
          <n-tag size="small" :type="stack === 'python' ? 'info' : 'warning'">
            {{ stack === 'python' ? 'Python 栈' : `Rust · ${rustBackend === 'ec' ? 'EC' : 'Ark'}` }}
          </n-tag>
          <n-text depth="3" style="font-size: 12px">
            {{ inferMode === 'batch' ? '顶栏 Network A 阶段随 focus job 推进' : '点击各阶段查看张量形状、密文形式与截断参数' }}
          </n-text>
        </n-space>
      </template>

      <template v-if="inferMode === 'batch'">
        <AheBatchProgressHeader
          :meta="batchMeta"
          :progress-pct="batchProgressPct"
          :running-phase="batchRunningPhase"
          :running="batchActive"
          :engine-label="enginePreset.label"
          :focus-job-id="focusJobId"
        />
        <n-text
          v-if="batchCompact && batchActive"
          depth="3"
          style="font-size: 12px; display: block; margin-top: 8px"
        >
          大批量模式（>{{ LARGE_BATCH_THRESHOLD }} 张）：顶栏进度条实时更新；下表仅显示最近 {{ 100 }} 项，完整结果见底部报告。
        </n-text>
        <AheBatchItemTable
          :items="batchItems"
          :focus-job-id="focusJobId"
          style="margin-top: 12px"
          @focus="onBatchRowFocus"
        />
        <AheFlowTimeline
          v-if="batchActive || batchReport"
          :steps="batchFlowSteps"
          :running="batchActive"
          :running-phase="batchRunningPhase"
          :engine-label="enginePreset.label"
          style="margin-top: 12px"
          @select="openStepDetail"
        />
        <AheBatchReportPanel v-if="batchReport" :report="batchReport" style="margin-top: 12px" />
      </template>
      <AheFlowTimeline
        v-else
        :steps="flowSteps"
        :running="inferBusy"
        :running-phase="runningPhase"
        :engine-label="enginePreset.label"
        @select="openStepDetail"
      />
    </n-card>



    <AheTraceDrawer v-model:show="drawerOpen" :step="selectedStep" />

  </div>

</template>



<script setup>

import { computed, onMounted, ref, watch } from "vue";

import { useRoute } from "vue-router";

import { useAheDemoSession } from "../../composables/useAheDemoSession.js";

import { useAheInferTimeline } from "../../composables/useAheInferTimeline.js";
import { useAheBatchTimeline, LARGE_BATCH_THRESHOLD } from "../../composables/useAheBatchTimeline.js";
import AheBatchProgressHeader from "../../components/demo/AheBatchProgressHeader.vue";
import AheBatchItemTable from "../../components/demo/AheBatchItemTable.vue";
import AheBatchReportPanel from "../../components/demo/AheBatchReportPanel.vue";


import { useAhePreprocessLanes } from "../../composables/useAhePreprocessLanes.js";

import AheFlowTimeline from "../../components/demo/AheFlowTimeline.vue";

import AheTraceDrawer from "../../components/demo/AheTraceDrawer.vue";

import AheTimingPanel from "../../components/demo/AheTimingPanel.vue";

import PreprocessGallery from "../../components/demo/PreprocessGallery.vue";

import {

  aheBatchInfer,
  aheInfer,
  fetchAheModels,
  jobIdFor,
  jobKeysForRange,
  jobsFromRange,
  jobsFromSelectedSamples,

  getEnginePreset,

  inferEngineFromStack,

  stackFromInferEngine,

  isTauri,

  loadSavedInferEngine,

  pythonPreprocessBatch,

  pythonPreprocessOfficial,

  pythonPreprocessUpload,

  rustPreprocessOfficial,
  rustPreprocessBatch,
  rustPreprocessUpload,

  saveInferEngine,

} from "../../services/aheClient.js";



const PREVIEW_COUNT = 10;

const FALLBACK_MODEL_ID = "cnn-mnist-trained";

const FALLBACK_MODEL_OPTION = {

  label: "CNN MNIST Network A (trained)",

  value: FALLBACK_MODEL_ID,

};



const isDesktop = isTauri();

const route = useRoute();

const initialStack = stackFromInferEngine(loadSavedInferEngine());

const stack = ref(initialStack.stack);

const rustBackend = ref(initialStack.rustBackend);

const inferEngine = computed(() => inferEngineFromStack(stack.value, rustBackend.value));

const { state, log: pushLog } = useAheDemoSession();

const {

  lanes,

  index,

  activeLane,

  selectedSample,

  sampleKey,

  isSelected,

  formatMeta,

  upsertGalleryItem,

  applySelection,

  selectSample,

  setGallery,

  pickDefaultSelection,
  isMultiSelected,
  clearMultiSelect,
  getMultiSelectedSamples,
  toggleMultiSelect,
} = useAhePreprocessLanes(inferEngine);



const {

  flowSteps,

  runningPhase,

  beginInfer,

  endInfer,

  resetTimeline,

  mergePreprocessTrace,

  queueSteps,

  bumpPhase,

} = useAheInferTimeline(activeLane);

const {
  batchActive,
  batchCompact,
  batchMeta,
  items: batchItems,
  focusJobId,
  runningPhase: batchRunningPhase,
  flowSteps: batchFlowSteps,
  report: batchReport,
  progressPct: batchProgressPct,
  beginBatch,
  endBatch,
  resetBatch,
  setFocus,
  applyBatchReport,
} = useAheBatchTimeline();

const inferMode = ref("single");
const batchSource = ref("range");
const batchStart = ref(1000);
const batchEnd = ref(1004);
const batchConcurrency = ref(2);
const traceMode = ref("focus");
const batchBusy = ref(false);

const traceModeOptions = computed(() => {
  const opts = [
    { label: "无 Trace", value: "none" },
    { label: "聚焦项", value: "focus" },
    { label: "全部", value: "all" },
  ];
  return batchConcurrency.value > 1 ? opts.filter((o) => o.value !== "all") : opts;
});

const enginePreset = computed(() => getEnginePreset(inferEngine.value));

const preprocessBackendLabel = computed(() =>
  stack.value === "python" ? "vpin_client" : "ahe-cli · mnist_official"
);

const currentGallery = computed(() => lanes[activeLane.value].gallery);

const galleryLoading = computed(() =>
  stack.value === "python" ? pythonGalleryLoading.value : rustGalleryLoading.value
);

const preprocessBusy = computed(() =>
  stack.value === "python" ? pythonBusy.value : rustBusy.value
);

const uploadLoading = computed(() =>
  stack.value === "python" ? pythonUploadLoading.value : rustUploadLoading.value
);

const modelId = ref("");

const modelOptions = ref([]);

const modelsLoading = ref(false);

const pythonGalleryLoading = ref(false);

const rustGalleryLoading = ref(false);

const pythonUploadLoading = ref(false);

const rustUploadLoading = ref(false);

const pythonBusy = ref(false);

const rustBusy = ref(false);

const inferBusy = ref(false);

const result = ref(null);

const timing = ref(null);

const error = ref(null);

const selectedStep = ref(null);

const drawerOpen = ref(false);



const canRunAheInfer = computed(() => {

  if (!isDesktop || !selectedSample.value?.input_digest_hex || !modelId.value) return false;
  return true;

});

const batchJobCount = computed(() => {
  if (batchSource.value === "range") {
    const lo = Math.min(batchStart.value, batchEnd.value);
    const hi = Math.max(batchStart.value, batchEnd.value);
    return Math.max(0, hi - lo + 1);
  }
  return getMultiSelectedSamples(activeLane.value).length;
});

const multiSelectCount = computed(() => getMultiSelectedSamples(activeLane.value).length);

const canRunBatch = computed(() => {
  if (!isDesktop || !modelId.value || batchJobCount.value <= 0) return false;
  if (traceMode.value === "all" && batchConcurrency.value > 1) return false;
  return true;
});



watch(inferMode, (mode) => {
  if (mode === "batch") {
    resetBatch();
  }
});

function syncPreprocessTrace() {
  const lane = activeLane.value;
  const sel = lanes[lane].selectedSample;
  if (sel) {
    state.preprocessResult = sel;
    mergePreprocessTrace(sel, lane);
  }
}

watch([stack, rustBackend], () => {
  saveInferEngine(inferEngine.value);
  resetTimeline(activeLane.value, true);
  syncPreprocessTrace();
});

watch(stack, (lane) => {
  if (isDesktop && !lanes[lane].gallery.length) {
    loadGallery();
  }
});



const inferLabel = computed(() => {

  if (!selectedSample.value) return "—";

  if (selectedSample.value.source === "upload") {

    return selectedSample.value.filename || selectedSample.value.upload_id?.slice(0, 8);

  }

  return `#${selectedSample.value.mnist_index}`;

});



function nowStr() {

  return new Date().toLocaleTimeString();

}



function openStepDetail(step) {

  selectedStep.value = step;

  drawerOpen.value = true;

}



function addLog(title, content) {

  pushLog({ title, content, at: nowStr() });

}



function resolveModelId(options, preferredId) {

  const ids = new Set(options.map((o) => o.value));

  const candidates = [

    preferredId,

    route.query.model,

    modelId.value,

    FALLBACK_MODEL_ID,

    options[0]?.value,

  ].filter(Boolean);

  for (const id of candidates) {

    if (ids.has(id)) return id;

  }

  return FALLBACK_MODEL_ID;

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

    if (modelOptions.value.length) {

      modelId.value = resolveModelId(modelOptions.value, route.query.model);

    } else if (!modelId.value) {

      modelId.value = FALLBACK_MODEL_ID;

    }

  } catch (e) {

    modelOptions.value = [FALLBACK_MODEL_OPTION];

    modelId.value = FALLBACK_MODEL_ID;

    error.value = `模型列表加载失败: ${e}`;

  } finally {

    modelsLoading.value = false;

  }

}



async function loadGallery(start = 0) {
  if (stack.value === "python") {
    await loadPythonGallery(start);
  } else {
    await loadRustGallery(start);
  }
}

async function preprocessCurrent() {
  if (stack.value === "python") {
    await preprocessPython();
  } else {
    await preprocessRust();
  }
}

async function loadPythonGallery(start = 0) {
  if (!isDesktop) return;
  pythonGalleryLoading.value = true;
  error.value = null;
  try {
    const batch = await pythonPreprocessBatch(start, PREVIEW_COUNT);
    const official = (batch.items || []).map((item) => ({ ...item, source: "official" }));
    setGallery("python", official);
    pickDefaultSelection("python", index.value);
    const sel = lanes.python.selectedSample;
    if (sel) {
      state.preprocessResult = sel;
      mergePreprocessTrace(sel, "python");
    }
    addLog("Python 数据", `本地 ${official.length} 张 (start=${start})`);
  } catch (e) {
    error.value = String(e);
    state.connectionStatus = "error";
  } finally {
    pythonGalleryLoading.value = false;
  }
}



async function loadRustGallery(start = 0) {
  if (!isDesktop) return;
  rustGalleryLoading.value = true;
  error.value = null;
  try {
    const batch = await rustPreprocessBatch(start, PREVIEW_COUNT);
    const official = (batch.items || []).map((item) => ({ ...item, source: "official" }));
    setGallery("rust", official);
    pickDefaultSelection("rust", index.value);
    const sel = lanes.rust.selectedSample;
    if (sel) {
      state.preprocessResult = sel;
      mergePreprocessTrace(sel, "rust");
    }
    addLog("Rust 数据", `本地 ${official.length} 张 (start=${start})`);
  } catch (e) {
    error.value = String(e);
  } finally {
    rustGalleryLoading.value = false;
  }
}




function onGallerySelect(lane, item, mods = {}) {
  if (inferMode.value === "batch" && batchSource.value === "multi") {
    toggleMultiSelect(lane, item, { additive: mods.ctrl, range: mods.shift });
    return;
  }
  selectSampleWithTrace(lane, item);
}

function onBatchRowFocus(row) {
  setFocus(row.jobId);
  const last = batchFlowSteps.value[batchFlowSteps.value.length - 1];
  if (last) {
    selectedStep.value = last;
    drawerOpen.value = true;
  }
}

function selectSampleWithTrace(lane, item) {

  selectSample(lane, item);

  state.preprocessResult = item;

  state.selectedIndex = item.mnist_index ?? index.value;

  if (lane === activeLane.value) {

    mergePreprocessTrace(item, lane);

  }

}



async function preprocessPython() {
  if (!isDesktop) return;
  pythonBusy.value = true;

  error.value = null;

  try {

    const prep = await pythonPreprocessOfficial(index.value);

    const item = { ...prep, source: "official" };

    upsertGalleryItem("python", item);

    applySelection("python", item);

    mergePreprocessTrace(item, "python");

    addLog("Python 预处理", `本地 index=${index.value}`);

  } catch (e) {

    error.value = String(e);

    state.connectionStatus = "error";

  } finally {

    pythonBusy.value = false;

  }

}



async function preprocessRust() {

  if (!isDesktop) return;

  rustBusy.value = true;

  error.value = null;

  try {

    const prep = await rustPreprocessOfficial(index.value);

    const item = { ...prep, source: "official" };

    upsertGalleryItem("rust", item);

    applySelection("rust", item);

    mergePreprocessTrace(item, "rust");

    addLog("Rust 预处理", `ahe-cli index=${index.value}`);

  } catch (e) {

    error.value = String(e);

  } finally {

    rustBusy.value = false;

  }

}



async function onUploadChange({ file }) {
  return onUploadChangeLane(activeLane.value, { file });
}

async function onUploadChangeLane(lane, { file }) {
  if (!isDesktop) return;

  const raw = file?.file;

  if (!raw) return;

  const loading = lane === "python" ? pythonUploadLoading : rustUploadLoading;

  loading.value = true;

  error.value = null;

  try {
    const path = raw.path;
    if (!path) throw new Error("Tauri 需要本地文件路径");
    lanes[lane].lastUploadPath = path;
    const prep =
      lane === "python"
        ? await pythonPreprocessUpload(path)
        : await rustPreprocessUpload(path);

    const item = { ...prep, source: "upload", local_path: path };

    upsertGalleryItem(lane, item);
    applySelection(lane, item);
    mergePreprocessTrace(item, lane);

    addLog(`${lane === "python" ? "Python" : "Rust"} 上传`, prep.filename || "image");

  } catch (e) {

    error.value = String(e);

  } finally {

    loading.value = false;

  }

}



async function runInfer() {

  if (!canRunAheInfer.value || inferBusy.value || batchBusy.value) return;

  inferBusy.value = true;

  error.value = null;

  result.value = null;

  timing.value = null;

  state.connectionStatus = "connecting";

  const preset = enginePreset.value;

  const lane = activeLane.value;

  await beginInfer({

    lane,

    engine: inferEngine.value,

    engineLabel: preset.label,

    backend: preset.ws,

    modelId: modelId.value,

  });

  try {

    const sample = selectedSample.value;

    const inferArgs = {

      modelId: modelId.value,

      inferEngine: inferEngine.value,

    };

    if (sample.source === "upload") {

      if (lane === "rust" && lanes.rust.lastUploadPath) {

        inferArgs.imagePath = lanes.rust.lastUploadPath;

      } else if (lane === "python" && lanes.python.lastUploadPath && isDesktop) {

        inferArgs.imagePath = lanes.python.lastUploadPath;

      } else if (sample.upload_id) {

        inferArgs.uploadId = sample.upload_id;

      } else {

        throw new Error("上传样本缺少 upload_id 或本地路径");

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

      const existing = new Set(flowSteps.value.map((s) => s.id));

      const missing = out.trace.filter((step) => !existing.has(step.id));

      if (missing.length) {

        queueSteps(missing);

        for (const step of missing) bumpPhase(step);

      }

    }

    queueSteps([

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

          infer_engine: out.infer_engine || inferEngine.value,

        },

        lane,

      },

    ]);

    addLog("完成", `prediction=${out.prediction} engine=${out.infer_engine || inferEngine.value}`);

  } catch (e) {

    error.value = String(e);

    state.connectionStatus = "error";

  } finally {

    endInfer();

    inferBusy.value = false;

  }

}




async function runBatch() {
  if (!canRunBatch.value || batchBusy.value || inferBusy.value) return;
  batchBusy.value = true;
  error.value = null;
  resetBatch();
  state.connectionStatus = "connecting";

  const preset = enginePreset.value;
  const lane = activeLane.value;
  let jobCount = 0;
  let mnistStart;
  let mnistEnd;
  let jobs;
  try {
    if (batchSource.value === "range") {
      const lo = Math.min(batchStart.value, batchEnd.value);
      const hi = Math.max(batchStart.value, batchEnd.value);
      jobCount = Math.max(0, hi - lo + 1);
      mnistStart = lo;
      mnistEnd = hi;
      if (jobCount <= LARGE_BATCH_THRESHOLD) {
        jobs = jobsFromRange(lo, hi);
      }
    } else {
      const samples = getMultiSelectedSamples(lane);
      jobs = jobsFromSelectedSamples(samples, lane, lanes);
      jobCount = jobs.length;
    }
  } catch (e) {
    error.value = String(e);
    batchBusy.value = false;
    return;
  }

  const compact = jobCount > LARGE_BATCH_THRESHOLD;
  const effectiveTrace =
    traceMode.value === "all" && batchConcurrency.value > 1 ? "focus" : traceMode.value;

  await beginBatch({
    jobCount,
    jobKeys: compact
      ? undefined
      : jobs
        ? jobs.map(jobIdFor)
        : jobKeysForRange(mnistStart, mnistEnd),
    compact,
    concurrency: batchConcurrency.value,
    engine: inferEngine.value,
    modelId: modelId.value,
  });

  try {
    const out = await aheBatchInfer({
      jobs,
      mnistStart,
      mnistEnd,
      modelId: modelId.value,
      inferEngine: inferEngine.value,
      concurrency: batchConcurrency.value,
      traceMode: effectiveTrace,
    });
    state.connectionStatus = "connected";
    applyBatchReport(out);
    addLog("批量完成", `acc=${((out.accuracy ?? 0) * 100).toFixed(1)}% n=${out.limit ?? jobCount}`);
  } catch (e) {
    error.value = String(e);
    state.connectionStatus = "error";
  } finally {
    if (batchActive.value) {
      endBatch();
    }
    batchBusy.value = false;
  }
}


onMounted(async () => {
  await loadModels();
  if (isDesktop) {
    await loadGallery(0);
  }
});

</script>


