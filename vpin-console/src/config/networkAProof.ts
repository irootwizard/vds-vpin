/** Network A 计算量证明（cp-snark-full）— 仅限自训练 CNN-MNIST；非 Network A 不接入 */

const NETWORK_A_PROOF_MODEL_IDS = new Set([
  "A",
  "cnn-mnist-trained",
  "cnn-mnist-trained-20260622_184254",
]);

const STRICT_NETWORK_A_MODEL_IDS = new Set([
  "cnn-mnist",
  "cnn-mnist-trained",
  "cnn-mnist-b",
]);

/** 仅这些模型在 Tauri 下可走真 Rust AHE */
export function isStrictNetworkAModel(modelId: string): boolean {
  if (STRICT_NETWORK_A_MODEL_IDS.has(modelId)) return true;
  return modelId.startsWith("cnn-mnist-trained");
}

export function supportsComputationProof(modelId: string): boolean {
  if (!isStrictNetworkAModel(modelId)) return false;
  if (NETWORK_A_PROOF_MODEL_IDS.has(modelId)) return true;
  return modelId.startsWith("cnn-mnist-trained");
}

/** 单图推理完成后可串联证明；批量任务不自动跑（避免阻塞） */
export function proofEligibleAfterInfer(modelId: string, batchSize: number): boolean {
  return supportsComputationProof(modelId) && batchSize === 1;
}
