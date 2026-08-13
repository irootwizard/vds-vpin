import type { ComputationProofState, RunRecord } from "@/bridge/types";
import { appendEventLog, inferenceEventBus } from "@/bridge/eventBus";
import { proofEligibleAfterInfer } from "@/config/networkAProof";
import {
  fetchProofArtifact,
  fetchProofPlan,
  parseArtifactMeta,
  postProofProve,
  sampleClientChallenge,
} from "@/services/proofApi";
import { manualVerifyProof, stateFromArtifactMeta } from "@/services/proofClient";

function initialProofState(enabled: boolean): ComputationProofState {
  return { phase: enabled ? "idle" : "skipped", enabled };
}

function emitProof(
  run: RunRecord,
  state: ComputationProofState,
  event: "proof_progress" | "proof_completed" | "proof_failed",
) {
  run.computation_proof = state;
  inferenceEventBus.emit({
    run_id: run.run_id,
    event,
    proof: { ...state },
    message: state.message,
  });
}

export function attachProofSlot(run: RunRecord): void {
  const enabled = proofEligibleAfterInfer(run.config.model_id, run.config.batch_size);
  run.computation_proof = initialProofState(enabled);
}

/** AHE 完成后异步触发；不占用推理锁、不阻塞 P3 时间线 */
export function scheduleComputationProof(run: RunRecord): void {
  if (!proofEligibleAfterInfer(run.config.model_id, run.config.batch_size)) {
    return;
  }
  if (!run.computation_proof) {
    attachProofSlot(run);
  }
  void driveComputationProof(run);
}

export async function runManualVerifyForRun(
  run: RunRecord,
): Promise<ComputationProofState | null> {
  if (!run.computation_proof?.enabled) return null;
  const prev = run.computation_proof;
  const verifying: ComputationProofState = {
    ...prev,
    phase: "verify",
    message: "手动 P6 verify…",
  };
  emitProof(run, verifying, "proof_progress");
  const res = await manualVerifyProof("A", run.config.model_id);
  const next: ComputationProofState = {
    ...prev,
    phase: res.ok ? "done" : "failed",
    verify_ok: res.ok,
    verify_message: res.message,
    ok: res.ok,
    message: res.message,
  };
  emitProof(run, next, res.ok ? "proof_completed" : "proof_failed");
  return next;
}

export async function driveComputationProof(run: RunRecord): Promise<void> {
  if (!proofEligibleAfterInfer(run.config.model_id, run.config.batch_size)) {
    return;
  }

  const modelId = run.config.model_id;
  const sessionId = run.run_id;

  const setPhase = (patch: Partial<ComputationProofState>) => {
    const prev = run.computation_proof ?? initialProofState(true);
    const next: ComputationProofState = { ...prev, enabled: true, ...patch };
    emitProof(run, next, "proof_progress");
  };

  try {
    setPhase({ phase: "plan", message: "加载 ProofPlan（训练 run W* + EC witness）" });
    appendEventLog("bridge://proof", `P4–P6 开始 model=${modelId}`);

    const plan = await fetchProofPlan(modelId);
    if (!plan?.witness.files_ok) {
      throw new Error(
        "ProofPlan 不可用：请确认 proof_artifacts 已打包或启动 vpin-backend",
      );
    }

    setPhase({
      phase: "plan",
      total_pt_mul: plan.schedule.total_pt_mul,
      total_pt_add: plan.schedule.total_pt_add,
      n_w: plan.topology.n_w,
      n2_eq_q1: plan.curve_embed.n2_eq_q1,
      message: `paper_proof ${plan.schedule.total_pt_mul} PtMul / ${plan.schedule.total_pt_add} PtAdd`,
    });

    setPhase({ phase: "challenge", message: "P4 客户端采样 γ / γ′" });
    const challenge = sampleClientChallenge(
      plan.schedule.total_pt_add,
      plan.schedule.total_pt_mul,
    );
    setPhase({
      phase: "challenge",
      challenge,
      gamma_prefix: challenge.gamma.slice(0, 8),
      message: "P4 已采样 γ（完整见下方）",
    });

    setPhase({ phase: "prove", message: "P5 服务端 cp-snark-full prove（约数分钟）" });
    const prove = await postProofProve({
      session_id: sessionId,
      model_id: modelId,
      network_id: "A",
      challenge,
    });
    if (!prove?.ok) {
      throw new Error("服务端 prove 失败");
    }

    setPhase({ phase: "verify", message: "P6 cp-snark-full verify-file" });
    const raw = await fetchProofArtifact("A");
    const meta = raw
      ? parseArtifactMeta(raw, prove.artifact_path)
      : parseArtifactMeta(
          {
            model_commitment: {
              cm_weights: {
                point_hex: prove.commitments?.cm_w_hex ?? prove.summary?.cm_w,
                digest_hex: prove.commitments?.cm_w_digest_hex,
              },
            },
            input_commitment: {
              cm_public: {
                point_hex: prove.commitments?.cm_x_hex ?? prove.summary?.cm_x,
                digest_hex: prove.commitments?.cm_x_digest_hex,
              },
            },
            cps_commitment: { poly_comm_hex: prove.commitments?.cps_cm_hex },
            client_challenge: prove.client_challenge ?? challenge,
            proof_coverage: prove.proof_coverage,
            scalar_trace_digest_hex: prove.scalar_trace_digest_hex,
            prove_time_ms: prove.summary?.prove_ms,
          },
          prove.artifact_path,
        );
    const verifyRes = await manualVerifyProof("A", modelId);
    const final: ComputationProofState = {
      phase: verifyRes.ok ? "done" : "failed",
      enabled: true,
      ok: verifyRes.ok,
      verify_ok: verifyRes.ok,
      verify_message: verifyRes.message,
      ...stateFromArtifactMeta(meta, challenge),
      total_pt_mul: plan.schedule.total_pt_mul,
      total_pt_add: plan.schedule.total_pt_add,
      n_w: plan.topology.n_w,
      n2_eq_q1: plan.curve_embed.n2_eq_q1,
      message: verifyRes.ok
        ? "P6 verify-file 通过"
        : `prove 完成但 verify 未通过: ${verifyRes.message}`,
    };
    emitProof(run, final, verifyRes.ok ? "proof_completed" : "proof_failed");
    appendEventLog(
      "bridge://proof",
      verifyRes.ok ? `计算量证明 OK · ${final.proof_coverage}` : `证明失败: ${final.message}`,
      verifyRes.ok ? "success" : "error",
    );
    if (verifyRes.ok) {
      run.workflow_nodes = run.workflow_nodes.map((n) =>
        n.id === "verification" ? { ...n, status: "done" } : n,
      );
    }
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    emitProof(
      run,
      {
        phase: "failed",
        enabled: true,
        ok: false,
        message: msg,
      },
      "proof_failed",
    );
    appendEventLog("bridge://proof", `证明失败: ${msg}`, "error");
  }
}
