import { createRouter, createWebHistory } from "vue-router";
import AppLayout from "../layouts/AppLayout.vue";
import HomeView from "../views/HomeView.vue";
import ModelWarehouseView from "../views/ModelWarehouseView.vue";
import TaskDetailView from "../views/TaskDetailView.vue";
import EmbedPage from "../views/EmbedPage.vue";
import DemoWelcomeView from "../views/demo/DemoWelcomeView.vue";
import DemoDeployView from "../views/demo/DemoDeployView.vue";
import DemoSessionView from "../views/demo/DemoSessionView.vue";
import AheDemoView from "../views/demo/AheDemoView.vue";

const routes = [
  {
    path: "/",
    component: AppLayout,
    children: [
      { path: "", name: "home", component: HomeView },
      { path: "demo", name: "demo", component: DemoWelcomeView, meta: { title: "隐私样板间" } },
      { path: "demo/deploy", name: "demo-deploy", component: DemoDeployView, meta: { title: "部署演示" } },
      { path: "demo/session/:id", name: "demo-session", component: DemoSessionView, meta: { title: "隐私体验" } },
      { path: "demo/ahe", name: "demo-ahe", component: AheDemoView, meta: { title: "AHE 密态推理" } },
      { path: "models", name: "models", component: ModelWarehouseView, meta: { title: "模型仓库" } },
      {
        path: "tasks/new",
        name: "task-new",
        component: EmbedPage,
        meta: { page: "data-config.html", title: "新建任务" },
      },
      { path: "tasks/:id", name: "task-detail", component: TaskDetailView, meta: { title: "任务详情" } },
      {
        path: "security/verification",
        name: "verification",
        component: EmbedPage,
        meta: { page: "verification-report.html", title: "任务报告" },
      },
    ],
  },
  {
    path: "/vpin/pages/:page",
    redirect: (to) => {
      const map = {
        "index.html": "/",
        "model-center.html": "/models",
        "data-config.html": "/tasks/new",
        "verification-report.html": "/security/verification",
      };
      return map[to.params.page] || "/";
    },
  },
];

export default createRouter({
  history: createWebHistory(),
  routes,
});
