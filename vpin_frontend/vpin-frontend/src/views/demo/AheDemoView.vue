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

            <!-- 模式切换 -->
            <n-radio-group v-model:value="inferMode" :disabled="busy || batchState.running">
              <n-radio-button value="single">单图模式</n-radio-button>
              <n-radio-button value="batch" :disabled="!isDesktop">批量模式</n-radio-button>
            </n-radio-group>

            <!-- 单图模式 -->
            <template v-if="inferMode === 'single'">
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
            </template>

            <!-- 批量模式 -->
            <template v-else>
              <n-space vertical style="width: 100%">
                <n-alert type="info" style="margin-bottom: 12px">
                  批量评估 test 集前 N 张（从索引 0 开始）
                </n-alert>
                <n-space>
                  <n-input-number
                    v-model:value="batchConfig.limit"
                    :min="1"
                    :max="50"
                    placeholder="张数"
                    style="width: 100px"
                  />
                  <n-input-number
                    v-model:value="batchConfig.concurrency"
                    :min="1"
                    :max="8"
                    placeholder="并发度"
                    style="width: 100px"
                  />
                </n-space>
                <n-button
                  type="primary"
                  :loading="batchState.running"
                  :disabled="!modelId"
                  @click="runBatchInfer"
                >
                  批量评估 {{ batchConfig.limit }} 张（并发={{ batchConfig.concurrency }}）
                </n-button>
                <n-text v-if="!isDesktop" depth="3" style="font-size: 12px">
                  批量 AHE 需在 Tauri 桌面端运行
                </n-text>
              </n-space>
            </template>

            <n-alert v-if="error" type="error">{{ error }}</n-alert>
          </n-space>
        </n-card>

        <!-- 批量进度 -->
        <n-card v-if="batchState.running || batchState.completed" title="批量进度" style="margin-top: 12px">
          <template v-if="batchState.running">
            <n-progress
              type="line"
              :percentage="batchProgress"
              :status="'info'"
              style="margin-bottom: 12px"
            />
            <n-text depth="3" style="font-size: 12px">
              {{ batchState.completedCount }} / {{ batchState.limit }} ·
              正确 {{ batchState.correct }} ·
              准确率 {{ (batchState.accuracy * 100).toFixed(1) }}% ·
              已用 {{ batchState.elapsed }}s ·
              ETA {{ batchState.eta }}s
            </n-text>
          </template>
          <template v-else-if="batchState.completed">
            <n-space vertical>
              <n-statistic :label="'准确率'" :value="`${(batchState.accuracy * 100).toFixed(1)}%`" />
              <n-statistic :label="'总耗时'" :value="`${batchState.totalElapsed}s`" />
              <n-statistic :label="'均摊'" :value="`${(batchState.totalElapsed / batchState.limit).toFixed(1)}s/张`" />
              <n-statistic :label="'并发度'" :value="batchState.concurrency" />
            </n-space>
            <n-button quaternary type="info" @click="exportBatchReport" style="margin-top: 8px">
              导出 JSON
            </n-button>
          </template>
        </n-card>

        <!-- 批量结果 -->
        <n-card v-if="batchState.results.length" title="批量结果" style="margin-top: 12px">
          <n-data-table
            :columns="batchColumns"
            :data="batchState.results"
            :single-line="false"
            :max-height="300"
            @row-click="onBatchRowClick"
          />
        </n-card>
      </n-gi>
    </n-grid>

    <n-card v-if="!batchState.running && inferMode === 'single'" title="推理流程时间线" style="margin-top: 16px">
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
import { computed, onMounted, ref, h } from "vue";
import { useAheDemoSession } from "../../composables/useAheDemoSession.js";
import AheFlowTimeline from "../../components/demo/AheFlowTimeline.vue";
import AheTraceDrawer from "../../components/demo/AheTraceDrawer.vue";
import { AHE_PHASES } from "../../constants/aheFlow.js";
import {
  aheInfer,
  aheBatchInfer,
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
const inferMode = ref("single");
const batchConfig = ref({
  startIndex: 0,
  limit: 10,
  concurrency: 4,
});
const batchState = ref({
  running: false,
  completed: false,
  completedCount: 0,
  limit: 10,
  correct: 0,
  accuracy: 0,
  elapsed: 0,
  eta: 0,
  totalElapsed: 0,
  concurrency: 4,
  results: [],
});

const batchColumns = [
  { title: "序号", key: "mnist_index", width: 80 },
  { title: "标签", key: "label", width: 60 },
  { title: "预测", key: "prediction", width: 60 },
  {
    title: "正确",
    key: "correct",
    width: 80,
    render: (row) => {
      return h(
        "n-tag",
        { type: row.correct ? "success" : "error", size: "small" },
        () => (row.correct ? "✓" : "✗")
      );
    },
  },
];

const batchProgress = computed(() => {
  if (batchState.value.limit === 0) return 0;
  return Math.round((batchState.value.completedCount / batchState.value.limit) * 100);
});

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

async function runBatchInfer() {
  if (!isDesktop || !modelId.value) return;

  batchState.value.running = true;
  batchState.value.completed = false;
  batchState.value.completedCount = 0;
  batchState.value.correct = 0;
  batchState.value.accuracy = 0;
  batchState.value.elapsed = 0;
  batchState.value.eta = 0;
  batchState.value.totalElapsed = 0;
  batchState.value.limit = batchConfig.value.limit;
  batchState.value.concurrency = batchConfig.value.concurrency;
  batchState.value.results = [];
  error.value = null;
  state.connectionStatus = "connecting";

  const startTime = Date.now();

  try {
    const report = await aheBatchInfer({
      startIndex: batchConfig.value.startIndex,
      limit: batchConfig.value.limit,
      concurrency: batchConfig.value.concurrency,
      modelId: modelId.value,
      onProgress: (progress) => {
        batchState.value.completedCount = progress.index;
        batchState.value.correct = progress.correct;
        batchState.value.accuracy = progress.accuracy;
        batchState.value.elapsed = progress.elapsed_s;
        batchState.value.eta = progress.eta_s;
      },
    });

    batchState.value.totalElapsed = Math.round((Date.now() - startTime) / 1000);
    batchState.value.running = false;
    batchState.value.completed = true;

    // Parse results from report
    if (report.results && Array.isArray(report.results)) {
      batchState.value.results = report.results.map((r) => ({
        mnist_index: r.mnist_index,
        label: r.label,
        prediction: r.prediction,
        correct: r.correct,
        logits: r.logits,
      }));
    }

    state.connectionStatus = "connected";
    addLog("批量完成", `准确率 ${(batchState.value.accuracy * 100).toFixed(1)}%`);
  } catch (e) {
    error.value = String(e);
    state.connectionStatus = "error";
    batchState.value.running = false;
  }
}

function onBatchRowClick(row) {
  inferMode.value = "single";
  index.value = row.mnist_index;
  preprocess().then(() => {
    selectSample(gallery.value.find((g) => g.mnist_index === row.mnist_index) || null);
  });
}

function exportBatchReport() {
  const report = {
    config: {
      start_index: batchConfig.value.startIndex,
      limit: batchConfig.value.limit,
      concurrency: batchConfig.value.concurrency,
      model_id: modelId.value,
    },
    results: batchState.value.results,
    summary: {
      total: batchState.value.limit,
      correct: batchState.value.correct,
      accuracy: batchState.value.accuracy,
      total_elapsed_s: batchState.value.totalElapsed,
      avg_time_per_item: batchState.value.totalElapsed / batchState.value.limit,
    },
    timestamp: new Date().toISOString(),
  };

  const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `batch_${batchConfig.value.limit}_${Date.now()}.json`;
  a.click();
  URL.revokeObjectURL(url);

  addLog("导出", `批量报告 ${a.download}`);
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
