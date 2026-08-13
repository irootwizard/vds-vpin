// [TEMP-DEMO-TIMING] — remove before production
// 非 Network A 模型在 Tauri / 浏览器均走 timing-demo；参数见 modelCatalog.resolvePerfProfileKey

export interface PerfProfile {
  model_id: string;
  single_sec: number;
  /** 批量吞吐（张/秒）；与 single_sec 二选一配置，批量优先用此字段 */
  batch_img_per_sec: number;
  train_accuracy: number;
}

/** 模型族 × 数据集 计时基准（用户给定） */
export const PERF_PROFILES: Record<string, PerfProfile> = {
  "mnist-lenet": {
    model_id: "mnist-lenet",
    single_sec: 5,
    batch_img_per_sec: 1.0,
    train_accuracy: 0.9291,
  },
  "mnist-resnet": {
    model_id: "mnist-resnet",
    single_sec: 50,
    batch_img_per_sec: 3 / 50,
    train_accuracy: 0.9956,
  },
  "cifar-lenet": {
    model_id: "cifar-lenet",
    single_sec: 10,
    batch_img_per_sec: 0.6,
    train_accuracy: 0.56,
  },
  "cifar-resnet": {
    model_id: "cifar-resnet",
    single_sec: 100,
    /** 批量相对单图提速 5× → 100/5 s/张 */
    batch_img_per_sec: 5 / 100,
    train_accuracy: 0.57,
  },
};

export const AHE_PHASE_WEIGHTS: { phase_id: string; weight: number; label: string }[] = [
  { phase_id: "initial", weight: 0.1, label: "输入加密" },
  { phase_id: "after_conv", weight: 0.25, label: "同态卷积" },
  { phase_id: "after_pool", weight: 0.2, label: "同态池化 + 截断" },
  { phase_id: "after_fc1", weight: 0.25, label: "FC1 + 截断环" },
  { phase_id: "after_fc2", weight: 0.2, label: "FC2 logits" },
];

function clamp(v: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, v));
}

function normal(mean = 1, std = 0.025): number {
  const u1 = Math.random();
  const u2 = Math.random();
  const z = Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2);
  return mean + z * std;
}

/** Box-Muller → N(1,σ), clamped to [0.95, 1.05] */
export function jitterFactor(): number {
  return clamp(normal(1, 0.025), 0.95, 1.05);
}

export function jitterSeconds(baseSec: number): number {
  return baseSec * jitterFactor();
}

export function splitPhaseDurations(totalSec: number): { phase_id: string; label: string; sec: number }[] {
  const jittered = jitterSeconds(totalSec);
  const phases = AHE_PHASE_WEIGHTS.map((p) => ({
    phase_id: p.phase_id,
    label: p.label,
    sec: jittered * p.weight,
  }));
  const sum = phases.reduce((a, p) => a + p.sec, 0);
  const scale = jittered / sum;
  return phases.map((p) => ({ ...p, sec: p.sec * scale }));
}

export function simulateBatchAccuracy(n: number, trainAcc: number) {
  const displayAcc = trainAcc * 0.95;
  const wrong = Math.round(n * (1 - displayAcc));
  const correct = n - wrong;
  return { displayAcc, correct, wrong, total: n };
}

export function getPerfProfile(perfProfileKey: string): PerfProfile {
  return PERF_PROFILES[perfProfileKey] ?? PERF_PROFILES["mnist-lenet"];
}

export function estimateRunDurationSec(perfProfileKey: string, batchSize: number): number {
  const profile = getPerfProfile(perfProfileKey);
  if (batchSize <= 1) return jitterSeconds(profile.single_sec);
  return jitterSeconds(batchSize / profile.batch_img_per_sec);
}
