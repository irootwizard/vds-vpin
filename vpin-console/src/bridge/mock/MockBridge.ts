import type {
  BridgeResponse,
  CustodyCapabilities,
  EventLogEntry,
  InferenceEvent,
  ModelInfo,
  PreflightResult,
  RunConfig,
  RunRecord,
  StartupOptimizerResult,
  WorkflowNode,
} from "@/bridge/types";
import {
  appendEventLog,
  eventLogBus,
  inferenceEventBus,
  sleep,
} from "@/bridge/eventBus";
import { recordRunInferenceUsage } from "@/services/inferenceMetricsRecorder";
import {
  getPerfProfile,
  simulateBatchAccuracy,
  splitPhaseDurations,
} from "@/demo/demoTiming";
import { clearAheDriver, driveRustAheRun, isRustAheAvailable } from "@/bridge/aheDriver";
import { attachProofSlot, scheduleComputationProof } from "@/bridge/proofDriver";
import {
  DEFAULT_NETWORK_A_ENGINE,
  networkAEngineLabel,
  networkAEnginePort,
} from "@/config/networkAEngine";
import { resolveInferencePlan } from "@/config/modelCatalog";
import { fetchEnrichedModel, fetchAheCapableIds } from "@/services/modelCatalogApi";
import { resolveComboAccuracyPct } from "@/config/homomorphicGovernance";
import { inferenceEngineLabel } from "@/utils/productLabels";
import {
  createBinding,
  commitUploadSession,
  createUploadSession,
  getCustodyDefaults,
  getBinding,
  listBindings,
  listSessions,
  simulateTamper,
  verifyBindingIntegrity,
  restoreSessionIntegrity,
  discardCustodyWorkflow,
  deleteBinding,
} from "@/custody/localCustodyShim";
import type {
  CustodyCommitResult,
  CustodyDefaultsView,
  CustodyUploadSession,
  DataBindingRecord,
  IntegrityVerifyResult,
} from "@/custody/types";
import { pingAheServerPort } from "@/services/backendApi";

function ok<T>(data: T): BridgeResponse<T> {
  return { ok: true, data };
}

function fail<T>(code: string, message: string): BridgeResponse<T> {
  return { ok: false, error: { code, message } };
}

const MODELS: ModelInfo[] = [
  {
    model_id: "cnn-mnist-trained",
    name: "CNN MNIST Network A (trained)",
    family: "lenet",
    dataset: "MNIST",
    train_accuracy: 0.9291,
  },
];

function defaultWorkflow(): WorkflowNode[] {
  return [
    { id: "bootstrap", stage: "0", label: "Bootstrap", status: "done" },
    { id: "custody", stage: "A", label: "数据托管", status: "pending" },
    { id: "inference", stage: "B", label: "密态推理 P3", status: "pending" },
    { id: "verification", stage: "C", label: "双验证 P4-P6", status: "pending" },
  ];
}

class MockBridge {
  private runs = new Map<string, RunRecord>();
  private runSeq = 0;
  private activeTimers = new Map<string, ReturnType<typeof setTimeout>[]>();

  subscribeInference(fn: (e: InferenceEvent) => void): () => void {
    return inferenceEventBus.subscribe(fn);
  }

  subscribeEventLog(fn: (e: EventLogEntry) => void): () => void {
    return eventLogBus.subscribe(fn);
  }

  async bridgeBootstrapDetect(
    consent: boolean,
  ): Promise<BridgeResponse<StartupOptimizerResult>> {
    if (!consent) {
      return ok({
        startup_id: `boot-${Date.now()}`,
        status: "degraded",
        detect_mode: "skipped_user_refused",
        bootstrap_timestamp: new Date().toISOString(),
        device_profile: {
          device_category: "desktop",
          device_class: "balanced",
          cpu_cores: 8,
          memory_mb: 16384,
        },
        deployment_recommendation: {
          custody_mode: "hosted",
          rationale: "detection_skipped",
        },
      });
    }
    appendEventLog("bridge://bootstrap", "StartupOptimizer 检测完成");
    return ok({
      startup_id: `boot-${Date.now()}`,
      status: "ok",
      detect_mode: "full",
      bootstrap_timestamp: new Date().toISOString(),
      device_profile: {
        device_category: "desktop",
        device_class: "balanced",
        cpu_cores: 8,
        memory_mb: 16384,
      },
      deployment_recommendation: {
        custody_mode: "hosted",
        rationale: "edge_low_compute",
      },
    });
  }

