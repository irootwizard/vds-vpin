<script setup lang="ts">
import { computed } from "vue";
import { useRouter } from "vue-router";
import { NButton, NTag, NGrid, NGi, NCard, NSpace, NSpin } from "naive-ui";
import { usePlatformConnect } from "@/composables/usePlatformConnect";
import HomomorphicGovernancePanel from "@/components/governance/HomomorphicGovernancePanel.vue";
import PageCard from "@/components/PageCard.vue";
import { PLATFORM_NAME } from "@/constants/nav";

const router = useRouter();
const platform = usePlatformConnect();
const bootstrap = computed(() => platform.bootstrapResult.value);
const loading = computed(() => !platform.bridgeReady.value);

const workflowSteps = [
  { title: "Setup 密钥", desc: "AHE 参数与预计算表", icon: "🔐" },
  { title: "选择模型", desc: "模型仓库绑定 cm_W", icon: "📦" },
  { title: "推理与验证", desc: "密态推理 + 客户端 Verify", icon: "✓" },
];

</script>

<template>
  <div class="home-view">
    <PageCard class="showroom-card">
      <NTag round type="info" :bordered="false">可验证隐私推理</NTag>
      <h1>Hi，欢迎来到{{ PLATFORM_NAME }}工作台</h1>
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

      <NButton type="primary" size="large" class="cta-btn" @click="router.push('/runs/new')">
        新建推理任务
      </NButton>
    </PageCard>

    <HomomorphicGovernancePanel />

    <NSpin :show="loading">
      <NGrid v-if="bootstrap" cols="1 m:3" responsive="screen" :x-gap="16" :y-gap="16">
        <NGi>
          <NCard title="设备画像" :bordered="false" class="section-card">
            <div class="panel panel-blue">
              <div>{{ bootstrap.device_profile.device_category }}</div>
              <div class="meta">
                {{ bootstrap.device_profile.cpu_cores }} cores ·
                {{ bootstrap.device_profile.memory_mb }} MB
              </div>
            </div>
          </NCard>
        </NGi>
        <NGi>
          <NCard title="部署建议" :bordered="false" class="section-card">
            <NTag type="info">{{ bootstrap.deployment_recommendation.custody_mode }}</NTag>
          </NCard>
        </NGi>
        <NGi>
          <NCard title="优化器" :bordered="false" class="section-card">
            <NTag :type="bootstrap.status === 'ok' ? 'success' : 'warning'">{{ bootstrap.status }}</NTag>
          </NCard>
        </NGi>
      </NGrid>
    </NSpin>

    <NCard title="快捷入口" :bordered="false" class="section-card" style="margin-top: 16px">
      <NSpace>
        <NButton type="primary" @click="router.push('/runs/new')">新建推理任务</NButton>
        <NButton secondary @click="router.push('/models')">模型仓库</NButton>
        <NButton secondary @click="router.push('/runs')">任务列表</NButton>
        <NButton secondary @click="router.push('/inference/llm')">大模型推理</NButton>
      </NSpace>
    </NCard>
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
}

.workflow-step span:last-child {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
}

.workflow-arrow {
  color: var(--color-text-muted);
  font-size: 20px;
}

.cta-btn {
  min-width: 200px;
  background: linear-gradient(135deg, var(--color-primary), var(--color-accent)) !important;
  border: none !important;
}

.section-card {
  box-shadow: var(--shadow-sm);
}

.panel {
  border-radius: var(--radius-md);
  padding: var(--space-4);
  border: 1px solid var(--color-border);
}

.panel-blue {
  background: #f8fbff;
}

.meta {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  margin-top: 6px;
}
</style>
