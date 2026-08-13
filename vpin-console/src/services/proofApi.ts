import { backendApiBase } from "@/config/endpoints";
import { fetchBackendJson, postBackendJson } from "@/services/backendApi";
import { isTauri } from "@/services/aheClient";

async function tauriProofInvoke<T>(
  cmd: string,
  args: Record<string, unknown>,
): Promise<T | null> {
  if (!isTauri()) return null;
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    return await invoke<T>(cmd, args);
  } catch (err) {
    console.warn(`[proof] tauri ${cmd} failed`, err);
    return null;
  }
}

export interface ProofPlanResponse {
  model_id: string;
  run_dir: string;
  schedule_mode: string;
  topology: { network: string; pool_k: number; n_w: number };
  schedule: { total_pt_mul: number; total_pt_add: number };
  witness: { root: string; files_ok: boolean };
  w_star: { num_weights: number; weights_path: string | null };
  curve_embed: { n2: string; q1: string; q2: string; n2_eq_q1: boolean };
}

export interface ClientChallengeWire {
  gamma: string;
  gamma_add: string;
  gamma_mult: string;
  num_pt_add: number;
  num_pt_mult: number;
}

export interface ProofArtifactMeta {
  artifact_path?: string;
  proof_coverage?: string;
  scalar_trace_digest_hex?: string;
  client_challenge?: ClientChallengeWire;
  cm_w_hex?: string;
  cm_w_digest_hex?: string;
  cm_x_hex?: string;
  cm_x_digest_hex?: string;
  cps_cm_hex?: string;
  prove_ms?: number;
}

export interface ProofProveResponse {
  ok: boolean;
  artifact_path?: string;
  proof_coverage?: string;
  scalar_trace_digest_hex?: string;
  client_challenge?: ClientChallengeWire;
  commitments?: {
    cm_w_hex?: string;
    cm_w_digest_hex?: string;
    cm_x_hex?: string;
    cm_x_digest_hex?: string;
    cps_cm_hex?: string;
  };
  summary?: {
    cm_w?: string;
    cm_x?: string;
    proof_coverage?: string;
    prove_ms?: number;
    num_weights?: number;
  };
  coverage?: Record<string, unknown>;
}

export interface ProofVerifyResponse {
  ok: boolean;
  artifact_path?: string;
  message?: string;
}

export interface ProofM1VerifyResponse {
  ok: boolean;
  scalar_ok?: boolean;
  opening_ok?: boolean;
  proof_coverage?: string;
  artifact_path?: string;
  message?: string;
}

function randomScalarHex(): string {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

export function sampleClientChallenge(
  numPtAdd: number,
  numPtMult: number,
): ClientChallengeWire {
  return {
    gamma: randomScalarHex(),
    gamma_add: randomScalarHex(),
    gamma_mult: randomScalarHex(),
    num_pt_add: numPtAdd,
    num_pt_mult: numPtMult,
  };
}

export async function fetchProofPlan(modelId: string): Promise<ProofPlanResponse | null> {
  if (isTauri()) {
    const local = await tauriProofInvoke<ProofPlanResponse>("read_proof_plan", { modelId });
    if (local?.witness?.files_ok) return local;
  }
  const q = new URLSearchParams({ model_id: modelId });
  const fromBackend = await fetchBackendJson<ProofPlanResponse>(`/proof/plan?${q.toString()}`);
  if (fromBackend?.witness?.files_ok) return fromBackend;
  if (isTauri()) {
    return tauriProofInvoke<ProofPlanResponse>("read_proof_plan", { modelId });
  }
  return null;
}

export async function postProofProve(body: {
  session_id: string;
  model_id: string;
  network_id: string;
  challenge: ClientChallengeWire;
}): Promise<ProofProveResponse | null> {
  const fromBackend = await postBackendJson<ProofProveResponse>("/proof/prove", body);
  if (fromBackend?.ok) return fromBackend;
  return tauriProofInvoke<ProofProveResponse>("proof_prove", {
    sessionId: body.session_id,
    modelId: body.model_id,
    networkId: body.network_id,
    challenge: body.challenge,
  });
}

export async function fetchProofArtifact(network = "A"): Promise<Record<string, unknown> | null> {
  const q = new URLSearchParams({ network });
  const fromBackend = await fetchBackendJson<Record<string, unknown>>(
    `/proof/artifact?${q.toString()}`,
  );
  if (fromBackend) return fromBackend;
  return tauriProofInvoke<Record<string, unknown>>("read_proof_artifact", { network });
}

export async function postProofVerify(network = "A"): Promise<ProofVerifyResponse | null> {
  const q = new URLSearchParams({ network });
  const fromBackend = await postBackendJson<ProofVerifyResponse>(
    `/proof/verify?${q.toString()}`,
    {},
  );
  if (fromBackend?.ok) return fromBackend;
  return tauriProofInvoke<ProofVerifyResponse>("proof_verify", { network });
}

export async function postProofM1Verify(body: {
  model_id: string;
  network_id?: string;
}): Promise<ProofM1VerifyResponse | null> {
  return postBackendJson<ProofM1VerifyResponse>("/proof/m1-verify", {
    model_id: body.model_id,
    network_id: body.network_id ?? "A",
  });
}

export function parseArtifactMeta(
  raw: Record<string, unknown>,
  artifactPath?: string,
): ProofArtifactMeta {
  const mc = (raw.model_commitment as Record<string, unknown>) ?? {};
  const cmW = (mc.cm_weights as Record<string, unknown>) ?? {};
  const ic = (raw.input_commitment as Record<string, unknown>) ?? {};
  const cmX = (ic.cm_public as Record<string, unknown>) ?? {};
  const cps = (raw.cps_commitment as Record<string, unknown>) ?? {};
  const ch = raw.client_challenge as Record<string, unknown> | undefined;
  return {
    artifact_path: artifactPath ?? (raw.artifact_path as string | undefined),
    proof_coverage: String(raw.proof_coverage ?? ""),
    scalar_trace_digest_hex: raw.scalar_trace_digest_hex as string | undefined,
    client_challenge: ch
      ? {
          gamma: String(ch.gamma ?? ""),
          gamma_add: String(ch.gamma_add ?? ""),
          gamma_mult: String(ch.gamma_mult ?? ""),
          num_pt_add: Number(ch.num_pt_add ?? ch.num_point_adds ?? 0),
          num_pt_mult: Number(ch.num_pt_mult ?? ch.num_point_mults ?? 0),
        }
      : undefined,
    cm_w_hex: String(cmW.point_hex ?? ""),
    cm_w_digest_hex: String(cmW.digest_hex ?? ""),
    cm_x_hex: String(cmX.point_hex ?? ""),
    cm_x_digest_hex: String(cmX.digest_hex ?? ""),
    cps_cm_hex: String(cps.poly_comm_hex ?? cps.cm_hex ?? ""),
    prove_ms: Number(raw.prove_time_ms ?? 0),
  };
}

export function downloadJsonArtifact(
  filename: string,
  data: Record<string, unknown>,
): void {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export async function pingProofBackend(): Promise<boolean> {
  const plan = await fetchProofPlan("cnn-mnist-trained");
  return plan != null && plan.witness.files_ok;
}

/** Release 便携包无 Python M1；verify-file 通过即视为 OK。 */
export async function isProofM1Available(): Promise<boolean> {
  const { pingBackend } = await import("@/services/backendApi");
  const { ok } = await pingBackend();
  return ok;
}

export function backendHttpRoot(): string {
  const base = backendApiBase();
  return base.replace(/\/api\/v1\/?$/, "");
}
