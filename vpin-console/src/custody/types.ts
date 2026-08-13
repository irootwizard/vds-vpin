export type CustodySessionStatus = "open" | "committed" | "cancelled";

export interface CustodyUploadSession {
  session_id: string;
  file_id: string;
  index_base: number;
  total_chunks: number;
  status: CustodySessionStatus;
  capability_mode: "data_only";
  created_at: string;
}

export interface CustodyChunkMeta {
  chunk_index: number;
  vads_index: number;
  digest_hex: string;
  byte_length: number;
}

export interface CustodyCommitResult {
  session_id: string;
  file_id: string;
  file_revision: number;
  manifest_digest_hex: string;
  chunk_count: number;
}

export interface DataBindingRecord {
  binding_id: string;
  file_id: string;
  manifest_digest_hex: string;
  vads_indices: number[];
  capability_mode: "data_only";
  sample_label?: string;
  /** Rust ahe-cli 预处理 input_digest_hex（Tauri 默认） */
  rust_input_digest_hex?: string;
  preprocess_lane?: "rust" | "js";
  created_at: string;
}

export interface IntegrityVerifyResult {
  ok: boolean;
  manifest_digest_hex: string;
  recomputed_digest_hex: string;
  checked_chunks: number;
  tampered_chunks: number[];
  message: string;
}

export interface CustodyDefaultsView {
  chunk_size_bytes: number;
  max_parallel_uploads: number;
  verify_mode: "vads_merkle";
  runtime: "local-shim";
}
