/**
 * Passive AHE progress consumer — lane-scoped timelines (Python / Rust preprocess + infer).
 *
 * Active path (driver):  Tauri spawn_blocking → python/ahe-cli subprocess → WebSocket → server
 * Passive path (UI):     listen("ahe-progress") → queue → rAF batch → Vue refs (per lane)
 */

import { computed, onUnmounted, ref, shallowRef } from "vue";
import { AHE_PHASES } from "../constants/aheFlow.js";

let globalUnlisten = null;
let subscriberCount = 0;

/** @typedef {(payload: object) => void} ProgressHandler */
/** @typedef {'python'|'rust'} PreprocessLane */

const handlers = new Set();

async function ensureGlobalListener() {
  if (globalUnlisten) return;
  const { listen } = await import("@tauri-apps/api/event");
  globalUnlisten = await listen("ahe-progress", (ev) => {
    for (const h of handlers) {
      try {
        h(ev.payload);
      } catch {
        /* UI handler must never throw back to Tauri */
      }
    }
  });
}

async function releaseGlobalListener() {
  subscriberCount -= 1;
  if (subscriberCount <= 0 && globalUnlisten) {
    globalUnlisten();
    globalUnlisten = null;
    subscriberCount = 0;
  }
}

/**
 * Subscribe to passive progress stream. Returns unsubscribe fn.
 * @param {ProgressHandler} handler
 */
export async function subscribeAheProgress(handler) {
  await ensureGlobalListener();
  subscriberCount += 1;
  handlers.add(handler);
  return () => {
    handlers.delete(handler);
    releaseGlobalListener();
  };
}

function nowStr() {
  return new Date().toLocaleTimeString();
}

function phaseIndexForStep(step) {
  const pid = step?.detail?.phase_id || step?.phase_id;
  if (!pid) return -1;
  return AHE_PHASES.findIndex((p) => p.id === pid);
}

function emptyLaneState() {
  return { steps: [], runningPhase: 0, inferActive: false, inferStartedAt: 0 };
}

/**
 * @param {import('vue').Ref<PreprocessLane>} activeLaneRef
 */
