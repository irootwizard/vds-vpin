// [TEMP-LOCAL-CUSTODY] — 本地托管 Shim，不连接 :8003；上线后替换为 HTTP 客户端

import { appendEventLog } from "@/bridge/eventBus";
import type {
  CustodyChunkMeta,
  CustodyCommitResult,
  CustodyDefaultsView,
  CustodyUploadSession,
  DataBindingRecord,
  IntegrityVerifyResult,
} from "@/custody/types";

const CHUNK_SIZE = 4096;

interface SessionStore {
  session: CustodyUploadSession;
  chunks: Map<number, Uint8Array>;
  /** 创建时的分片副本，用于恢复完整性演示 */
  originalChunks: Map<number, Uint8Array>;
  chunkDigests: Map<number, string>;
  tampered: Set<number>;
  manifest_digest_hex?: string;
  rust_input_digest_hex?: string;
  preprocess_lane?: "rust" | "js";
}

function cloneChunkMap(source: Map<number, Uint8Array>): Map<number, Uint8Array> {
  const out = new Map<number, Uint8Array>();
  for (const [idx, bytes] of source.entries()) {
    out.set(idx, new Uint8Array(bytes));
  }
  return out;
}

let indexSeq = 1000;
let sessionSeq = 0;
let bindingSeq = 0;

const sessions = new Map<string, SessionStore>();
const bindings = new Map<string, DataBindingRecord>();

