import { resolveModelFamily } from "@/config/modelCatalog";

/** MNIST Network A 单次推理同态算子（与 client_challenge / ec_schedule 一致） */
const MNIST_PT_ADD = 2144;
const MNIST_PT_MULT = 178;

export function estimateHomomorphicOps(
  modelId: string,
  imageCount: number,
  network?: string,
): { pt_add: number; pt_mult: number } {
  const n = Math.max(1, imageCount);
  const scale = resolveModelFamily({ id: modelId, input_shape: "", network }).homomorphicOpScale;
  return { pt_add: Math.round(MNIST_PT_ADD * scale * n), pt_mult: Math.round(MNIST_PT_MULT * scale * n) };
}

export function imageCountFromRun(batchSize: number, mnistStart?: number, mnistEnd?: number): number {
  if (mnistEnd != null && mnistStart != null && mnistEnd >= mnistStart) {
    return mnistEnd - mnistStart + 1;
  }
  return Math.max(1, batchSize);
}
