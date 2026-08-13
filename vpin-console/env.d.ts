/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_BRIDGE_MODE?: string;
  readonly VITE_BACKEND_URL?: string;
  readonly VITE_AHE_SERVER_URL?: string;
  readonly VITE_DEEPSEEK_API_KEY?: string;
  readonly VITE_DEEPSEEK_MODEL?: string;
  readonly VITE_DEEPSEEK_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

declare module "*.vue" {
  import type { DefineComponent } from "vue";
  const component: DefineComponent<object, object, unknown>;
  export default component;
}
