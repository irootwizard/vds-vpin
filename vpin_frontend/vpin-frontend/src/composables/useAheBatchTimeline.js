/**
 * Passive batch AHE progress consumer — batch meta, per-item table, focus job trace.
 */

import { computed, onUnmounted, ref, shallowRef } from "vue";
import { AHE_PHASES, getPhasesForModelId } from "../constants/aheFlow.js";
import { subscribeAheProgress } from "./useAheInferTimeline.js";

/** 超过此数量启用紧凑模式：不预填全表、节流刷新、仅保留最近项 */
export const LARGE_BATCH_THRESHOLD = 200;
const RECENT_ITEM_LIMIT = 100;

function phaseIndexForStep(step, phases) {
  const pid = step?.detail?.phase_id || step?.phase_id;
  if (!pid) return -1;
  return phases.findIndex((p) => p.id === pid);
}

function mnistIndexFromJobId(jobId) {
  const m = /^mnist-(\d+)$/.exec(jobId);
  return m ? parseInt(m[1], 10) : null;
}

function emptyItem(jobId) {
  return {
    jobId,
    status: "pending",
    slot: null,
    mnistIndex: mnistIndexFromJobId(jobId),
    uploadId: null,
    prediction: null,
    label: null,
    correct: null,
    timing: null,
    error: null,
  };
}

function isBatchProgressPhase(phase, payload) {
  if (!phase) return false;
  if (phase.startsWith("batch_")) return true;
  return phase === "trace" && Boolean(payload?.job_id);
}

