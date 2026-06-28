<script setup>
import { ref } from "vue";
import { useRouter } from "vue-router";
import {
  NCard,
  NGrid,
  NGi,
  NButton,
  NTag,
  NSpace,
  NAlert,
  useMessage,
} from "naive-ui";
import { useProtocolSession } from "../composables/useProtocolSession.js";
import PageCard from "../components/PageCard.vue";

const router = useRouter();
const message = useMessage();
const { state, markSetupKeysReady, markPrecomputeReady } = useProtocolSession();

const local = ref({ publicKey: "", privateKey: "", precomputeTable: "" });

const workflowSteps = [
  { title: "Setup 密钥", desc: "AHE 参数与预计算表", icon: "🔐" },
  { title: "选择模型", desc: "模型仓库绑定 cm_W", icon: "📦" },
  { title: "推理与验证", desc: "密态推理 + 本地 Verify", icon: "✓" },
];

function downloadTextFile(fileName, content) {
  const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
  const href = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = href;
  a.download = fileName;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(href);
}

function initParams() {
  const stamp = Date.now();
  local.value.publicKey = `AHE-PUB-${stamp}-MOCK`;
  local.value.privateKey = `AHE-PRI-${stamp}-MOCK`;
  markSetupKeysReady();
  message.success("AHE 公私钥已生成（Mock）");
}

function getPrecompute() {
  local.value.precomputeTable = JSON.stringify(
    { keyRef: local.value.publicKey, tableName: "ahe_precompute_table", generatedAt: new Date().toISOString() },
    null,
    2,
  );
  markPrecomputeReady();
  downloadTextFile("ahe_precompute_table.json", local.value.precomputeTable);
  message.success("预计算表已生成并下载");
}

function startWorkflow() {
  if (!state.aheReady) {
    message.warning("请先完成 Setup 参数初始化");
    return;
  }
  router.push("/tasks/new");
}
</script>

<template>
  <div class="home-view">
    <PageCard class="showroom-card">
      <NTag round type="info" :bordered="false">vPIN 论文复现 · 演示</NTag>
      <h1>Hi，欢迎来到 VDS-VPIN 隐私推理工作台</h1>
      <p class="lead">隐私推理，结果可验证 — 在客户端完成挑战与验证，不含大模型训练/在线服务。</p>

      <div class="workflow-strip">
        <template v-for="(step, i) in workflowSteps" :key="step.title">
          <div class="workflow-step">
            <span class="workflow-step__icon">{{ step.icon }}</span>
            <strong>{{ step.title }}</strong>
            <span>{{ step.desc }}</span>
          </div>
          <span v-if="i < workflowSteps.length - 1" class="workflow-arrow">›</span>
        </template>
      </div>

      <NButton type="primary" size="large" class="cta-btn" @click="startWorkflow">
        立即开始推理任务
      </NButton>
    </PageCard>

    <NGrid cols="1 m:2" responsive="screen" :x-gap="16" :y-gap="16">
      <NGi>
        <NCard title="Setup：参数初始化" class="section-card" :bordered="false">
          <div class="panel panel-blue">
            <div class="panel-head">
              <strong>AHE 密钥</strong>
              <NTag size="small" :type="state.aheReady ? 'success' : 'default'">
                {{ state.aheReady ? "已就绪" : "待初始化" }}
              </NTag>
            </div>
            <NSpace wrap>
              <NButton type="primary" @click="initParams">参数初始化</NButton>
              <NButton secondary :disabled="!state.aheReady" @click="downloadTextFile('ahe_public_key.txt', local.publicKey)">下载公钥</NButton>
              <NButton secondary :disabled="!state.aheReady" @click="downloadTextFile('ahe_private_key.txt', local.privateKey)">下载私钥</NButton>
            </NSpace>
            <NAlert v-if="state.aheReady" type="success" :bordered="false" style="margin-top: 12px">Mock 密钥，后续对接真实 AHE Setup</NAlert>
          </div>
          <div class="panel panel-green" style="margin-top: 12px">
            <div class="panel-head">
              <strong>预计算表</strong>
              <NTag size="small" :type="state.precomputeReady ? 'success' : 'warning'">
                {{ state.precomputeReady ? "已生成" : "等待" }}
              </NTag>
            </div>
            <NButton type="primary" :disabled="!state.aheReady" @click="getPrecompute">获取预计算表</NButton>
          </div>
        </NCard>
      </NGi>
      <NGi>
        <NCard title="快捷入口" class="section-card" :bordered="false">
          <NSpace vertical :size="12">
            <NButton block secondary @click="router.push('/models')">模型仓库</NButton>
            <NButton block type="primary" @click="router.push('/tasks/new')">新建推理任务</NButton>
            <NButton block secondary @click="router.push('/tasks')">推理任务列表</NButton>
            <NButton block tertiary @click="router.push('/demo')">进入隐私样板间（图像密态推理）</NButton>
          </NSpace>
        </NCard>
      </NGi>
    </NGrid>
  </div>
</template>

<style scoped>
.home-view {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.showroom-card h1 {
  margin: 12px 0 8px;
  font-size: var(--text-2xl);
  font-weight: 600;
  color: var(--color-text-primary);
}

.lead {
  margin: 0 0 var(--space-5);
  color: var(--color-text-secondary);
  max-width: 640px;
  line-height: 1.6;
}

.workflow-strip {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: wrap;
  padding: var(--space-4);
  background: var(--color-bg);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border);
  margin-bottom: var(--space-5);
}

.workflow-step {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 140px;
  padding: var(--space-3);
  background: var(--color-surface);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border);
}

.workflow-step__icon {
  font-size: 20px;
}

.workflow-step strong {
  font-size: var(--text-sm);
  color: var(--color-text-primary);
}

.workflow-step span:last-child {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
}

.workflow-arrow {
  color: var(--color-text-muted);
  font-size: 20px;
  padding: 0 4px;
}

.cta-btn {
  min-width: 200px;
  background: linear-gradient(135deg, var(--color-primary), var(--color-accent)) !important;
  border: none !important;
}

.section-card {
  box-shadow: var(--shadow-sm);
  height: 100%;
}

.panel {
  border-radius: var(--radius-md);
  padding: var(--space-4);
  border: 1px solid var(--color-border);
}

.panel-blue {
  background: #f8fbff;
}

.panel-green {
  background: #f6fff8;
}

.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-3);
}
</style>
