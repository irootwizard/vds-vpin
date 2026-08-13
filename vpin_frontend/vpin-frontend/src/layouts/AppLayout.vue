<script setup>
import { computed, h } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  NLayout,
  NLayoutHeader,
  NLayoutSider,
  NLayoutContent,
  NMenu,
  NConfigProvider,
  NButton,
  NTag,
  NAvatar,
  NIcon,
  NProgress,
  zhCN,
  dateZhCN,
} from "naive-ui";
import {
  SparklesOutline,
  HomeOutline,
  CubeOutline,
  ListOutline,
  AddCircleOutline,
  ServerOutline,
  ShieldCheckmarkOutline,
  DocumentTextOutline,
  WalletOutline,
  HelpCircleOutline,
} from "@vicons/ionicons5";
import { themeOverrides } from "../theme/naive-theme.js";
import { PLATFORM_NAME, PLATFORM_SUBTITLE } from "../constants/nav.js";
import SessionContextBar from "../components/SessionContextBar.vue";
import ProtocolProgressBar from "../components/ProtocolProgressBar.vue";
import { useProtocolSession } from "../composables/useProtocolSession.js";

const route = useRoute();
const router = useRouter();
const { state } = useProtocolSession();

const icon = (C) => () => h(NIcon, null, { default: () => h(C) });

const menuOptions = [
  { label: "工作台", key: "home", icon: icon(HomeOutline) },
  { label: "隐私样板间", key: "demo", icon: icon(SparklesOutline) },
  {
    label: "模型服务",
    key: "model-group",
    type: "group",
    children: [{ label: "模型仓库", key: "models", icon: icon(CubeOutline) }],
  },
  {
    label: "推理任务",
    key: "task-group",
    type: "group",
    children: [
      { label: "任务列表", key: "tasks", icon: icon(ListOutline) },
      { label: "新建任务", key: "task-new", icon: icon(AddCircleOutline) },
    ],
  },
  {
    label: "数据管理",
    key: "data-group",
    type: "group",
    children: [{ label: "数据配置", key: "data-config", icon: icon(ServerOutline) }],
  },
  {
    label: "安全中心",
    key: "security-group",
    type: "group",
    children: [
      { label: "通信与推理用量", key: "security", icon: icon(ShieldCheckmarkOutline) },
      { label: "验证报告", key: "verification", icon: icon(DocumentTextOutline) },
    ],
  },
];

const activeKey = computed(() => {
  const n = route.name;
  if (n === "home") return "home";
  if (String(n).startsWith("demo")) return "demo";
  if (n === "task-detail") return "tasks";
  return n || "home";
});

const showProtocolChrome = computed(
  () =>
    ["home", "task-detail", "task-new", "data-config"].includes(route.name) &&
    !String(route.name).startsWith("demo"),
);

const storagePercent = computed(() => {
  if (!state.aheReady) return 12;
  if (!state.precomputeReady) return 35;
  return 58;
});

function handleMenuSelect(key) {
  const map = {
    home: "/",
    demo: "/demo",
    models: "/models",
    tasks: "/tasks",
    "task-new": "/tasks/new",
    "data-config": "/data-config",
    security: "/security",
    verification: "/security/verification",
  };
  if (map[key]) router.push(map[key]);
}
</script>

<template>
  <NConfigProvider :locale="zhCN" :date-locale="dateZhCN" :theme-overrides="themeOverrides">
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
          <div class="brand-mark">V</div>
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
            <div class="storage-card__title">
              <NIcon :size="16"><WalletOutline /></NIcon>
              本地密钥空间
            </div>
            <NProgress type="line" :percentage="storagePercent" :show-indicator="false" :height="6" />
            <div class="storage-card__meta">
              <span>{{ state.aheReady ? "AHE 已 Setup" : "未 Setup" }}</span>
              <span>{{ storagePercent }}%</span>
            </div>
          </div>
        </div>
      </NLayoutSider>

      <NLayout>
        <NLayoutHeader bordered class="app-header">
          <div class="header-left">
            <span class="platform-title">{{ PLATFORM_NAME }}</span>
            <NTag size="small" round :bordered="false">测试版</NTag>
          </div>
          <div class="header-right">
            <NButton quaternary size="small">
              <template #icon><NIcon><HelpCircleOutline /></NIcon></template>
              帮助中心
            </NButton>
            <div class="user-chip">
              <NAvatar round size="small" :style="{ background: 'var(--color-primary)' }">研</NAvatar>
              <span>研究员</span>
            </div>
          </div>
        </NLayoutHeader>

        <NLayoutContent class="app-content">
          <div class="content-inner">
            <template v-if="showProtocolChrome">
              <SessionContextBar />
              <ProtocolProgressBar />
            </template>
            <router-view />
          </div>
        </NLayoutContent>
      </NLayout>
    </NLayout>
  </NConfigProvider>
</template>

<style scoped>
.app-shell {
  height: 100vh;
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
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  margin-bottom: 8px;
  color: var(--color-text-primary);
}

.storage-card__meta {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: var(--color-text-muted);
  margin-top: 6px;
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
  color: var(--color-text-primary);
}

.app-content {
  background: var(--color-page-bg);
  padding: var(--space-4);
  overflow: auto;
}

.content-inner {
  max-width: 1280px;
  margin: 0 auto;
}
</style>