  async bridgeCustodyGetCapabilities(): Promise<BridgeResponse<CustodyCapabilities>> {
    appendEventLog("local-shim://custody", "能力发现 data_only");
    return ok({
      implemented: ["data_only"],
      placeholder: [],
      runtime: "vpin-custody",
    });
  }

  async bridgeCustodyGetDefaults(): Promise<BridgeResponse<CustodyDefaultsView>> {
    return ok(getCustodyDefaults());
  }

  async bridgeCustodyCreateUploadSession(opts: {
    dataset_id?: string;
    mnist_index?: number;
    sample_index?: number;
    file_name?: string;
    file_bytes?: number[];
    rust_input_digest_hex?: string;
    preprocess_lane?: "rust" | "js";
  }): Promise<
    BridgeResponse<{ session: CustodyUploadSession; chunks: { chunk_index: number; vads_index: number; digest_hex: string; byte_length: number }[] }>
  > {
    try {
      const bytes =
        opts.file_bytes != null ? new Uint8Array(opts.file_bytes) : undefined;
      const data = await createUploadSession({
        datasetId: opts.dataset_id,
        mnistIndex: opts.mnist_index,
        sampleIndex: opts.sample_index ?? opts.mnist_index,
        fileName: opts.file_name,
        fileBytes: bytes,
        rustInputDigestHex: opts.rust_input_digest_hex,
        preprocessLane: opts.preprocess_lane,
      });
      return ok(data);
    } catch (e) {
      return fail("CUSTODY_ERROR", e instanceof Error ? e.message : String(e));
    }
  }

  async bridgeCustodyCommit(sessionId: string): Promise<BridgeResponse<CustodyCommitResult>> {
    try {
      return ok(await commitUploadSession(sessionId));
    } catch (e) {
      return fail("CUSTODY_ERROR", e instanceof Error ? e.message : String(e));
    }
  }

  async bridgeCustodyCreateBinding(
    sessionId: string,
    sampleLabel?: string,
  ): Promise<BridgeResponse<DataBindingRecord>> {
    try {
      return ok(await createBinding(sessionId, sampleLabel));
    } catch (e) {
      return fail("CUSTODY_ERROR", e instanceof Error ? e.message : String(e));
    }
  }

  async bridgeCustodyVerifyIntegrity(
    bindingId: string,
  ): Promise<BridgeResponse<IntegrityVerifyResult>> {
    try {
      return ok(await verifyBindingIntegrity(bindingId));
    } catch (e) {
      return fail("CUSTODY_ERROR", e instanceof Error ? e.message : String(e));
    }
  }

  async bridgeCustodySimulateTamper(
    sessionId: string,
    chunkIndex?: number,
  ): Promise<BridgeResponse<{ ok: boolean }>> {
    return ok({ ok: simulateTamper(sessionId, chunkIndex ?? 0) });
  }

  async bridgeCustodyRestoreIntegrity(
    sessionId: string,
  ): Promise<BridgeResponse<{ ok: boolean }>> {
    return ok({ ok: restoreSessionIntegrity(sessionId) });
  }

  async bridgeCustodyDiscardWorkflow(opts: {
    session_id: string;
    binding_id?: string;
  }): Promise<BridgeResponse<{ ok: boolean }>> {
    return ok({
      ok: discardCustodyWorkflow(opts.session_id, opts.binding_id),
    });
  }

