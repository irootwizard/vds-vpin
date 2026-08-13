/** Network A AHE 推理阶段（与 vpin_backend.crypto.ahe.topology 对齐） */

export const AHE_PHASES = [
  { id: "initial", label: "输入加密" },
  { id: "after_conv", label: "同态卷积" },
  { id: "after_pool", label: "同态池化 + 截断" },
  { id: "after_fc1", label: "FC1 + 截断环" },
  { id: "after_fc2", label: "FC2 logits" },
] as const;

export type AhePhaseId = (typeof AHE_PHASES)[number]["id"];