export function useAheInferTimeline(activeLaneRef) {
  /** @type {Record<PreprocessLane, ReturnType<typeof emptyLaneState> & { steps: import('vue').ShallowRef<object[]> }>} */
  const laneStore = {
    python: { ...emptyLaneState(), steps: shallowRef([]) },
    rust: { ...emptyLaneState(), steps: shallowRef([]) },
  };

  const runningPhase = ref(0);
  const inferActive = ref(false);

  const flowSteps = computed(() => laneStore[activeLaneRef.value]?.steps.value ?? []);

  const pendingByLane = { python: [], rust: [] };
  const phaseBumpsByLane = { python: [], rust: [] };
  let rafId = null;
  let unsubscribe = null;
  /** @type {PreprocessLane|null} */
  let activeInferLane = null;
  /** @type {object|null} */
  let currentInferCtx = null;

  function laneSteps(lane) {
    return laneStore[lane]?.steps ?? laneStore.python.steps;
  }

  function flushPending() {
    rafId = null;
    for (const lane of /** @type {PreprocessLane[]} */ (["python", "rust"])) {
      const bumps = phaseBumpsByLane[lane];
      if (bumps.length && lane === activeLaneRef.value) {
        runningPhase.value = Math.max(runningPhase.value, ...bumps);
      }
      bumps.length = 0;

      const pending = pendingByLane[lane];
      if (!pending.length) continue;
      const batch = pending.splice(0);
      const store = laneStore[lane];
      const now = performance.now();
      const base = store.inferStartedAt;
      const stamped = batch.map((s) => ({
        ...s,
        lane,
        at: s.at || nowStr(),
        elapsed_ms: s.elapsed_ms ?? (base ? now - base : undefined),
      }));
      store.steps.value = [...store.steps.value, ...stamped];
    }
  }

  function scheduleFlush() {
    if (rafId != null) return;
    rafId = requestAnimationFrame(flushPending);
  }

  function queueSteps(lane, steps) {
    pendingByLane[lane].push(...steps);
    scheduleFlush();
  }

  function bumpPhase(lane, step) {
    const idx = phaseIndexForStep(step);
    if (idx >= 0) phaseBumpsByLane[lane].push(idx + 1);
    scheduleFlush();
  }

  function dedupePreprocess(steps, lane) {
    const seen = new Set();
    return steps.filter((s) => {
      if (s.category !== "预处理") return true;
      if (s.lane && s.lane !== lane) return false;
      if (seen.has(s.id)) return false;
      seen.add(s.id);
      return true;
    });
  }

  function handleProgress(payload, ctx) {
    const lane = ctx.lane;
    const store = laneStore[lane];
    if (!store.inferActive || !payload || payload.kind !== "progress") return;
    const phase = payload.phase;

    if (phase === "trace" && payload.step) {
      queueSteps(lane, [{ ...payload.step, lane }]);
      bumpPhase(lane, payload.step);
      return;
    }
    if (phase === "session_start") {
      queueSteps(lane, [
        {
          id: "ws_session_start",
          category: "P0",
          title: "WebSocket 会话开始",
          summary: `${ctx.engineLabel || ctx.engine} → ${payload.backend || ctx.backend}`,
          detail: { backend: payload.backend, engine: ctx.engine },
          lane,
        },
      ]);
      if (lane === activeLaneRef.value) runningPhase.value = 0;
      return;
    }
    if (phase === "preprocess_start") {
      queueSteps(lane, [
        {
          id: "infer_preprocess_start",
          category: "客户端",
          title: "加载推理输入",
          summary: `model=${payload.model_id || ctx.modelId}`,
          lane,
        },
      ]);
      return;
    }
    if (phase === "preprocess_done") {
      queueSteps(lane, [
        {
          id: "infer_preprocess_done",
          category: "客户端",
          title: "输入就绪",
          summary: `digest=${payload.digest || "—"}`,
          lane,
        },
      ]);
      return;
    }
    if (phase === "session_done") {
      bumpPhase(lane, { detail: { phase_id: "after_fc2" } });
    }
  }

  async function beginInfer(ctx) {
    const lane = ctx.lane;
    activeInferLane = lane;
    currentInferCtx = ctx;
    const store = laneStore[lane];
    store.inferActive = true;
    store.inferStartedAt = performance.now();
    inferActive.value = true;
    if (lane === activeLaneRef.value) runningPhase.value = 0;
    const prep = store.steps.value.filter(
      (s) => s.category === "预处理" && (!s.lane || s.lane === lane),
    );
    store.steps.value = dedupePreprocess(prep, lane);

    if (!unsubscribe) {
      unsubscribe = await subscribeAheProgress((payload) => {
        if (activeInferLane && currentInferCtx) {
          handleProgress(payload, { ...currentInferCtx, lane: activeInferLane });
        }
      });
    }
  }

  function endInfer() {
    if (activeInferLane) {
      laneStore[activeInferLane].inferActive = false;
    }
    activeInferLane = null;
    currentInferCtx = null;
    inferActive.value = false;
    if (rafId != null) {
      cancelAnimationFrame(rafId);
      rafId = null;
    }
    flushPending();
    runningPhase.value = AHE_PHASES.length;
  }

  function resetTimeline(lane, keepPreprocess = true) {
    const store = laneStore[lane];
    store.steps.value = keepPreprocess ? dedupePreprocess(store.steps.value, lane) : [];
    if (lane === activeLaneRef.value) runningPhase.value = 0;
  }

  function mergePreprocessTrace(prep, lane) {
    if (!prep?.preprocess_trace?.length) return;
    const trace = prep.preprocess_trace.map((s) => ({
      ...s,
      lane,
      at: s.at || nowStr(),
    }));
    const store = laneStore[lane];
    const rest = store.steps.value.filter((s) => s.category !== "预处理" || (s.lane && s.lane !== lane));
    store.steps.value = [...trace, ...rest];
  }

  onUnmounted(async () => {
    if (unsubscribe) {
      unsubscribe();
      unsubscribe = null;
    }
  });

  return {
    flowSteps,
    runningPhase,
    inferActive,
    beginInfer,
    endInfer,
    resetTimeline,
    mergePreprocessTrace,
    queueSteps: (steps) => queueSteps(activeLaneRef.value, steps),
    bumpPhase: (step) => bumpPhase(activeLaneRef.value, step),
  };
}