  async bridgeCustodyDeleteBinding(
    bindingId: string,
  ): Promise<BridgeResponse<{ ok: boolean }>> {
    return ok({ ok: deleteBinding(bindingId) });
  }

  async bridgeCustodyListBindings(): Promise<BridgeResponse<DataBindingRecord[]>> {
    return ok(listBindings());
  }

  async bridgeCustodyListSessions(): Promise<BridgeResponse<CustodyUploadSession[]>> {
    return ok(listSessions());
  }

  async bridgeCustodyGetBinding(bindingId: string): Promise<BridgeResponse<DataBindingRecord>> {
    const b = getBinding(bindingId);
    if (!b) return fail("NOT_FOUND", `binding ${bindingId} not found`);
    return ok(b);
  }

  async bridgeProxyListModels(): Promise<BridgeResponse<ModelInfo[]>> {
    return ok(MODELS);
  }

  async bridgeRunCreate(config: RunConfig): Promise<BridgeResponse<RunRecord>> {
    const runId = `run-${++this.runSeq}-${Date.now().toString(36)}`;
    const rustEngine = config.rust_engine ?? DEFAULT_NETWORK_A_ENGINE;
    const run: RunRecord = {
      run_id: runId,
      status: "created",
      config: { ...config, rust_engine: isRustAheAvailable() ? rustEngine : config.rust_engine },
      created_at: new Date().toISOString(),
      workflow_nodes: defaultWorkflow(),
    };
    this.runs.set(runId, run);
    attachProofSlot(run);
    appendEventLog("bridge://run", `创建运行 ${runId} model=${config.model_id}`);
    return ok(run);
  }

  async bridgeRunGet(runId: string): Promise<BridgeResponse<RunRecord>> {
    const run = this.runs.get(runId);
    if (!run) return fail("NOT_FOUND", `run ${runId} not found`);
    return ok(structuredClone(run));
  }

  async bridgeRunList(): Promise<BridgeResponse<RunRecord[]>> {
    return ok([...this.runs.values()].sort((a, b) => b.created_at.localeCompare(a.created_at)));
  }

  async bridgeRunPreflight(runId: string): Promise<BridgeResponse<PreflightResult>> {
    const run = this.runs.get(runId);
    if (!run) return fail("NOT_FOUND", `run ${runId} not found`);

    const aheIds = await fetchAheCapableIds();
    const model = await fetchEnrichedModel(run.config.model_id);
    const plan = resolveInferencePlan(
      model,
      run.config.model_id,
      aheIds,
      isRustAheAvailable(),
      run.config.dataset_id,
    );
    const useRustPath = plan.mode === "rust_ahe";
    const rustEngine = run.config.rust_engine ?? DEFAULT_NETWORK_A_ENGINE;
    const rustPort = networkAEnginePort(rustEngine);
    const aheUp = useRustPath ? (await pingAheServerPort(rustPort)).ok : false;
    const canUseRust = useRustPath && aheUp;
    const canUseDemo = plan.mode === "timing_demo";

    const checks = [
      {
        id: "model",
        label: "模型 registry",
        status: canUseRust || canUseDemo ? ("pass" as const) : ("fail" as const),
        detail: plan.preflightModelDetail,
      },
      {
        id: "ahe-server",
        label: `Rust ahe-server (${networkAEngineLabel(rustEngine)})`,
        status: plan.requiresAheServer
          ? aheUp
            ? ("pass" as const)
            : ("fail" as const)
          : ("warn" as const),
        detail: plan.requiresAheServer
          ? aheUp
            ? `:${rustPort} 在线`
            : `节点 :${rustPort} 同步中`
          : `${plan.familyLabel} · 无需 ahe-server`,
      },
      {
        id: "scheme",
        label: "密态推理路径",
        status: canUseRust || canUseDemo ? ("pass" as const) : ("fail" as const),
        detail: canUseRust
          ? `Tauri → ahe-cli → ${rustEngine} :${rustPort}`
          : canUseDemo
            ? plan.preflightSchemeDetail
            : undefined,
      },
    ];
    const canStart = canUseRust || canUseDemo;
    run.status = "preflight";
    return ok({ run_id: runId, checks, can_start: canStart });
  }

