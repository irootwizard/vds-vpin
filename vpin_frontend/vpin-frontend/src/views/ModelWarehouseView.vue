<script setup>
import { ref, computed, onMounted, h } from "vue";
import { useRouter } from "vue-router";
import {
  NInput,
  NButton,
  NDataTable,
  NTag,
  NSpace,
  NUpload,
  NModal,
  NForm,
  NFormItem,
  NSelect,
  useMessage,
} from "naive-ui";
import PageCard from "../components/PageCard.vue";
import { fetchModels, uploadModel } from "../services/vpinApi";

const router = useRouter();
const message = useMessage();
const keyword = ref("");
const models = ref([]);
const loading = ref(false);
const showUpload = ref(false);
const uploading = ref(false);

const uploadForm = ref({
  modelId: "",
  name: "",
  network: "A",
  file: null,
});

const networkOptions = [
  { label: "Network A (64→16→10)", value: "A" },
  { label: "Network B (64→32→10)", value: "B" },
  { label: "Network C (256→16→10)", value: "C" },
  { label: "Network D", value: "D" },
  { label: "Network E", value: "E" },
];

async function loadModels() {
  loading.value = true;
  try {
    models.value = await fetchModels();
  } catch (e) {
    message.error(`加载失败: ${e.message}`);
  } finally {
    loading.value = false;
  }
}

onMounted(loadModels);

const columns = [
  { title: "ID", key: "id", width: 160 },
  { title: "名称", key: "name" },
  { title: "框架", key: "framework", width: 100 },
  {
    title: "cm_W",
    key: "commitment_digest",
    render: (row) =>
      h("code", { class: "mono" }, row.commitment_digest ? `${row.commitment_digest.slice(0, 12)}…` : "—"),
  },
  {
    title: "操作",
    key: "actions",
    width: 180,
    render: (row) =>
      h(
        NSpace,
        { size: 8 },
        {
          default: () => [
            h(
              NButton,
              {
                size: "small",
                type: "primary",
                secondary: true,
                onClick: () => router.push({ path: "/demo/ahe", query: { model: row.id } }),
              },
              () => "AHE 推理",
            ),
          ],
        },
      ),
  },
];

const filtered = computed(() =>
  models.value.filter(
    (m) =>
      !keyword.value ||
      m.name?.toLowerCase().includes(keyword.value.toLowerCase()) ||
      m.id?.toLowerCase().includes(keyword.value.toLowerCase()),
  ),
);

function onFileChange({ file }) {
  uploadForm.value.file = file?.file || null;
}

async function submitUpload() {
  const { modelId, name, network, file } = uploadForm.value;
  if (!modelId || !name || !file) {
    message.warning("请填写 model_id、名称并选择文件");
    return;
  }
  uploading.value = true;
  try {
    const res = await uploadModel({ modelId, name, network, file });
    message.success(`已注册: ${res.storage_path || modelId}`);
    showUpload.value = false;
    await loadModels();
  } catch (e) {
    message.error(String(e.message || e));
  } finally {
    uploading.value = false;
  }
}
</script>

<template>
  <PageCard>
    <div class="page-head">
      <div>
        <h1 class="page-title">模型仓库</h1>
        <p class="page-desc">
          对接 GET/POST /api/v1/models。AHE 推理请上传 <strong>npy 权重 zip</strong>（见文档）；CP-SNARK 路径可传 model_export.json。
        </p>
      </div>
      <NSpace>
        <NButton @click="loadModels" :loading="loading">刷新</NButton>
        <NButton type="primary" @click="showUpload = true">上传注册</NButton>
      </NSpace>
    </div>

    <NTag size="small" type="info" :bordered="false" style="margin-bottom: 16px">
      支持格式：.zip（4×npy AHE 包，Network A–E 文件名见 weights_layout）· .json（model_export.json）
    </NTag>

    <div class="toolbar">
      <NInput v-model:value="keyword" placeholder="搜索模型" clearable style="width: 240px" />
    </div>

    <NDataTable :columns="columns" :data="filtered" :loading="loading" size="small" :bordered="false" />

    <NModal v-model:show="showUpload" title="注册模型" preset="card" style="width: 480px">
      <NForm label-placement="left" label-width="90">
        <NFormItem label="model_id">
          <NInput v-model:value="uploadForm.modelId" placeholder="cnn-mnist-trained" />
        </NFormItem>
        <NFormItem label="名称">
          <NInput v-model:value="uploadForm.name" placeholder="CNN MNIST A" />
        </NFormItem>
        <NFormItem label="网络">
          <NSelect v-model:value="uploadForm.network" :options="networkOptions" />
        </NFormItem>
        <NFormItem label="权重文件">
          <NUpload :max="1" @change="onFileChange">
            <NButton>选择 .zip 或 .json</NButton>
          </NUpload>
        </NFormItem>
      </NForm>
      <template #footer>
        <NButton @click="showUpload = false">取消</NButton>
        <NButton type="primary" :loading="uploading" @click="submitUpload">上传</NButton>
      </template>
    </NModal>
  </PageCard>
</template>

<style scoped>
.page-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 16px;
}
.page-title {
  margin: 0 0 8px;
  font-size: 1.5rem;
}
.page-desc {
  margin: 0;
  color: var(--n-text-color-3);
  max-width: 640px;
}
.toolbar {
  margin-bottom: 16px;
}
.mono {
  font-size: 12px;
}
</style>
