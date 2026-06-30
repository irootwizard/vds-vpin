/** Network A AHE 推理阶段（与 vpin_backend.crypto.ahe.topology 对齐） */

export const LENET_MNIST_PHASES = [
  {
    id: "initial",
    layer: "输入",
    server: "—",
    client: "定点加密",
    shape: [1, 1, 32, 32],
    dataForm: "MNIST 28×28 uint8 → float pad 32×32 → Q16 int32 → ElGamal (c1,c2)",
  },
  {
    id: "after_conv1",
    layer: "Conv1 (6×1×5×5)",
    server: "同态卷积",
    client: "ReLU + 池化 + 截断",
    shiftBits: 32,
    poolKernel: 2,
    shape: [1, 6, 28, 28],
    dataForm: "密文 [1,6,28,28] → 解密 → ReLU → AvgPool(2) → [1,6,14,14] → shift(32) → 重加密",
  },
  {
    id: "after_conv2",
    layer: "Conv2 (16×6×5×5)",
    server: "同态卷积",
    client: "ReLU + 池化 + 截断",
    shiftBits: 32,
    poolKernel: 2,
    shape: [1, 16, 10, 10],
    dataForm: "密文 [1,16,10,10] → 解密 → ReLU → AvgPool(2) → [1,16,5,5] → shift(32) → 重加密",
  },
  {
    id: "after_c3",
    layer: "C3 (FC 400→120)",
    server: "同态全连接",
    client: "ReLU + 截断",
    shiftBits: 32,
    shape: [1, 120],
    dataForm: "密文 [1,120] → 解密 → ReLU → shift(32) → 重加密",
  },
  {
    id: "after_fc4",
    layer: "FC4 (120→84)",
    server: "同态全连接",
    client: "ReLU + 截断",
    shiftBits: 32,
    shape: [1, 84],
    dataForm: "密文 [1,84] → 解密 → ReLU → shift(32) → 重加密",
  },
  {
    id: "after_fc5",
    layer: "FC5 (84→10)",
    server: "同态全连接",
    client: "logits → argmax",
    shape: [1, 10],
    dataForm: "密文 [1,10] → 解密 → Q32→float → argmax",
  },
];

export const LENET_CIFAR_PHASES = [
  {
    id: "initial",
    layer: "输入",
    server: "—",
    client: "定点加密",
    shape: [1, 3, 32, 32],
    dataForm: "CIFAR-10 3×32×32 uint8 → Q16 int32 → ElGamal (c1,c2)",
  },
  {
    id: "after_conv1",
    layer: "Conv1 (6×3×5×5)",
    server: "同态卷积",
    client: "ReLU + 池化 + 截断",
    shiftBits: 32,
    poolKernel: 2,
    shape: [1, 6, 28, 28],
    dataForm: "密文 [1,6,28,28] → 解密 → ReLU → AvgPool(2) → [1,6,14,14] → shift(32) → 重加密",
  },
  {
    id: "after_conv2",
    layer: "Conv2 (16×6×5×5)",
    server: "同态卷积",
    client: "ReLU + 池化 + 截断",
    shiftBits: 32,
    poolKernel: 2,
    shape: [1, 16, 10, 10],
    dataForm: "密文 [1,16,10,10] → 解密 → ReLU → AvgPool(2) → [1,16,5,5] → shift(32) → 重加密",
  },
  {
    id: "after_c3",
    layer: "C3 (FC 400→120)",
    server: "同态全连接",
    client: "ReLU + 截断",
    shiftBits: 32,
    shape: [1, 120],
    dataForm: "密文 [1,120] → 解密 → ReLU → shift(32) → 重加密",
  },
  {
    id: "after_fc4",
    layer: "FC4 (120→84)",
    server: "同态全连接",
    client: "ReLU + 截断",
    shiftBits: 32,
    shape: [1, 84],
    dataForm: "密文 [1,84] → 解密 → ReLU → shift(32) → 重加密",
  },
  {
    id: "after_fc5",
    layer: "FC5 (84→10)",
    server: "同态全连接",
    client: "logits → argmax",
    shape: [1, 10],
    dataForm: "密文 [1,10] → 解密 → Q32→float → argmax",
  },
];

export const AHE_PHASES = [
  {
    id: "initial",
    layer: "输入",
    server: "—",
    client: "定点加密",
    shape: [1, 1, 32, 32],
    dataForm: "uint8 28×28 → float pad 32×32 → Q16 int32 → ElGamal (c1,c2)",
  },
  {
    id: "after_conv",
    layer: "Conv",
    server: "同态卷积",
    client: "ReLU",
    shape: [1, 1, 32, 32],
    dataForm: "密文特征图 → 解密 → int32 激活",
  },
  {
    id: "after_pool",
    layer: "MaxPool",
    server: "同态池化",
    client: "右移截断",
    shiftBits: 26,
    shape: [1, 64],
    dataForm: "密文 → 解密 → shift → 重加密",
  },
  {
    id: "after_fc1",
    layer: "FC1",
    server: "同态全连接",
    client: "ReLU + 截断",
    shiftBits: 32,
    shape: [1, 16],
    dataForm: "密文 → 解密 → ReLU → shift → 重加密",
  },
  {
    id: "after_fc2",
    layer: "FC2",
    server: "同态全连接",
    client: "ReLU → logits",
    shape: [1, 10],
    dataForm: "密文 → 解密 → logits (Q16→float)",
  },
];

export const PREPROCESS_STAGES = [
  { id: "raw", title: "原始图像", desc: "MNIST 28×28 uint8" },
  { id: "padded", title: "零填充", desc: "居中 pad 至 32×32 float [0,1]" },
  { id: "normalized", title: "Min-Max 归一化", desc: "每图独立缩放到 [0,1]" },
  { id: "fixed", title: "定点化", desc: "× 2^16 → int32，供 AHE 加密" },
  { id: "digest", title: "输入摘要", desc: "SHA256(fixed_int32 bytes)" },
];

/** Return the correct phase array for a given model ID string. */
export function getPhasesForModelId(modelId) {
  const id = modelId ?? "";
  if (id.includes("lenet") && id.includes("mnist")) return LENET_MNIST_PHASES;
  if (id.includes("lenet")) return LENET_CIFAR_PHASES;
  return AHE_PHASES;
}

export const TRACE_CATEGORIES = {
  预处理: "info",
  P0: "default",
  P1: "default",
  P2: "default",
  P3: "warning",
  服务端: "success",
  客户端: "warning",
  完成: "success",
};