  async bridgeRunStart(runId: string): Promise<BridgeResponse<RunRecord>> {
    const run = this.runs.get(runId);
    if (!run) return fail("NOT_FOUND", `run ${runId} not found`);
    const aheIds = await fetchAheCapableIds();
    const model = await fetchEnrichedModel(run.config.model_id);
    const plan = resolveInferencePlan(
      model,
      run.config.model_id,
      aheIds,
      isRustAheAvailable(),
      run.config.dataset_id,
    );
    const profile = getPerfProfile(plan.perfProfileKey);
    const useRustPath = plan.mode === "rust_ahe";

    if (useRustPath) {
      const rustEngine = run.config.rust_engine ?? DEFAULT_NETWORK_A_ENGINE;
      const rustPort = networkAEnginePort(rustEngine);
      const aheUp = (await pingAheServerPort(rustPort)).ok;
      if (!aheUp) {
        return fail(
          "AHE_UNAVAILABLE",
          `${networkAEngineLabel(rustEngine)} 节点暂时不可用，请稍后重试`,
        );
      }
    }

    this.clearTimers(runId);
    run.status = "running";
    run.workflow_nodes = run.workflow_nodes.map((n) =>
      n.id === "custody" ? { ...n, status: "done" } : n,
    );
    run.workflow_nodes = run.workflow_nodes.map((n) =>
      n.id === "inference" ? { ...n, status: "active" } : n,
    );
    run.batch_total = run.config.batch_size;
    run.batch_completed = 0;
    run.inference_engine = useRustPath
      ? (run.config.rust_engine ?? DEFAULT_NETWORK_A_ENGINE)
      : "timing-demo";
    run.mnist_index =
      run.config.sample_index ?? run.config.mnist_index ?? run.config.mnist_start ?? 0;

    appendEventLog(
      "bridge://inference",
      `启动推理 run=${runId} batch=${run.config.batch_size} engine=${inferenceEngineLabel(run.inference_engine)} profile=${profile.model_id}`,
    );

    if (useRustPath) {
      void this.runRustInference(run);
    } else {
      void this.simulateInference(run);
    }
    return ok(structuredClone(run));
  }

  private async runRustInference(run: RunRecord): Promise<void> {
    const start = performance.now();
    try {
      const stats = await driveRustAheRun(run);
      run.batch_completed = run.config.batch_size;
      run.elapsed_ms = performance.now() - start;
      run.inference_engine = run.config.rust_engine ?? DEFAULT_NETWORK_A_ENGINE;
      if (stats.prediction != null) run.prediction = stats.prediction;
      if (stats.label != null) run.label = stats.label;
      if (stats.display_accuracy != null) {
        run.display_accuracy = stats.display_accuracy;
        run.correct_count = stats.correct_count;
        run.wrong_count = stats.wrong_count;
      }
      run.status = "completed";
      run.workflow_nodes = run.workflow_nodes.map((n) =>
        n.id === "inference" ? { ...n, status: "done" } : n,
      );
      run.workflow_nodes = run.workflow_nodes.map((n) =>
        n.id === "verification" ? { ...n, status: "active" } : n,
      );
      inferenceEventBus.emit({
        run_id: run.run_id,
        event: "run_completed",
        display_accuracy: run.display_accuracy,
        wrong_count: run.wrong_count,
        correct_count: run.correct_count,
        elapsed_ms: performance.now() - start,
      });
      void recordRunInferenceUsage(run);
      appendEventLog("bridge://ahe-server", `Rust 推理完成 run=${run.run_id}`, "success");
      scheduleComputationProof(run);
    } catch (err) {
      run.status = "failed";
      run.workflow_nodes = run.workflow_nodes.map((n) =>
        n.id === "inference" ? { ...n, status: "failed" } : n,
      );
      const msg = err instanceof Error ? err.message : String(err);
      inferenceEventBus.emit({
        run_id: run.run_id,
        event: "run_failed",
        message: msg,
      });
      appendEventLog("bridge://ahe-server", `Rust 推理失败: ${msg}`, "error");
    } finally {
      clearAheDriver();
    }
  }

