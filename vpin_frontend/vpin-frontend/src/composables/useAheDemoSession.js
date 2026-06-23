import { reactive, computed } from "vue";

const AHE_STEPS = [
  { key: "session", label: "P0 会话", desc: "SessionStart / Accept" },
  { key: "model", label: "P1 模型", desc: "ModelSelect / Ack" },
  { key: "digest", label: "P2 摘要", desc: "InputDigest" },
  { key: "infer", label: "P3 推理", desc: "同态推理 + 四轮截断" },
];

const state = reactive({
  currentStep: 0,
  connectionStatus: "disconnected",
  selectedIndex: 0,
  preprocessResult: null,
  sessionResult: null,
  interactionLog: [],
  timing: null,
  error: null,
});

export function useAheDemoSession() {
  const steps = AHE_STEPS;
  const connectionLabel = computed(() => {
    const map = {
      disconnected: "未连接",
      connecting: "连接中",
      connected: "已完成",
      error: "错误",
    };
    return map[state.connectionStatus] ?? state.connectionStatus;
  });

  function log(entry) {
    state.interactionLog.push({ ...entry, at: new Date().toISOString() });
  }

  function reset() {
    state.currentStep = 0;
    state.connectionStatus = "disconnected";
    state.preprocessResult = null;
    state.sessionResult = null;
    state.interactionLog = [];
    state.timing = null;
    state.error = null;
  }

  return {
    state,
    steps,
    connectionLabel,
    log,
    reset,
  };
}
