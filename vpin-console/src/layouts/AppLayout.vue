<script setup lang="ts">
import { computed, h, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  NLayout,
  NLayoutHeader,
  NLayoutSider,
  NLayoutContent,
  NMenu,
  NConfigProvider,
  NMessageProvider,
  NDialogProvider,
  NButton,
  NTag,
  NAvatar,
  NIcon,
  zhCN,
  dateZhCN,
} from "naive-ui";
import {
  HomeOutline,
  ServerOutline,
  CubeOutline,
  ListOutline,
  AddCircleOutline,
  ShieldCheckmarkOutline,
  DocumentTextOutline,
  SettingsOutline,
  SparklesOutline,
  GitNetworkOutline,
} from "@vicons/ionicons5";
import { themeOverrides } from "@/theme/naive-theme";
import { PLATFORM_NAME, PLATFORM_SUBTITLE } from "@/constants/nav";
import SessionContextBar from "@/components/SessionContextBar.vue";
import WorkflowNavigator from "@/workflow/WorkflowNavigator.vue";
import EventLog from "@/workflow/EventLog.vue";
import type { WorkflowNode } from "@/bridge/types";
import { initPlatformSession, usePlatformConnect } from "@/composables/usePlatformConnect";

const route = useRoute();
const router = useRouter();
const { sessionId, backendStatus, aheStatus, bridgeReady, backendUrl, aheUrl } =
  usePlatformConnect();

const icon = (C: typeof HomeOutline) => () => h(NIcon, null, { default: () => h(C) });

const menuOptions = [
  { label: "总览", key: "home", icon: icon(HomeOutline) },
  {
    label: "L1 数据",
    key: "l1-group",
    type: "group",
    children: [
      { label: "数据托管", key: "custody", icon: icon(ServerOutline) },
      { label: "数据集目录", key: "catalog", icon: icon(DocumentTextOutline) },
    ],
  },
  {
    label: "L2 计算",
    key: "l2-group",
    type: "group",
    children: [
      { label: "模型仓库", key: "models", icon: icon(CubeOutline) },
      { label: "大模型推理", key: "llm-inference", icon: icon(SparklesOutline) },
    ],
  },
  {
    label: "L3 调度",
    key: "l3-group",
    type: "group",
    children: [
      { label: "运行列表", key: "runs", icon: icon(ListOutline) },
      { label: "新建运行", key: "run-new", icon: icon(AddCircleOutline) },
    ],
  },
  {
    label: "L4 结果",
    key: "l4-group",
    type: "group",
    children: [
      { label: "隐私与策略", key: "privacy", icon: icon(ShieldCheckmarkOutline) },
      { label: "链路监视", key: "link-monitor", icon: icon(GitNetworkOutline) },
    ],
  },
  { label: "设置", key: "settings", icon: icon(SettingsOutline) },
];

const workflowNodes = ref<WorkflowNode[]>([
  { id: "bootstrap", stage: "0", label: "Bootstrap", status: "done" },
  { id: "custody", stage: "A", label: "数据托管", status: "pending" },
  { id: "inference", stage: "B", label: "密态推理 P3", status: "pending" },
  { id: "verification", stage: "C", label: "双验证 P4-P6", status: "pending" },
]);

const activeKey = computed(() => {
  const n = route.name;
  if (n === "home") return "home";
  if (n === "custody") return "custody";
  if (n === "catalog") return "catalog";
  if (n === "models") return "models";
  if (n === "llm-inference") return "llm-inference";
  if (n === "runs") return "runs";
  if (n === "run-new") return "run-new";
  if (n === "run-detail") return "runs";
  if (n === "privacy") return "privacy";
  if (n === "link-monitor") return "link-monitor";
  if (n === "settings") return "settings";
  return "home";
});

const showSessionBar = computed(() =>
  ["home", "run-new", "run-detail", "runs", "custody", "models", "llm-inference"].includes(
    String(route.name),
  ),
);

const runId = computed(() =>
  route.name === "run-detail" ? String(route.params.id) : undefined,
);

onMounted(async () => {
  await initPlatformSession();
  workflowNodes.value = workflowNodes.value.map((n) =>
    n.id === "custody" ? { ...n, status: "done" } : n,
  );
});