  private clearTimers(runId: string): void {
    const timers = this.activeTimers.get(runId) ?? [];
    for (const t of timers) clearTimeout(t);
    this.activeTimers.delete(runId);
  }

  private async simulateInference(run: RunRecord): Promise<void> {
    const model = await fetchEnrichedModel(run.config.model_id);
    const plan = resolveInferencePlan(
      model,
      run.config.model_id,
      new Set(),
      false,
      run.config.dataset_id,
    );
    const profile = getPerfProfile(plan.perfProfileKey);
    const sampleStart =
      run.config.sample_index ?? run.config.mnist_start ?? run.config.mnist_index ?? 0;
    const sampleEnd =
      run.config.mnist_end ??
      sampleStart + Math.max(1, run.config.batch_size) - 1;
    const batchSize = Math.max(1, sampleEnd - sampleStart + 1);
    const start = performance.now();

    const runOneImage = async (index: number, isBatch: boolean) => {
      const totalSec =
        batchSize === 1
          ? profile.single_sec
          : 1 / profile.batch_img_per_sec;
      const phases = splitPhaseDurations(totalSec);

      for (const phase of phases) {
        inferenceEventBus.emit({
          run_id: run.run_id,
          event: "phase_started",
          phase_id: phase.phase_id as InferenceEvent["phase_id"],
          batch_index: isBatch ? index : undefined,
          batch_total: isBatch ? batchSize : undefined,
          message: phase.label,
        });
        appendEventLog(
          "bridge://inference-event",
          `P3 ${phase.label} (${(phase.sec * 1000).toFixed(0)}ms)`,
        );
        await sleep(phase.sec * 1000);
        inferenceEventBus.emit({
          run_id: run.run_id,
          event: "phase_completed",
          phase_id: phase.phase_id as InferenceEvent["phase_id"],
          batch_index: isBatch ? index : undefined,
          elapsed_ms: performance.now() - start,
        });
      }
    };

    if (batchSize === 1) {
      await runOneImage(0, false);
    } else {
      for (let i = 0; i < batchSize; i++) {
        await runOneImage(i, true);
        run.batch_completed = i + 1;
        inferenceEventBus.emit({
          run_id: run.run_id,
          event: "batch_progress",
          batch_index: i + 1,
          batch_total: batchSize,
        });
      }
      const trainAcc =
        (model
          ? resolveComboAccuracyPct(model, run.config.dataset_id ?? "mnist-test")
          : profile.train_accuracy * 100) / 100;
      const acc = simulateBatchAccuracy(batchSize, trainAcc);
      run.display_accuracy = acc.displayAcc;
      run.wrong_count = acc.wrong;
      run.correct_count = acc.correct;
    }

    run.status = "completed";
    run.inference_engine = "timing-demo";
    run.elapsed_ms = performance.now() - start;
    run.workflow_nodes = run.workflow_nodes.map((n) =>
      n.id === "inference" ? { ...n, status: "done" } : n,
    );
    run.workflow_nodes = run.workflow_nodes.map((n) =>
      n.id === "verification" ? { ...n, status: "active" } : n,
    );

    inferenceEventBus.emit({
      run_id: run.run_id,
      event: "run_completed",
      display_accuracy: run.display_accuracy,
      wrong_count: run.wrong_count,
      correct_count: run.correct_count,
      elapsed_ms: performance.now() - start,
    });
    void recordRunInferenceUsage(run);
    appendEventLog("bridge://inference", `推理完成 run=${run.run_id}`, "success");
    scheduleComputationProof(run);
  }
}

export const mockBridge = new MockBridge();

export type BridgeClient = MockBridge;
