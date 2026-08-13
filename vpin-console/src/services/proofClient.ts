import type { ComputationProofState } from "@/bridge/types";
import { isTauri } from "@/services/aheClient";
import {
  downloadJsonArtifact,
  fetchProofArtifact,
  isProofM1Available,
  parseArtifactMeta,
  postProofM1Verify,
  postProofVerify,
  type ClientChallengeWire,
} from "@/services/proofApi";

export function stateFromArtifactMeta(
  meta: ReturnType<typeof parseArtifactMeta>,
  challenge?: ClientChallengeWire,
): Partial<ComputationProofState> {
  const ch = meta.client_challenge ?? challenge;
  return {
    challenge: ch,
    gamma_prefix: ch?.gamma.slice(0, 8),
    cm_w_hex: meta.cm_w_hex,
    cm_w_digest_hex: meta.cm_w_digest_hex,
    cm_x_hex: meta.cm_x_hex,
    cm_x_digest_hex: meta.cm_x_digest_hex,
    cps_cm_hex: meta.cps_cm_hex,
    artifact_path: meta.artifact_path,
    proof_coverage: meta.proof_coverage,
    scalar_trace_digest_hex: meta.scalar_trace_digest_hex,
    prove_ms: meta.prove_ms,
  };
}

/** P6: cp-snark-full verify-file；有 Python 后端时追加 M1。 */
export async function manualVerifyProof(
  network = "A",
  modelId = "cnn-mnist-trained",
): Promise<{ ok: boolean; message: string }> {
  const resp = await postProofVerify(network);
  if (!resp?.ok) {
    return { ok: false, message: "cp-snark-full verify 失败" };
  }
  const m1Backend = await isProofM1Available();
  if (!m1Backend) {
    return {
      ok: true,
      message: resp.message ?? "cp-snark-full verify-file PASSED (release)",
    };
  }
  const m1 = await postProofM1Verify({ model_id: modelId, network_id: network });
  if (!m1?.ok) {
    return { ok: false, message: m1?.message ?? "M1 scalar verify 失败" };
  }
  return {
    ok: true,
    message: `${resp.message ?? "verify-file PASSED"}; ${m1.message ?? "M1 PASSED"}`,
  };
}

export async function saveProofToPath(
  destPath: string,
  _sourcePath?: string,
  network = "A",
): Promise<{ ok: boolean; message: string }> {
  if (!destPath.trim()) {
    return { ok: false, message: "请填写保存路径" };
  }
  const raw = await fetchProofArtifact(network);
  if (!raw) {
    return { ok: false, message: "无法读取 protocol.json（后端或 Tauri 证明桥）" };
  }
  const text = JSON.stringify(raw, null, 2);
  if (isTauri()) {
    const { invoke } = await import("@tauri-apps/api/core");
    await invoke("write_text_file", { path: destPath.trim(), contents: text });
    return { ok: true, message: `已保存到 ${destPath}` };
  }
  downloadJsonArtifact(destPath.split(/[/\\]/).pop() ?? "protocol.json", raw);
  return { ok: true, message: "已触发浏览器下载" };
}