function handleMenuSelect(key: string) {
  if (key.endsWith("-group")) return;
  const map: Record<string, string> = {
    home: "/",
    custody: "/data/custody",
    catalog: "/data/catalog",
    models: "/models",
    runs: "/runs",
    "run-new": "/runs/new",
    privacy: "/privacy",
    "link-monitor": "/link-monitor",
    "llm-inference": "/inference/llm",
    settings: "/settings",
  };
  if (map[key]) router.push(map[key]);
}
</script>

<template>
  <NConfigProvider :locale="zhCN" :date-locale="dateZhCN" :theme-overrides="themeOverrides">
    <NMessageProvider>
      <NDialogProvider>
        <NLayout class="app-shell" has-sider>
      <NLayoutSider
        bordered
        collapse-mode="width"
        :collapsed-width="64"
        :width="220"
        :native-scrollbar="false"
        class="app-sider"
      >
        <div class="brand">
          <div class="brand-mark">密</div>
          <div class="brand-text">
            <strong>{{ PLATFORM_NAME }}</strong>
            <span>{{ PLATFORM_SUBTITLE }}</span>
          </div>
        </div>

        <NMenu
          :value="activeKey"
          :options="menuOptions"
          :indent="16"
          :root-indent="16"
          @update:value="handleMenuSelect"
        />

        <div class="sider-footer">
          <div class="storage-card">
            <div class="storage-card__title">协议进度</div>
            <WorkflowNavigator :nodes="workflowNodes" compact />
          </div>
        </div>
      </NLayoutSider>

      <NLayout class="app-main">
        <NLayoutHeader bordered class="app-header">
          <div class="header-left">
            <span class="platform-title">{{ PLATFORM_NAME }}</span>
            <NTag size="small" round :bordered="false">{{ PLATFORM_SUBTITLE }}</NTag>
          </div>
          <div class="header-right">
            <NButton quaternary size="small" @click="router.push('/runs/new')">新建运行</NButton>
            <div class="user-chip">
              <NAvatar round size="small" :style="{ background: 'var(--color-primary)' }">研</NAvatar>
              <span>研究员</span>
            </div>
          </div>
        </NLayoutHeader>

        <NLayoutContent class="app-content" :native-scrollbar="false">
          <div class="content-column">
            <div class="content-inner">
              <SessionContextBar
                v-if="showSessionBar"
                :run-id="runId"
                :session-id="sessionId"
                :backend-url="backendUrl"
                :ahe-url="aheUrl"
                :backend-status="backendStatus"
                :ahe-status="aheStatus"
                :bridge-ready="bridgeReady"
              />
              <router-view :key="route.fullPath" />
            </div>
            <EventLog />
          </div>
        </NLayoutContent>
      </NLayout>
    </NLayout>
      </NDialogProvider>
    </NMessageProvider>
  </NConfigProvider>
</template>

<style scoped>
.app-shell {
  height: 100vh;
}

.app-shell > :deep(.n-layout) {
  height: 100%;
}

.app-main {
  flex: 1;
  min-width: 0;
  min-height: 0;
}

.app-sider {
  background: var(--color-sider-bg) !important;
}

.app-sider :deep(.n-layout-sider-scroll-container) {
  display: flex;
  flex-direction: column;
}

.app-sider :deep(.n-menu-item-content--selected) {
  background: var(--color-sider-active-bg) !important;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 18px 16px 12px;
}

.brand-mark {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: linear-gradient(135deg, #4f6ef7, #7c5cff);
  color: #fff;
  font-weight: 800;
  font-size: 14px;
  display: grid;
  place-items: center;
}

.brand-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.brand-text strong {
  font-size: 14px;
  color: var(--color-text-primary);
}

.brand-text span {
  font-size: 10px;
  color: var(--color-text-secondary);
}

.sider-footer {
  margin-top: auto;
  padding: 12px;
}

.storage-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: 12px;
}

.storage-card__title {
  font-size: 12px;
  font-weight: 600;
  margin-bottom: 8px;
  color: var(--color-text-primary);
}

.app-header {
  height: var(--header-height);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  background: var(--color-surface);
}

.header-left,
.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.platform-title {
  font-weight: 600;
  font-size: 15px;
  color: var(--color-text-primary);
}

.user-chip {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.app-content {
  background: var(--color-page-bg);
  height: calc(100vh - var(--header-height));
  padding: var(--space-4);
  box-sizing: border-box;
}

.app-content :deep(.n-layout-scroll-container) {
  height: 100%;
  overflow: hidden !important;
}

.content-column {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  gap: var(--space-3);
}

.content-inner {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
  max-width: var(--content-max-width);
  width: 100%;
  margin: 0 auto;
}
</style>
