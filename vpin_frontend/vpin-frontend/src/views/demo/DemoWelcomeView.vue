<script setup>
import { ref } from "vue";
import { useRouter } from "vue-router";
import { NButton, NTag } from "naive-ui";
import PageCard from "../../components/PageCard.vue";
import ServiceNoticeModal from "../../components/demo/ServiceNoticeModal.vue";
import { useDemoStore } from "../../composables/useDemoStore.js";

const router = useRouter();
const { hasAgreedNotice, agreeNotice } = useDemoStore();

const showNotice = ref(false);

const steps = [
  { title: "部署演示服务", desc: "选择论文 CNN/LeNet 模型", icon: "🛰️" },
  { title: "进入隐私体验", desc: "排队就绪后上传图像推理", icon: "🖼️" },
  { title: "查看密态效果", desc: "密文/明文对照与验证说明", icon: "🔐" },
];

function onExecute() {
  if (!hasAgreedNotice()) {
    showNotice.value = true;
    return;
  }
  router.push("/demo/deploy");
}

function onAgree() {
  agreeNotice();
  showNotice.value = false;
  router.push("/demo/deploy");
}
</script>

<template>
  <PageCard class="welcome-card">
    <NTag round type="info" :bordered="false">隐私样板间</NTag>
    <h1>Hi，欢迎来到 VDS-VPIN 隐私推理样板间</h1>
    <p class="lead">
      零成本体验 vPIN 图像密态推理：部署内置 CNN/LeNet 演示服务，上传 28×28 图像查看
      <strong>加密输入、密态计算与推理结果</strong>，并可对照密文形态（Mock，非大模型对话商用）。
    </p>

    <div class="workflow-strip">
      <template v-for="(step, i) in steps" :key="step.title">
        <div class="workflow-step">
          <span class="icon">{{ step.icon }}</span>
          <strong>{{ step.title }}</strong>
          <span>{{ step.desc }}</span>
        </div>
        <span v-if="i < steps.length - 1" class="arrow">›</span>
      </template>
    </div>

    <NButton type="primary" size="large" class="cta" @click="onExecute">立即执行</NButton>

    <ServiceNoticeModal v-model:show="showNotice" @agree="onAgree" />
  </PageCard>
</template>

<style scoped>
.welcome-card {
  text-align: center;
  max-width: 880px;
  margin: 0 auto;
}

h1 {
  margin: 12px 0 8px;
  font-size: 22px;
  font-weight: 600;
}

.lead {
  margin: 0 auto 24px;
  max-width: 640px;
  color: var(--color-text-secondary);
  line-height: 1.7;
  font-size: 14px;
}

.workflow-strip {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 28px;
  padding: 16px;
  background: var(--color-bg);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border);
}

.workflow-step {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  min-width: 140px;
  padding: 12px;
  background: var(--color-surface);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border);
}

.workflow-step .icon {
  font-size: 22px;
}

.workflow-step strong {
  font-size: 13px;
}

.workflow-step span:last-child {
  font-size: 11px;
  color: var(--color-text-secondary);
}

.arrow {
  color: var(--color-text-muted);
  font-size: 18px;
}

.cta {
  min-width: 200px;
  background: linear-gradient(135deg, #4f6ef7, #7c5cff) !important;
  border: none !important;
}
</style>
