import { createApp } from "vue";
import naive from "naive-ui";
import App from "./App.vue";
import router from "./router/index.js";
import "../public/vpin/css/tokens.css";
import "./base.css";

createApp(App).use(router).use(naive).mount("#app");