async function sha256Hex(data: ArrayBuffer | Uint8Array): Promise<string> {
  const buf = data instanceof Uint8Array ? data : new Uint8Array(data);
  const hash = await crypto.subtle.digest("SHA-256", buf);
  return [...new Uint8Array(hash)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function manifestFromChunks(chunks: Map<number, Uint8Array>): Promise<string> {
  const ordered = [...chunks.entries()].sort((a, b) => a[0] - b[0]);
  const parts: string[] = [];
  for (const [idx, bytes] of ordered) {
    parts.push(`${idx}:${await sha256Hex(bytes)}`);
  }
  return sha256Hex(new TextEncoder().encode(parts.join("|")));
}

function payloadFromIndexedDataset(datasetId: string, index: number): Uint8Array {
  const seed = `vpin-custody-${datasetId}-v1|index=${index}|fixed_q16`;
  const raw = new TextEncoder().encode(seed);
  const out = new Uint8Array(784 * 4);
  for (let i = 0; i < out.length; i += 1) {
    out[i] = raw[i % raw.length] ^ (index & 0xff) ^ (i & 0xff);
  }
  return out;
}

/** @deprecated use payloadFromIndexedDataset */
function payloadFromMnist(index: number): Uint8Array {
  return payloadFromIndexedDataset("mnist-test", index);
}

async function payloadFromFile(name: string, bytes: Uint8Array): Promise<Uint8Array> {
  const header = new TextEncoder().encode(`vpin-custody-upload-v1|${name}|`);
  const out = new Uint8Array(header.length + bytes.length);
  out.set(header, 0);
  out.set(bytes, header.length);
  return out;
}

function splitChunks(payload: Uint8Array): Map<number, Uint8Array> {
  const map = new Map<number, Uint8Array>();
  let offset = 0;
  let idx = 0;
  while (offset < payload.length) {
    const end = Math.min(offset + CHUNK_SIZE, payload.length);
    map.set(idx, payload.slice(offset, end));
    offset = end;
    idx += 1;
  }
  if (map.size === 0) map.set(0, new Uint8Array(0));
  return map;
}

export function getCustodyDefaults(): CustodyDefaultsView {
  return {
    chunk_size_bytes: CHUNK_SIZE,
    max_parallel_uploads: 4,
    verify_mode: "vads_merkle",
    runtime: "local-shim",
  };
}

export async function createUploadSession(opts: {
  fileId?: string;
  datasetId?: string;
  mnistIndex?: number;
  sampleIndex?: number;
  fileName?: string;
  fileBytes?: Uint8Array;
  rustInputDigestHex?: string;
  preprocessLane?: "rust" | "js";
}): Promise<{ session: CustodyUploadSession; chunks: CustodyChunkMeta[] }> {
  const datasetId = opts.datasetId ?? "mnist-test";
  const sampleIndex = opts.sampleIndex ?? opts.mnistIndex;

  const fileId =
    opts.fileId ??
    (sampleIndex != null
      ? `${datasetId}-${sampleIndex}`
      : `upload-${Date.now().toString(36)}`);

  let payload: Uint8Array;
  if (opts.fileBytes && opts.fileName) {
    payload = await payloadFromFile(opts.fileName, opts.fileBytes);
  } else if (sampleIndex != null) {
    payload = payloadFromIndexedDataset(datasetId, sampleIndex);
  } else {
    throw new Error("需要样本序号或上传文件");
  }

  const chunkMap = splitChunks(payload);
  const sessionId = `cust-${++sessionSeq}-${Date.now().toString(36)}`;
  const indexBase = indexSeq;
  indexSeq += chunkMap.size;

  const session: CustodyUploadSession = {
    session_id: sessionId,
    file_id: fileId,
    index_base: indexBase,
    total_chunks: chunkMap.size,
    status: "open",
    capability_mode: "data_only",
    created_at: new Date().toISOString(),
  };

  const store: SessionStore = {
    session,
    chunks: cloneChunkMap(chunkMap),
    originalChunks: cloneChunkMap(chunkMap),
    chunkDigests: new Map(),
    tampered: new Set(),
    rust_input_digest_hex: opts.rustInputDigestHex,
    preprocess_lane: opts.preprocessLane ?? (opts.rustInputDigestHex ? "rust" : "js"),
  };

  const metas: CustodyChunkMeta[] = [];
  for (const [chunkIndex, bytes] of store.chunks.entries()) {
    const digest = await sha256Hex(bytes);
    store.chunkDigests.set(chunkIndex, digest);
    metas.push({
      chunk_index: chunkIndex,
      vads_index: indexBase + chunkIndex,
      digest_hex: digest,
      byte_length: bytes.length,
    });
  }

  sessions.set(sessionId, store);
  const lane = store.preprocess_lane ?? "js";
  appendEventLog(
    "local-shim://custody",
    `upload session ${sessionId} file=${fileId} chunks=${chunkMap.size} lane=${lane}`,
  );
  return { session, chunks: metas };
}

export async function commitUploadSession(sessionId: string): Promise<CustodyCommitResult> {
  const store = sessions.get(sessionId);
  if (!store) throw new Error(`session ${sessionId} not found`);
  if (store.session.status !== "open") throw new Error("session 已关闭");

  const manifest = await manifestFromChunks(store.chunks);
  store.manifest_digest_hex = manifest;
  store.session.status = "committed";

  appendEventLog("local-shim://custody", `commit ${sessionId} digest=${manifest.slice(0, 16)}…`, "success");

  return {
    session_id: sessionId,
    file_id: store.session.file_id,
    file_revision: 1,
    manifest_digest_hex: manifest,
    chunk_count: store.chunks.size,
  };
}

export async function createBinding(sessionId: string, sampleLabel?: string): Promise<DataBindingRecord> {
  const store = sessions.get(sessionId);
  if (!store) throw new Error(`session ${sessionId} not found`);
  if (store.session.status !== "committed" || !store.manifest_digest_hex) {
    throw new Error("请先 commit 上传会话");
  }

  const vadsIndices = [...store.chunks.keys()]
    .sort((a, b) => a - b)
    .map((i) => store.session.index_base + i);

  const binding: DataBindingRecord = {
    binding_id: `bind-${++bindingSeq}-${Date.now().toString(36)}`,
    file_id: store.session.file_id,
    manifest_digest_hex: store.manifest_digest_hex,
    vads_indices: vadsIndices,
    capability_mode: "data_only",
    sample_label: sampleLabel,
    rust_input_digest_hex: store.rust_input_digest_hex,
    preprocess_lane: store.preprocess_lane,
    created_at: new Date().toISOString(),
  };

  bindings.set(binding.binding_id, binding);
  appendEventLog("local-shim://custody", `binding ${binding.binding_id} vads=${vadsIndices.length}`, "success");
  return binding;
}

export async function verifyBindingIntegrity(bindingId: string): Promise<IntegrityVerifyResult> {
  const binding = bindings.get(bindingId);
  if (!binding) throw new Error(`binding ${bindingId} not found`);

  const store = [...sessions.values()].find(
    (s) => s.session.file_id === binding.file_id && s.manifest_digest_hex,
  );
  if (!store) {
    return {
      ok: false,
      manifest_digest_hex: binding.manifest_digest_hex,
      recomputed_digest_hex: "",
      checked_chunks: 0,
      tampered_chunks: [],
      message: "托管会话已丢失，请重新上传",
    };
  }

  const tampered: number[] = [];
  for (const [idx, bytes] of store.chunks.entries()) {
    const expected = store.chunkDigests.get(idx)!;
    const actual = await sha256Hex(bytes);
    if (actual !== expected || store.tampered.has(idx)) tampered.push(idx);
  }

  const recomputed = await manifestFromChunks(store.chunks);
  const ok = tampered.length === 0 && recomputed === binding.manifest_digest_hex;

  const result: IntegrityVerifyResult = {
    ok,
    manifest_digest_hex: binding.manifest_digest_hex,
    recomputed_digest_hex: recomputed,
    checked_chunks: store.chunks.size,
    tampered_chunks: tampered,
    message: ok
      ? "VADS 分片摘要与 manifest 一致，数据未篡改"
      : tampered.length
        ? `检测到 ${tampered.length} 个分片摘要不匹配（可能已篡改）`
        : "manifest 摘要不一致",
  };

  appendEventLog(
    "local-shim://custody",
    ok ? `verify PASS ${bindingId}` : `verify FAIL ${bindingId}`,
    ok ? "success" : "error",
  );
  return result;
}

/** 演示用：篡改一个分片后再验证应 FAIL */
export function simulateTamper(sessionId: string, chunkIndex = 0): boolean {
  const store = sessions.get(sessionId);
  if (!store) return false;
  const chunk = store.chunks.get(chunkIndex);
  if (!chunk || chunk.length === 0) return false;
  const copy = new Uint8Array(chunk);
  copy[0] ^= 0xff;
  store.chunks.set(chunkIndex, copy);
  store.tampered.add(chunkIndex);
  appendEventLog("local-shim://custody", `simulate tamper session=${sessionId} chunk=${chunkIndex}`, "warn");
  return true;
}

/** 演示用：从原始分片副本恢复，清除篡改标记 */
export function restoreSessionIntegrity(sessionId: string): boolean {
  const store = sessions.get(sessionId);
  if (!store) return false;
  store.chunks = cloneChunkMap(store.originalChunks);
  store.tampered.clear();
  appendEventLog("local-shim://custody", `restore integrity session=${sessionId}`, "success");
  return true;
}

/** 丢弃当前托管会话及关联 binding（可重新从步骤 1 开始） */
export function discardCustodyWorkflow(sessionId: string, bindingId?: string): boolean {
  const store = sessions.get(sessionId);
  if (!store) return false;

  if (bindingId) {
    bindings.delete(bindingId);
  } else {
    for (const [id, b] of bindings.entries()) {
      if (b.file_id === store.session.file_id) bindings.delete(id);
    }
  }

  sessions.delete(sessionId);
  appendEventLog(
    "local-shim://custody",
    `discard workflow session=${sessionId}${bindingId ? ` binding=${bindingId}` : ""}`,
  );
  return true;
}

export function listBindings(): DataBindingRecord[] {
  return [...bindings.values()].sort((a, b) => b.created_at.localeCompare(a.created_at));
}

export function listSessions(): CustodyUploadSession[] {
  return [...sessions.values()].map((s) => ({ ...s.session }));
}

export function getBinding(bindingId: string): DataBindingRecord | undefined {
  return bindings.get(bindingId);
}

export function deleteBinding(bindingId: string): boolean {
  const removed = bindings.delete(bindingId);
  if (removed) {
    appendEventLog("local-shim://custody", `delete binding ${bindingId}`);
  }
  return removed;
}
