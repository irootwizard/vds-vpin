<script setup>
import { ref } from "vue";
import { useRouter } from "vue-router";
import { NButton, NForm, NFormItem, NInput, NSelect, NIcon, useMessage } from "naive-ui";
import { ArrowBackOutline } from "@vicons/ionicons5";
import PageCard from "../../components/PageCard.vue";
import { useDemoStore } from "../../composables/useDemoStore.js";

const router = useRouter();
const message = useMessage();
const { DEMO_MODELS, createSession } = useDemoStore();

const form = ref({
  name: `vpin_demo_${Date.now().toString(36).slice(-6)}`,
  modelId: "cnn-a",
  ttlHours: 24,
});

const ttlOptions = [
  { label: "24 小时", value: 24 },
  { label: "12 小时", value: 12 },
  { label: "6 小时", value: 6 },
];

function deploy() {
  const name = form.value.name.trim();
  if (!/^[a-zA-Z][a-zA-Z0-9_]{0,49}$/.test(name)) {
    message.warning("服务名称：英文/数字/下划线，不能以数字开头，≤50 字符");
    return;
  }
  const session = createSession({
    name,
    modelId: form.value.modelId,
    ttlHours: form.value.ttlHours,
  });
  message.success("演示服务已创建，进入排队…");
  router.push(`/demo/session/${session.id}`);
}
</script>

<template>
  <PageCard class="deploy-card">
    <NButton quaternary class="back" @click="router.push('/demo')">
      <template #icon><NIcon><ArrowBackOutline /></NIcon></template>
      返回
    </NButton>

    <h1>部署演示服务</h1>
    <p class="sub">选择 vPIN 论文内置 CNN/LeNet 模型（非 ChatGLM 等大模型）</p>

    <NForm label-placement="top" class="form">
      <NFormItem label="服务名称" required>
        <NInput v-model:value="form.name" placeholder="英文、数字、下划线；≤50 字符" />
      </NFormItem>

      <NFormItem label="选择模型" required>
        <div class="model-cards">
          <button
            v-for="m in DEMO_MODELS"
            :key="m.id"
            type="button"
            class="model-card"
            :class="{ active: form.modelId === m.id }"
            @click="form.modelId = m.id"
          >
            <div class="model-card__icon">{{ m.icon }}</div>
            <div>
              <strong>{{ m.name }}</strong>
              <span class="ver">{{ m.version }}</span>
              <p>{{ m.desc }}</p>
            </div>
          </button>
        </div>
      </NFormItem>

      <NFormItem label="服务有效期">
        <NSelect v-model:value="form.ttlHours" :options="ttlOptions" style="width: 160px" />
      </NFormItem>

      <NButton type="primary" size="large" class="deploy-btn" @click="deploy">立即部署</NButton>
    </NForm>
  </PageCard>
</template>

<style scoped>
.deploy-card {
  max-width: 720px;
  margin: 0 auto;
}

.back {
  margin-bottom: 8px;
}

h1 {
  margin: 0 0 4px;
  font-size: 20px;
}

.sub {
  margin: 0 0 20px;
  color: var(--color-text-secondary);
  font-size: 13px;
}

.model-cards {
  display: grid;
  gap: 12px;
  width: 100%;
}

.model-card {
  display: flex;
  gap: 14px;
  text-align: left;
  padding: 14px;
  border: 2px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  cursor: pointer;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.model-card.active {
  border-color: #4f6ef7;
  box-shadow: 0 0 0 3px rgba(79, 110, 247, 0.15);
}

.model-card__icon {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: linear-gradient(135deg, #4f6ef7, #7c5cff);
  color: #fff;
  font-weight: 700;
  display: grid;
  place-items: center;
  flex-shrink: 0;
}

.model-card strong {
  display: block;
  font-size: 14px;
}

.ver {
  font-size: 11px;
  color: var(--color-text-muted);
  margin-left: 6px;
}

.model-card p {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--color-text-secondary);
  line-height: 1.5;
}

.deploy-btn {
  margin-top: 8px;
  background: linear-gradient(135deg, #4f6ef7, #7c5cff) !important;
  border: none !important;
}
</style>