export function useAheBatchTimeline() {
  const batchActive = ref(false);
  const batchCompact = ref(false);
  const batchMeta = ref({
    total: 0,
    concurrency: 1,
    completed: 0,
    correct: 0,
    accuracy: 0,
    elapsed_s: 0,
    eta_s: 0,
    engine: "",
    modelId: "",
  });
  const items = shallowRef([]);
  const focusJobId = ref(null);
  const runningPhase = ref(0);
  const flowSteps = shallowRef([]);
  const report = shallowRef(null);
  const activePhases = ref(AHE_PHASES);

  /** @type {Map<string, object>} */
  const itemMap = new Map();
  /** @type {object[]} */
  let recentRows = [];
  let syncRafId = null;
  let unsubscribe = null;

  const progressPct = computed(() => {
    const t = batchMeta.value.total;
    if (!t) return 0;
    return Math.round((batchMeta.value.completed / t) * 100);
  });

  function syncItemsNow() {
    if (batchCompact.value) {
      items.value = recentRows.slice();
      return;
    }
    items.value = Array.from(itemMap.values());
  }

  function scheduleSync() {
    if (!batchCompact.value) {
      syncItemsNow();
      return;
    }
    if (syncRafId != null) return;
    syncRafId = requestAnimationFrame(() => {
      syncRafId = null;
      syncItemsNow();
    });
  }

  function ensureItem(jobId) {
    if (!itemMap.has(jobId)) {
      itemMap.set(jobId, emptyItem(jobId));
    }
    return itemMap.get(jobId);
  }

  function touchRecentRow(row) {
    const idx = recentRows.findIndex((r) => r.jobId === row.jobId);
    if (idx > 0) {
      recentRows.splice(idx, 1);
      recentRows.unshift(row);
    } else if (idx < 0) {
      recentRows.unshift(row);
      if (recentRows.length > RECENT_ITEM_LIMIT) {
        recentRows.length = RECENT_ITEM_LIMIT;
      }
    }
  }

  function patchItem(jobId, patch) {
    let row;
    if (batchCompact.value) {
      row = recentRows.find((r) => r.jobId === jobId);
      if (!row) {
        row = emptyItem(jobId);
        Object.assign(row, patch);
        recentRows.unshift(row);
        if (recentRows.length > RECENT_ITEM_LIMIT) {
          recentRows.pop();
        }
      } else {
        Object.assign(row, patch);
        touchRecentRow(row);
      }
    } else {
      row = ensureItem(jobId);
      Object.assign(row, patch);
    }
    scheduleSync();
    return row;
  }

  function setFocus(jobId) {
    if (!jobId) return;
    focusJobId.value = jobId;
    flowSteps.value = [];
    runningPhase.value = 0;
  }

  function applyReportResults(rep) {
    if (!rep) return;
    if (batchCompact.value) {
      for (const e of rep.errors || []) {
        if (!e.job_id) continue;
        patchItem(e.job_id, { status: "error", error: e.error ?? null });
      }
      return;
    }
    for (const r of rep.results || []) {
      const jid =
        r.job_id ?? (r.mnist_index != null ? `mnist-${r.mnist_index}` : null);
      if (!jid) continue;
      const row = ensureItem(jid);
      row.status = "done";
      row.mnistIndex = r.mnist_index ?? row.mnistIndex;
      row.prediction = r.prediction ?? row.prediction;
      row.label = r.label ?? row.label;
      row.correct = r.correct ?? row.correct;
      row.timing = r.timing ?? row.timing;
    }
    for (const e of rep.errors || []) {
      if (!e.job_id) continue;
      const row = ensureItem(e.job_id);
      row.status = "error";
      row.error = e.error ?? row.error;
    }
    syncItemsNow();
  }

  function applyBatchReport(rep) {
    if (!rep) return;
    report.value = rep;
    applyReportResults(rep);
    batchMeta.value = {
      ...batchMeta.value,
      total: rep.limit ?? rep.total ?? batchMeta.value.total,
      completed: rep.limit ?? rep.total ?? batchMeta.value.completed,
      correct: rep.correct ?? batchMeta.value.correct,
      accuracy: rep.accuracy ?? batchMeta.value.accuracy,
      elapsed_s: rep.elapsed_s ?? batchMeta.value.elapsed_s,
      concurrency: rep.concurrency ?? batchMeta.value.concurrency,
      engine: rep.engine ?? rep.infer_engine ?? batchMeta.value.engine,
    };
    runningPhase.value = activePhases.value.length;
    batchActive.value = false;
    syncItemsNow();
  }

  function handleProgress(payload) {
    if (!payload || payload.kind !== "progress") return;
    const phase = payload.phase;

    if (phase === "batch_start") {
      batchMeta.value = {
        ...batchMeta.value,
        total: payload.total ?? 0,
        concurrency: payload.concurrency ?? 1,
        engine: payload.engine ?? payload.infer_engine ?? "",
        modelId: payload.model_id ?? batchMeta.value.modelId,
        completed: 0,
        correct: 0,
        accuracy: 0,
        elapsed_s: 0,
        eta_s: 0,
      };
      if (!batchCompact.value && payload.job_keys?.length) {
        itemMap.clear();
        for (const key of payload.job_keys) {
          itemMap.set(key, emptyItem(key));
        }
        syncItemsNow();
      }
      return;
    }

    if (phase === "batch_item_start") {
      patchItem(payload.job_id, {
        status: "running",
        slot: payload.slot ?? null,
        mnistIndex: payload.mnist_index ?? mnistIndexFromJobId(payload.job_id),
        uploadId: payload.upload_id ?? null,
      });
      if (!batchCompact.value || batchMeta.value.completed === 0) {
        setFocus(payload.job_id);
      }
      return;
    }

    if (phase === "trace" && payload.step && payload.job_id) {
      if (payload.job_id !== focusJobId.value) return;
      const step = { ...payload.step, job_id: payload.job_id };
      flowSteps.value = [...flowSteps.value, step];
      const idx = phaseIndexForStep(step, activePhases.value);
      if (idx >= 0) runningPhase.value = idx + 1;
      return;
    }

    if (phase === "batch_item_done") {
      patchItem(payload.job_id, {
        status: payload.failed ? "error" : "done",
        prediction: payload.prediction ?? null,
        label: payload.label ?? null,
        correct: payload.correct_item ?? payload.correct ?? null,
        timing: payload.timing ?? null,
        error: payload.error ?? null,
      });
      batchMeta.value = {
        ...batchMeta.value,
        completed: payload.completed ?? batchMeta.value.completed + 1,
        correct:
          typeof payload.correct === "number"
            ? payload.correct
            : batchMeta.value.correct + (payload.correct_item ? 1 : 0),
        accuracy: payload.accuracy ?? batchMeta.value.accuracy,
        elapsed_s: payload.elapsed_s ?? batchMeta.value.elapsed_s,
        eta_s: payload.eta_s ?? batchMeta.value.eta_s,
      };
      return;
    }

    if (phase === "batch_done") {
      const rep = payload.report ?? payload;
      applyBatchReport(rep);
    }
  }

  async function beginBatch(ctx) {
    activePhases.value = getPhasesForModelId(ctx.modelId);
    batchCompact.value = Boolean(
      ctx.compact ?? (ctx.jobCount ?? 0) > LARGE_BATCH_THRESHOLD,
    );
    batchActive.value = true;
    report.value = null;
    batchMeta.value = {
      total: ctx.jobCount ?? 0,
      concurrency: ctx.concurrency ?? 1,
      completed: 0,
      correct: 0,
      accuracy: 0,
      elapsed_s: 0,
      eta_s: 0,
      engine: ctx.engine ?? "",
      modelId: ctx.modelId ?? "",
    };
    itemMap.clear();
    recentRows = [];
    if (!batchCompact.value) {
      for (const key of ctx.jobKeys || []) {
        itemMap.set(key, emptyItem(key));
      }
      syncItemsNow();
    } else {
      items.value = [];
    }
    focusJobId.value = null;
    flowSteps.value = [];
    runningPhase.value = 0;

    if (!unsubscribe) {
      unsubscribe = await subscribeAheProgress((payload) => {
        if (isBatchProgressPhase(payload?.phase, payload) || batchActive.value) {
          handleProgress(payload);
        }
      });
    }
  }

  function endBatch() {
    batchActive.value = false;
  }

  function resetBatch() {
    batchActive.value = false;
    batchCompact.value = false;
    report.value = null;
    itemMap.clear();
    recentRows = [];
    items.value = [];
    focusJobId.value = null;
    flowSteps.value = [];
    runningPhase.value = 0;
    if (syncRafId != null) {
      cancelAnimationFrame(syncRafId);
      syncRafId = null;
    }
    batchMeta.value = {
      total: 0,
      concurrency: 1,
      completed: 0,
      correct: 0,
      accuracy: 0,
      elapsed_s: 0,
      eta_s: 0,
      engine: "",
      modelId: "",
    };
  }

  onUnmounted(() => {
    if (unsubscribe) {
      unsubscribe();
      unsubscribe = null;
    }
    if (syncRafId != null) {
      cancelAnimationFrame(syncRafId);
    }
  });

  return {
    batchActive,
    batchCompact,
    batchMeta,
    items,
    focusJobId,
    runningPhase,
    flowSteps,
    report,
    progressPct,
    activePhases,
    beginBatch,
    endBatch,
    resetBatch,
    setFocus,
    applyBatchReport,
  };
}
