import { createApp } from "vue";
import naive from "naive-ui";
import App from "./App.vue";
import router from "./router";
import "./design/tokens.css";

createApp(App).use(router).use(naive).mount("#app");
