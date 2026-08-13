export interface BridgeError {
  code: string;
  message: string;
  details?: unknown;
}

export interface BridgeResponse<T> {
  ok: boolean;
  data?: T;
  error?: BridgeError;
}

export type WorkflowStage = "0" | "A" | "B" | "C";
export type WorkflowNodeStatus = "pending" | "active" | "done" | "failed";

export interface WorkflowNode {
  id: string;
  stage: WorkflowStage;
  label: string;
  status: WorkflowNodeStatus;
}

export type CustodyCapabilityMode =
  | "data_only"
  | "inference_peer"
  | "proof_verification"
  | "full_proxy";

export interface CustodyCapabilities {
  implemented: CustodyCapabilityMode[];
  placeholder: CustodyCapabilityMode[];
  runtime: string;
  _temp_note?: string;
}

export interface ModelInfo {
  model_id: string;
  name: string;
  family: string;
  dataset: string;
  train_accuracy?: number;
  placeholder?: boolean;
}

export interface RunConfig {
  model_id: string;
  custody_mode: "hosted" | "client_local";
  capability_mode: CustodyCapabilityMode;
  batch_size: number;
  privacy_mode: "balanced" | "strict" | "performance";
  /** Network A Rust 引擎：默认 rust-ark，可选 rust-ec */
  rust_engine?: "rust-ark" | "rust-ec";
  /** 数据集 catalog id（mnist-test / cifar10-test 等） */
  dataset_id?: string;
  /** 单图样本序号（通用；兼容 mnist_index） */
  sample_index?: number;
  /** @deprecated 使用 sample_index */
  mnist_index?: number;
  /** 批量起始序号（含） */
  mnist_start?: number;
  /** 批量结束序号（含） */
  mnist_end?: number;
}

export type RunStatus =
  | "created"
  | "preflight"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

export interface ComputationProofState {
  phase: "idle" | "plan" | "challenge" | "prove" | "verify" | "done" | "failed" | "skipped";
  enabled: boolean;
  ok?: boolean;
  verify_ok?: boolean;
  verify_message?: string;
  proof_coverage?: string;
  scalar_trace_digest_hex?: string;
  cm_w_hex?: string;
  cm_w_digest_hex?: string;
  cm_x_hex?: string;
  cm_x_digest_hex?: string;
  cps_cm_hex?: string;
  total_pt_mul?: number;
  total_pt_add?: number;
  n_w?: number;
  n2_eq_q1?: boolean;
  prove_ms?: number;
  gamma_prefix?: string;
  /** P4 完整客户端挑战（γ / γ_add / γ_mult） */
  challenge?: {
    gamma: string;
    gamma_add: string;
    gamma_mult: string;
    num_pt_add: number;
    num_pt_mult: number;
  };
  artifact_path?: string;
  message?: string;
}

export interface RunRecord {
  run_id: string;
  status: RunStatus;
  config: RunConfig;
  created_at: string;
  workflow_nodes: WorkflowNode[];
  batch_completed?: number;
  batch_total?: number;
  display_accuracy?: number;
  wrong_count?: number;
  correct_count?: number;
  /** rust-ark | timing-demo */
  inference_engine?: string;
  elapsed_ms?: number;
  prediction?: number;
  label?: number;
  mnist_index?: number;
  /** Network A 计算量证明（P4–P6，与 AHE 独立、非阻塞） */
  computation_proof?: ComputationProofState;
}

export interface InferencePhaseId {
  phase_id:
    | "initial"
    | "after_conv"
    | "after_pool"
    | "after_fc1"
    | "after_fc2"
    | "done";
}

export interface InferenceEvent {
  run_id: string;
  event:
    | "phase_started"
    | "phase_completed"
    | "batch_progress"
    | "run_completed"
    | "run_failed"
    | "proof_progress"
    | "proof_completed"
    | "proof_failed";
  phase_id?: InferencePhaseId["phase_id"];
  batch_index?: number;
  batch_total?: number;
  elapsed_ms?: number;
  message?: string;
  display_accuracy?: number;
  wrong_count?: number;
  correct_count?: number;
  proof?: ComputationProofState;
}

export interface EventLogEntry {
  id: string;
  ts: string;
  channel: string;
  message: string;
  level: "info" | "warn" | "error" | "success";
}

export interface StartupOptimizerResult {
  startup_id: string;
  status: "ok" | "degraded" | "blocked" | "failed";
  detect_mode: "full" | "skipped_user_refused";
  bootstrap_timestamp: string;
  device_profile: {
    device_category: string;
    device_class: string;
    cpu_cores: number;
    memory_mb: number;
  };
  deployment_recommendation: {
    custody_mode: "hosted" | "client_local";
    rationale: string;
  };
}

export interface PreflightCheck {
  id: string;
  label: string;
  status: "pass" | "fail" | "warn" | "pending";
  detail?: string;
}

export interface PreflightResult {
  run_id: string;
  checks: PreflightCheck[];
  can_start: boolean;
}
