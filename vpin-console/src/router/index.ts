import { createRouter, createWebHashHistory } from "vue-router";
import AppLayout from "@/layouts/AppLayout.vue";

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    {
      path: "/",
      component: AppLayout,
      children: [
        { path: "", name: "home", component: () => import("@/views/HomeView.vue") },
        { path: "data/custody", name: "custody", component: () => import("@/views/CustodyView.vue") },
        { path: "data/catalog", name: "catalog", component: () => import("@/views/CatalogView.vue") },
        { path: "models", name: "models", component: () => import("@/views/ModelsView.vue") },
        { path: "runs", name: "runs", component: () => import("@/views/RunsListView.vue") },
        { path: "runs/new", name: "run-new", component: () => import("@/views/RunNewView.vue") },
        { path: "runs/:id", name: "run-detail", component: () => import("@/views/RunDetailView.vue") },
        { path: "verification/:runId", name: "verification", component: () => import("@/views/VerificationView.vue") },
        { path: "privacy", name: "privacy", component: () => import("@/views/PrivacyView.vue") },
        { path: "link-monitor", name: "link-monitor", component: () => import("@/views/LinkMonitorView.vue") },
        { path: "settings", name: "settings", component: () => import("@/views/SettingsView.vue") },
        { path: "inference/llm", name: "llm-inference", component: () => import("@/views/demo/LlmDemoView.vue") },
        { path: "demo/llm", redirect: "/inference/llm" },
      ],
    },
  ],
});

export default router;
