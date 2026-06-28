import { reactive, computed, watch } from "vue";

const STORAGE_KEY = "vpin-protocol-session";

/** @typedef {'setup'|'commit'|'infer'|'challenge'|'prove'|'verify'} ProtocolStage */

export const PROTOCOL_STEPS = [
  { key: "setup", label: "Setup", desc: "AHE 参数与预计算表" },
  { key: "commit", label: "Commit", desc: "模型/输入承诺 cm_W, cm_x" },
  { key: "infer", label: "Infer", desc: "同态推理与客户端截断" },
  { key: "challenge", label: "Challenge", desc: "客户端采样 γ" },
  { key: "prove", label: "Prove", desc: "服务端生成证明 π" },
  { key: "verify", label: "Verify", desc: "客户端本地验证" },
];

const defaultState = () => ({
  /** @type {number} 0–5，对应 PROTOCOL_STEPS */
  currentStep: 0,
  sessionId: null,
  modelName: null,
  modelCmW: null,
  aheCurveId: "E2-default",
  backendUrl: "http://127.0.0.1:8000",
  connectionStatus: "disconnected",
  aheReady: false,
  precomputeReady: false,
  aheEnabled: true,
  cpSnarkEnabled: false,
  verifyStatus: null,
});

function loadState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return { ...defaultState(), ...JSON.parse(raw) };
  } catch {
    /* ignore */
  }
  return defaultState();
}

const state = reactive(loadState());

watch(
  () => ({ ...state }),
  (val) => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(val));
    } catch {
      /* ignore */
    }
  },
  { deep: true },
);

export function useProtocolSession() {
  const currentStage = computed(
    () => PROTOCOL_STEPS[state.currentStep]?.key ?? "setup",
  );

  const connectionLabel = computed(() => {
    const map = {
      disconnected: "未连接",
      connecting: "连接中",
      connected: "已连接",
    };
    return map[state.connectionStatus] ?? state.connectionStatus;
  });

  function markSetupKeysReady() {
    state.aheReady = true;
    if (state.currentStep < 1) state.currentStep = 1;
  }

  function markPrecomputeReady() {
    state.precomputeReady = true;
    if (state.currentStep < 1) state.currentStep = 1;
  }

  function bindModel(name, cmW) {
    state.modelName = name;
    state.modelCmW = cmW;
    if (state.currentStep < 2) state.currentStep = 2;
  }

  function setSessionId(id) {
    state.sessionId = id;
  }

  function advanceTo(stepIndex) {
    state.currentStep = Math.min(Math.max(stepIndex, 0), PROTOCOL_STEPS.length - 1);
  }

  function resetSession() {
    Object.assign(state, defaultState());
  }

  return {
    state,
    currentStage,
    connectionLabel,
    markSetupKeysReady,
    markPrecomputeReady,
    bindModel,
    setSessionId,
    advanceTo,
    resetSession,
  };
}
