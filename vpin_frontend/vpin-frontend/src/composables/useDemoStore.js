import { reactive, watch } from "vue";

const STORAGE_KEY = "vpin-demo-store";
const NOTICE_KEY = "vpin-service-notice-v1";

const DEMO_MODELS = [
  {
    id: "cnn-a",
    name: "CNN Network A",
    version: "paper-fig2",
    desc: "vPIN 论文图 2 网络 A，MNIST 28×28 隐私推理演示（Mock）",
    icon: "A",
  },
  {
    id: "lenet5",
    name: "LeNet-5",
    version: "table2",
    desc: "LeNet-5 准确率实验网络，支持 AHE 同态推理演示（Mock）",
    icon: "L",
  },
];

function loadStore() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return JSON.parse(raw);
  } catch {
    /* ignore */
  }
  return { sessions: [] };
}

const store = reactive(loadStore());

watch(
  () => ({ sessions: [...store.sessions] }),
  (val) => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(val));
    } catch {
      /* ignore */
    }
  },
  { deep: true },
);

function hasAgreedNotice() {
  return localStorage.getItem(NOTICE_KEY) === "1";
}

function agreeNotice() {
  localStorage.setItem(NOTICE_KEY, "1");
}

function createSession({ name, modelId, ttlHours = 24 }) {
  const model = DEMO_MODELS.find((m) => m.id === modelId) ?? DEMO_MODELS[0];
  const id = `demo-${Date.now()}`;
  const now = Date.now();
  const session = {
    id,
    name,
    modelId: model.id,
    modelName: model.name,
    modelVersion: model.version,
    status: "queuing",
    createdAt: now,
    expiresAt: now + ttlHours * 3600 * 1000,
    messages: [],
    queueStartedAt: now,
  };
  store.sessions.unshift(session);
  return session;
}

function getSession(id) {
  return store.sessions.find((s) => s.id === id) ?? null;
}

function updateSession(id, patch) {
  const s = getSession(id);
  if (s) Object.assign(s, patch);
}

function deleteSession(id) {
  const idx = store.sessions.findIndex((s) => s.id === id);
  if (idx >= 0) store.sessions.splice(idx, 1);
}

function addMessage(sessionId, message) {
  const s = getSession(sessionId);
  if (!s) return;
  s.messages.push({ ...message, id: `msg-${Date.now()}-${Math.random().toString(36).slice(2, 6)}` });
}

export function useDemoStore() {
  return {
    store,
    DEMO_MODELS,
    hasAgreedNotice,
    agreeNotice,
    createSession,
    getSession,
    updateSession,
    deleteSession,
    addMessage,
  };
}
