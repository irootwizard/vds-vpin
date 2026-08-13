import type { InferenceEvent, RunRecord } from "@/bridge/types";
import { appendEventLog, inferenceEventBus } from "@/bridge/eventBus";
import { AHE_PHASES, type AhePhaseId } from "@/constants/aheFlow";
import {
  DEFAULT_NETWORK_A_ENGINE,
  networkAEngineLabel,
  networkAEnginePort,
} from "@/config/networkAEngine";
import {
  ensureAheServerForEngine,
  isTauri,
  runRustAheBatch,
  runRustAheInfer,
  subscribeAheProgress,
  type NetworkARustEngine,
} from "@/services/aheClient";

let activeRunId: string | null = null;
let progressUnsub: (() => void) | null = null;
const activePhases = new Set<string>();

function emit(ev: InferenceEvent): void {
  inferenceEventBus.emit(ev);
}

function handleProgress(payload: Record<string, unknown>, runId: string): void {
  if (payload.kind !== "progress") return;
  const phase = String(payload.phase ?? "");

  if (phase === "trace" && payload.step && typeof payload.step === "object") {
    const step = payload.step as Record<string, unknown>;
    const detail = step.detail as Record<string, unknown> | undefined;
    const phaseId = (detail?.phase_id ?? step.phase_id) as string | undefined;
    if (phaseId && AHE_PHASES.some((p) => p.id === phaseId)) {
      if (!activePhases.has(phaseId)) {
        activePhases.add(phaseId);
        const label = AHE_PHASES.find((p) => p.id === phaseId)?.label ?? phaseId;
        emit({
          run_id: runId,
          event: "phase_started",
          phase_id: phaseId as AhePhaseId,
          message: label,
        });
        appendEventLog("bridge://ahe-server", `P3 ${label}`);
      }
    }
    return;
  }

  if (phase === "session_start") {
    appendEventLog(
      "bridge://ahe-server",
      `WebSocket 会话 → ${payload.backend ?? "ahe-server"}`,
    );
    return;
  }

  if (phase === "batch_item_done") {
    const completed = Number(payload.completed ?? 0);
    const total = Number(payload.total ?? 0);
    if (total > 0) {
      emit({
        run_id: runId,
        event: "batch_progress",
        batch_index: completed,
        batch_total: total,
      });
    }
  }
}

async function ensureProgressListener(runId: string): Promise<void> {
  if (progressUnsub) return;
  progressUnsub = await subscribeAheProgress((payload) => {
    if (activeRunId === runId) handleProgress(payload, runId);
  });
}

export function isRustAheAvailable(): boolean {
  return isTauri();
}

function resolveEngine(run: RunRecord): NetworkARustEngine {
  return run.config.rust_engine ?? DEFAULT_NETWORK_A_ENGINE;
}

export async function driveRustAheRun(run: RunRecord): Promise<{
  display_accuracy?: number;
  correct_count?: number;
  wrong_count?: number;
  prediction?: number;
  label?: number;
  elapsed_ms?: number;
}> {
  if (!isTauri()) {
    throw new Error("Rust AHE 需在 Tauri 桌面端运行");
  }

  const engine = resolveEngine(run);
  await ensureAheServerForEngine(engine);

  activeRunId = run.run_id;
  activePhases.clear();
  await ensureProgressListener(run.run_id);

  const batchSize = Math.max(1, run.config.batch_size);
  const modelId = run.config.model_id;
  const mnistStart =
    run.config.mnist_start ?? run.mnist_index ?? run.config.mnist_index ?? 0;
  const mnistEnd =
    run.config.mnist_end ??
    (batchSize === 1 ? mnistStart : mnistStart + batchSize - 1);
  const t0 = performance.now();

  appendEventLog(
    "bridge://ahe-server",
    `Network A ${networkAEngineLabel(engine)} :${networkAEnginePort(engine)} model=${modelId} batch=${batchSize}`,
  );

  if (batchSize === 1) {
    const result = await runRustAheInfer({
      modelId,
      mnistIndex: mnistStart,
      inferEngine: engine,
    });
    const prediction = Number(result.prediction ?? -1);
    const label = Number(result.label ?? result.true_label ?? -1);
    const lastPhase = AHE_PHASES[AHE_PHASES.length - 1];
    emit({
      run_id: run.run_id,
      event: "phase_completed",
      phase_id: lastPhase.id,
      elapsed_ms: performance.now() - t0,
    });
    return {
      prediction: prediction >= 0 ? prediction : undefined,
      label: label >= 0 ? label : undefined,
      elapsed_ms: performance.now() - t0,
    };
  }

  const result = await runRustAheBatch({
    modelId,
    mnistStart,
    mnistEnd,
    concurrency: Math.min(4, batchSize),
    inferEngine: engine,
  });

  const report =
    (result.report as Record<string, unknown> | undefined) ??
    (result as Record<string, unknown>);
  const total = Number(report.total ?? batchSize);
  const correct = Number(report.correct ?? 0);
  const accuracy = Number(report.accuracy ?? (total > 0 ? correct / total : 0));
  const wrong = total - correct;

  emit({
    run_id: run.run_id,
    event: "batch_progress",
    batch_index: total,
    batch_total: total,
  });

  return {
    display_accuracy: accuracy,
    correct_count: correct,
    wrong_count: wrong,
    elapsed_ms: performance.now() - t0,
  };
}

export function clearAheDriver(): void {
  activeRunId = null;
  activePhases.clear();
}
