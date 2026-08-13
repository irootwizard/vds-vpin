# vPIN Client Bridge API（Tauri IPC）

> **版本**：v0.2  
> **状态**：接口定稿 · Rust 实现待开发  
> **消费者**：[`vpin-console`](./vpin-console-ui-mock.md) 新 UI（Vue）  
> **实现方**：`vpin-console/src-tauri/src/bridge/`（Rust Tauri 2）  
> **架构对齐**：[vpin-平台顶层抽象架构.md](../architecture/vpin-平台顶层抽象架构.md) 附录 C、[vpin-平台工作流程图.html](../architecture/vpin-平台工作流程图.html)（交互节点，非视觉）  
> **托管服务器**：[vpin-custody-server-软件架构.md](../architecture/vpin-custody-server-软件架构.md)、[vpin-custody-server-接口规格.md](../architecture/vpin-custody-server-接口规格.md)

---

## 1. 概述

Client Bridge 是 **vpin-console 前端与本地 Rust 运行时**之间的唯一契约。前端通过 Tauri **`invoke`** 调用命令、通过 **`listen`** 订阅事件；**不**直接连接 WebSocket、**不**读写 legacy `useProtocolSession` localStorage。

| 项 | 约定 |
|----|------|
| 传输 | Tauri Command + Event（非 HTTP Agent） |
| 响应信封 | 所有 command 返回 `BridgeResponse<T>` |
| 外部依赖 | `vpin-backend` REST、`vpin-custody-server` HTTPS、子进程 `ahe-cli` |
| legacy UI | [`vpin_frontend`](../../vpin_frontend/vpin-frontend) 暂不使用本 Bridge |

### ⚠️ [TEMP-LOCAL-CUSTODY] 前端实现期临时覆盖（后续必删）

> 检索标记：**`TEMP-LOCAL-CUSTODY`**。正式契约仍为 §1.1 三端 + §4.2 HTTP；**当前实现**不启 `vpin-custody-server`，`bridge_custody_*` 走 **`LocalCustodyShim`**（内存状态机 + fixture），用户选 `hosted` 亦在本地完成阶段 A。取消后改回 `reqwest` → `:8003`。详见 [UI Mock 方案 §TEMP](./vpin-console-ui-mock.md)。

### 1.1 三端部署与 Bridge 职责

| 角色 | 工程 | 默认端口 | Bridge 访问方式 |
|------|------|----------|-----------------|
| 无头密态推理服务 | `vpin-backend` | `8000` | `bridge_proxy_*` → `/api/v1/*` |
| 信任数据托管服务器 | `vpin-custody-server` | **`8003`** | `bridge_custody_*` → `/api/v1/*` + `/v1/*` |
| 本地编排 | Tauri `bridge` 模块 | — | 设备检测、P0–P6 编排、JWT 注入 |

**重要边界**（与 [托管服务器软件架构 §5](../architecture/vpin-custody-server-软件架构.md#5-工程优化器客户端-vs-服务端) 一致）：

| 数据 | 产生方 | 是否上传托管服务器 |
|------|--------|-------------------|
| `SchemeSelection` / `PrivacyModePreference` | **客户端** | **否**（托管不参与选型） |
| `CustodyOptimizerProfile` | 客户端 `CustodyOptimizer` | **否**（当前里程碑） |
| `InferenceOptimizerProfile` | 客户端 `InferenceOptimizer` | **否** |
| `CustodyServerDefaults` | 托管服务器常量 | 客户端**只读**展示（可选） |
| `DataBindingRecord` | 客户端组装或 `POST /v1/bindings` | 是（hosted） |

托管能力里程碑：**仅 `data_only` 实现**；`inference_peer` / `proof_verification` / `full_proxy` 托管侧返回 **HTTP 501**，Bridge 映射为 `CUSTODY_CAPABILITY_NOT_IMPLEMENTED`。

---

## 2. 调用约定

### 2.1 Command 命名

- 注册名：`bridge_<domain>_<action>`（snake_case）
- 示例：`invoke('bridge_bootstrap_detect', { consent: true })`

### 2.2 响应信封

```typescript
interface BridgeError {
  code: string;
  message: string;
  details?: unknown;
}

interface BridgeResponse<T> {
  ok: boolean;
  data?: T;
  error?: BridgeError;
  request_id: string; // UUID v4
}
```

Rust 侧使用 `serde` 序列化；`ok === false` 时 `data` 为空、`error` 必填。

### 2.3 事件

| 事件名 | Payload | 说明 |
|--------|---------|------|
| `bridge://workflow-updated` | `WorkflowRun` | 工作流阶段/节点变化 |
| `bridge://inference-event` | `InferenceEvent` | P3 密态环实时消息（仅元数据） |
| `bridge://custody-progress` | `CustodyProgressEvent` | OVDS 上传进度 |
| `bridge://log` | `BridgeLogEvent` | EventLog 面板 |

```typescript
interface CustodyProgressEvent {
  session_id: string;
  state: CustodySessionState;
  chunks_done: number;
  chunks_total: number;
}

interface BridgeLogEvent {
  level: "debug" | "info" | "warn" | "error";
  message: string;
  ts: string;
}
```

订阅示例：

```typescript
import { listen } from "@tauri-apps/api/event";
await listen<InferenceEvent>("bridge://inference-event", (e) => { /* ... */ });
```

### 2.4 错误码

| code | 说明 | UI 建议 |
|------|------|---------|
| `OK` | 成功 | — |
| `NOT_FOUND` | run / binding / session 不存在 | 提示重新创建 |
| `NOT_IMPLEMENTED` | Rust 未实现 | 显示「客户端待升级」+ mock 降级 |
| `BLOCKED` | `execution_trust === untrusted` | 全屏阻断，仅开放设置 |
| `PREFLIGHT_FAIL` | Preflight 门禁未通过 | 展示 `preflight_checks` 失败项 |
| `CUSTODY_ERROR` | 托管方 / OVDS 错误 | 展示 `details` |
| `CUSTODY_CAPABILITY_NOT_IMPLEMENTED` | 托管 501（非 data_only 能力） | 灰显能力卡片 + 服务端 `mode` |
| `CUSTODY_AUTH_DENIED` | 托管 401 / 403 | 跳转设置补 JWT |
| `CUSTODY_CONFLICT` | 托管 409 revision 冲突 | 提示刷新 manifest |
| `CUSTODY_SESSION_GONE` | 托管 410 会话已取消 | 重新创建 upload-session |
| `INFERENCE_ERROR` | 推理 WS / 子进程中断 | 可重试 / 取消 run |
| `VERIFY_FAIL` | 验证业务失败（非异常） | 展示 `VerificationReport` |
| `INTERNAL` | 未预期错误 | 记录 `request_id` |

---

## 3. 共享类型

字段来源：架构附录 C + [`vpin_backend/protocol/messages.py`](../../vpin-backend/vpin_backend/protocol/messages.py)。

### 3.1 工作流

```typescript
type WorkflowPhase = "bootstrap" | "custody" | "inference" | "verification" | "done";
type WorkflowLane = "client" | "custody" | "gov" | "vads" | "infer" | "verify";
type WorkflowStatus = "idle" | "running" | "pass" | "fail" | "blocked";

interface WorkflowRun {
  run_id: string;
  workflow_phase: WorkflowPhase;
  workflow_node: string;
  lane?: WorkflowLane;
  status: WorkflowStatus;
  updated_at: string;
}
```

**`workflow_node` 枚举（与工作流程图方框对应）**：

| workflow_node | 阶段 | 说明 |
|---------------|------|------|
| `auth_login` | 0 | OIDC / JWT（可选） |
| `bootstrap_detect` | 0 | StartupOptimizer |
| `detect_consent` | 0 | 同意/拒绝设备检测 |
| `scheme_select` | 0 | CiphertextSchemeSelector |
| `privacy_mode` | 0 | PrivacyModePreference |
| `preprocess` | A | 客户端预处理 |
| `custody_mode_decision` | A | hosted / client_local |
| `capability_mode_decision` | A | CustodyCapabilityMode 四档 |
| `ovds_upload` | A | append / verify |
| `binding_ready` | A | DataBindingRecord |
| `p0_session_start` | B | SessionStart |
| `preflight` | B | Preflight 门禁 |
| `p1_model_commit` | B | P1 cm_W |
| `p2_input_digest` | B | P2 InputDigest |
| `p3_truncate_loop` | B | P3 多轮环 |
| `p4_challenge` | B | γ / 抽样挑战 |
| `p5_proof` | B | ComputeProof |
| `verify_inference` | C | 模型推理验证器 |
| `verify_flow` | C | 密态流程验证器 |
| `report_ready` | C | VerificationReport |
| `client_reverify` | C | 可选本地复核 |

### 3.2 启动与设备

```typescript
interface SecureExecutionSignals {
  app_sandboxed: boolean;
  tee_available: boolean;
  debugger_attached: boolean;
  privileged_escalation: boolean;
  emulator_or_vm: boolean;
  secure_storage_available: boolean;
}

interface DeviceProfile {
  device_category: "edge" | "compute" | "cloud";
  device_class:
    | "edge_cpu" | "edge_gpu"
    | "compute_cpu" | "compute_gpu"
    | "cloud_vm" | "cloud_gpu";
  cpu_cores: number;
  memory_available_mb: number;
  accelerator: "none" | "integrated_gpu" | "discrete_gpu" | "cloud_gpu";
  network_rtt_ms: number;
  execution_trust: "trusted" | "constrained" | "untrusted";
  secure_execution: SecureExecutionSignals;
  detect_mode: "full" | "skipped_user_refused";
  detect_timestamp: string;
}

interface InferenceOptimizerProfile {
  device_category: DeviceProfile["device_category"];
  device_class: DeviceProfile["device_class"];
  memory_budget_mb: number;
  concurrency: number;
  engine_tier: "lightweight" | "balanced" | "high_throughput";
  batch_key_reuse: boolean;
  pipeline_depth: number;
  offload_policy: "local_only" | "hybrid" | "remote_preferred";
}

interface CustodyOptimizerProfile {
  enabled: boolean;
  chunk_size_mb: number;
  max_parallel_upload: number;
  chunk_count?: number;
  rtt_ms?: number;
  cpu_cores?: number;
  agg_timeout_ms?: number;
  parallel_downloads?: number;
  parallel_verify?: number;
  default_verify_strategy?: "single_verify" | "aggregate" | "parallel_single";
  transport: "https_tls12";
}

interface DeploymentRecommendation {
  custody_mode: "hosted" | "client_local";
  inference_peer: "client_local" | "custody_host";
  verifier_target: "client_local" | "custody_host";
  offload_policy: InferenceOptimizerProfile["offload_policy"];
  rationale: "edge_low_compute" | "detection_skipped" | "network_degraded" | "user_override";
  user_confirm_required: boolean;
}

interface StartupOptimizerResult {
  startup_id: string;
  status: "ok" | "degraded" | "blocked" | "failed";
  detect_mode: "full" | "skipped_user_refused";
  bootstrap_timestamp: string;
  device_profile: DeviceProfile;
  inference_profile: InferenceOptimizerProfile;
  custody_profile: CustodyOptimizerProfile;
  deployment_recommendation: DeploymentRecommendation;
}
```

### 3.3 密态方案

```typescript
interface PrivacyModePreference {
  privacy_mode: "strict" | "balanced" | "performance" | "bandwidth" | "custom";
  weight_communication: number;
  weight_inference_time: number;
  weight_crypto_load: number;
  weight_security: number;
  preferred_scheme_id?: string;
  preferred_verification?: "strict_proof" | "game_sampling" | "mpc_protocol" | "auto";
}

interface ComputeParityGate {
  eligible: boolean;
  parity_mode?: "client_vs_inference" | "custody_vs_inference";
  custody_non_collusion?: boolean;
  peer_compute_delta_ratio?: number;
}

interface SchemeSelectionRequest {
  model_family: string;
  modality: string;
  param_count?: number;
  target_accuracy?: number;
  device_profile: DeviceProfile;
  compute_parity_gate?: ComputeParityGate;
  privacy_mode_preference: PrivacyModePreference;
  preferred_scheme_id?: string;
}

interface SchemeSelection {
  scheme: string;
  nonlinear_policy: string;
  verification_path: "strict_proof" | "game_sampling" | "mpc_protocol";
  compute_paradigm: "he" | "mpc";
  deploy_plan_ref?: string;
  selection_rationale: string;
  estimated_cost_profile?: Record<string, number>;
}
```

### 3.4 数据绑定与托管

```typescript
type CustodyCapabilityMode =
  | "data_only"
  | "inference_peer"
  | "proof_verification"
  | "full_proxy";

interface DataBindingRecord {
  binding_id: string;
  owner_id: string;
  tenant_id?: string;
  custody_mode: "hosted" | "client_local";
  capability_mode: CustodyCapabilityMode;
  auth_target: "custody_host" | "inference_server";
  inference_peer: "client_local" | "custody_host";
  verifier_target: "client_local" | "custody_host";
  ovds_file_id?: string;
  vads_indices?: number[];
  data_digest: string;
  ovds_verify_ref?: string;
  binding_timestamp: string;
}

type CustodySessionState =
  | "CREATED"
  | "UPLOADING"
  | "READY"
  | "COMMITTING"
  | "COMMITTED"
  | "CANCELLED"
  | "FAILED";

interface CustodySession {
  session_id: string;
  state: CustodySessionState;
  tenant_id: string;
  file_id: string;
  file_revision?: string;
  custody_host_endpoint: string;
  capability_mode: CustodyCapabilityMode;
  chunks_total?: number;
  chunks_done?: number;
  index_base?: number;
  ovds_verify_ref?: string;
  recomposed_hash?: string;
}

/** GET /api/v1/capabilities — 托管方已实现能力声明 */
interface CustodyCapabilities {
  implemented: CustodyCapabilityMode[];
  placeholder: CustodyCapabilityMode[];
  runtime: "vpin-custody-server";
}

/** POST /v1/files/upload-sessions 响应摘要 */
interface UploadSessionCreated {
  session_id: string;
  file_id: string;
  index_base: number;
  total_chunks: number;
  chunk_upload_path_template: string;
  capability_mode: CustodyCapabilityMode;
}

interface ChunkUploadResult {
  chunk_index: number;
  vads_index: number;
  accepted: boolean;
}

interface FileManifest {
  file_id: string;
  file_revision: string;
  file_hash: string;
  chunk_count: number;
  chunk_map: Record<string, number>;
}

interface CustodyServerDefaultsView {
  max_parallel_upload: number;
  chunk_size_mb: number;
  verify_strategy: "single_verify" | "aggregate" | "parallel_single";
  batch_size: number;
  parallel_downloads: number;
  parallel_verify: number;
  note: "server_side_only";
}
```

**`custody_mode` vs `capability_mode`**（正交）：

| 字段 | 问题 |
|------|------|
| `custody_mode` | 数据存哪里（`hosted` / `client_local`） |
| `capability_mode` | 托管方代理哪些环节（四档） |

典型组合见 [托管软件架构 §3.2](../architecture/vpin-custody-server-软件架构.md#32-典型-databindingrecord-组合)；UI 在绑定步骤须同时展示二者，并以 `bridge_custody_get_capabilities` 结果禁用未实现档位。

### 3.5 推理会话

```typescript
type ProtocolPhase = "P0" | "P1" | "P2" | "P3" | "P4" | "P5" | "P6";

interface PreflightCheck {
  id:
    | "binding_valid"
    | "device_trust"
    | "parity_gate"
    | "model_deployable"
    | "scheme_compatible"
    | "capability_supported";
  label: string;
  status: "pass" | "fail" | "warn";
  message?: string;
}

interface InferenceRun {
  run_id: string;
  binding_id: string;
  model_id: string;
  session_id?: string;
  protocol_phase: ProtocolPhase;
  workflow: WorkflowRun;
  preflight_status: "pending" | "pass" | "fail";
  preflight_checks: PreflightCheck[];
  scheme_selection: SchemeSelection;
  startup_id: string;
}

interface SessionStartPayload {
  client_version: string;
  ahe_params_id: string;
  device_profile_summary?: {
    device_category: DeviceProfile["device_category"];
    execution_trust: DeviceProfile["execution_trust"];
    detect_mode: DeviceProfile["detect_mode"];
  };
  inference_profile_summary?: {
    engine_tier: InferenceOptimizerProfile["engine_tier"];
    offload_policy: InferenceOptimizerProfile["offload_policy"];
  };
  ovds_binding_ref?: string;
}

interface SessionAccept {
  session_id: string;
  server_version: string;
  model_catalog_epoch: string;
}
```

### 3.6 P3 消息（UI 元数据）

UI **不得**接收原始密文字节；仅下列元数据类型。

```typescript
interface TruncateRequest {
  phase_id: string;
  bits: number;
  shape: number[];
  client_action: string;
  shift_bits?: number;
}

interface CiphertextPayloadMeta {
  phase_id: string;
  tensor_part: string;
  chunk_index: number;
  total_chunks: number;
  byte_length: number;
}

interface InferenceComplete {
  num_pt_add: number;
  num_pt_mult: number;
  witness_root?: string;
}

interface ProofBundle {
  proof_coverage: string;
  prove_time_ms: number;
  trace_digest?: string;
  rlc_binding?: string;
}

type InferenceEvent =
  | { type: "phase_changed"; phase: ProtocolPhase }
  | { type: "truncate_request"; payload: TruncateRequest }
  | { type: "ciphertext_payload"; payload: CiphertextPayloadMeta }
  | { type: "inference_complete"; payload: InferenceComplete }
  | { type: "proof_bundle"; payload: ProofBundle }
  | { type: "error"; code: string; message: string };

interface AheTraceEntry {
  ts: string;
  phase_id: string;
  direction: "server_to_peer" | "peer_to_server";
  message_type: "TruncateRequest" | "CiphertextPayload" | "InferenceComplete";
  byte_estimate?: number;
}
```

### 3.7 验证

```typescript
interface InferenceVerdict {
  status: "pass" | "fail";
  verification_path: string;
  proof_coverage?: string;
  failure_code?: string;
}

interface ClientReverify {
  status: "pass" | "fail" | "mismatch";
  privacy_integrity?: "pass" | "fail";
  inference_integrity?: "pass" | "fail";
  compared_at: string;
}

interface VerificationReport {
  session_id: string;
  run_id: string;
  privacy_integrity: "pass" | "fail";
  inference_integrity: "pass" | "fail";
  inference_verdict: InferenceVerdict;
  verification_path: "strict_proof" | "game_sampling" | "mpc_protocol";
  proof_coverage: string;
  verifier_target: "client_local" | "custody_host";
  client_reverify?: ClientReverify;
  artifacts: {
    pi_ref?: string;
    witness_root?: string;
    ovds_verify_ref?: string;
    trace_digest?: string;
  };
}
```

### 3.8 设置

```typescript
interface ClientSettings {
  backend_url: string;
  custody_host_endpoint: string;
  custody_jwt?: string;
  inference_ws_url?: string;
  repo_root?: string;
}
```

**默认**：

- `backend_url` = `http://127.0.0.1:8000/api/v1`
- `custody_host_endpoint` = `http://127.0.0.1:8003`（生产须 `https://`）

---

## 4. Command 参考

### 4.1 Bootstrap（阶段 0）

#### `bridge_bootstrap_detect`

| | |
|--|--|
| **参数** | `{ consent: boolean }` |
| **返回** | `BridgeResponse<StartupOptimizerResult>` |
| **行为** | `consent=true` → DeviceDetector；`false` → FallbackBaselineProfile |
| **阻断** | `execution_trust=untrusted` → `status=blocked`，`error.code=BLOCKED` |

#### `bridge_bootstrap_get`

| | |
|--|--|
| **参数** | 无 |
| **返回** | `BridgeResponse<StartupOptimizerResult \| null>` |

#### `bridge_bootstrap_redetect`

| | |
|--|--|
| **参数** | 无 |
| **返回** | `BridgeResponse<StartupOptimizerResult>` |

#### `bridge_scheme_select`

| | |
|--|--|
| **参数** | `SchemeSelectionRequest` |
| **返回** | `BridgeResponse<SchemeSelection>` |

#### `bridge_workflow_get`

| | |
|--|--|
| **参数** | `{ run_id?: string }` |
| **返回** | `BridgeResponse<WorkflowRun>` |

---

### 4.2 Custody & Binding（阶段 A）

> Bridge **不**向托管服务器上传 `CustodyOptimizerProfile`；上传并行度由客户端 Profile 约束本地 HTTPS 客户端，服务端调度读 `CustodyServerDefaults`（[接口规格 §5](../architecture/vpin-custody-server-接口规格.md#5-客户端-profile-与服务端-defaults)）。

#### `bridge_custody_get_capabilities`

| | |
|--|--|
| **参数** | 无（读 `ClientSettings.custody_host_endpoint` + JWT） |
| **返回** | `BridgeResponse<CustodyCapabilities>` |
| **上游** | `GET {custody}/api/v1/capabilities` |

#### `bridge_custody_get_defaults_view`（可选，只读）

| | |
|--|--|
| **参数** | 无 |
| **返回** | `BridgeResponse<CustodyServerDefaultsView>` |
| **说明** | 展示服务端写死配置；非客户端可调参 |

#### `bridge_custody_create_upload_session`

| | |
|--|--|
| **参数** | `{ file_id?, total_chunks, capability_mode? }` |
| **返回** | `BridgeResponse<UploadSessionCreated>` |
| **上游** | `POST {custody}/v1/files/upload-sessions` |
| **默认** | `capability_mode = "data_only"`；非 data_only 且未实现 → `CUSTODY_CAPABILITY_NOT_IMPLEMENTED` |

请求体（Bridge → 托管）：

```json
{
  "file_id": "optional-uuid",
  "total_chunks": 1024,
  "capability_mode": "data_only"
}
```

#### `bridge_custody_upload_chunk`

| | |
|--|--|
| **参数** | `{ session_id, chunk_index, file_path?: string, bytes_b64?: string }` |
| **返回** | `BridgeResponse<ChunkUploadResult>` |
| **上游** | `PUT {custody}/v1/upload-sessions/{sid}/chunks/{k}` + 客户端 VADS 签名 |
| **事件** | emit `bridge://custody-progress` |

#### `bridge_custody_commit_upload_session`

| | |
|--|--|
| **参数** | `{ session_id, idempotency_key?: string }` |
| **返回** | `BridgeResponse<CustodySession>`（`COMMITTED`，含 `file_revision`、`recomposed_hash`） |
| **上游** | `POST {custody}/v1/upload-sessions/{sid}/commit` |

#### `bridge_custody_cancel_upload_session`

| | |
|--|--|
| **参数** | `{ session_id }` |
| **返回** | `BridgeResponse<{ cancelled: boolean }>` |
| **上游** | `DELETE {custody}/v1/upload-sessions/{sid}` → 410 映射 `CUSTODY_SESSION_GONE` |

#### `bridge_custody_get_file_manifest`

| | |
|--|--|
| **参数** | `{ file_id }` |
| **返回** | `BridgeResponse<FileManifest>` |
| **上游** | `GET {custody}/v1/files/{fid}` |

#### `bridge_custody_get_session`

| | |
|--|--|
| **参数** | `{ session_id }` |
| **返回** | `BridgeResponse<CustodySession>` |

#### `bridge_custody_list_sessions`

| | |
|--|--|
| **参数** | `{ state?: CustodySessionState }` |
| **返回** | `BridgeResponse<CustodySession[]>` |

#### `bridge_binding_create`

| | |
|--|--|
| **参数** | `CreateBindingRequest` |
| **返回** | `BridgeResponse<DataBindingRecord>` |
| **上游（hosted）** | `POST {custody}/v1/bindings`（托管 `BindingService` 组装） |
| **上游（client_local）** | 纯本地组装，不调托管 |

```typescript
interface CreateBindingRequest {
  custody_mode: "hosted" | "client_local";
  capability_mode?: CustodyCapabilityMode;
  inference_peer: "client_local" | "custody_host";
  verifier_target: "client_local" | "custody_host";
  custody_session_id?: string;
  file_id?: string;
  vads_indices?: number[];
  local_data_digest?: string;
  owner_id: string;
  tenant_id?: string;
}
```

**校验规则（Bridge 侧）**：

1. `bridge_custody_get_capabilities`：`capability_mode` 须在 `implemented[]` 内，否则 fail（非 data_only 当前必失败）
2. `capability_mode` 为 `inference_peer` / `full_proxy` → `inference_peer` 应为 `custody_host`
3. `capability_mode === proof_verification` → `verifier_target` 应为 `custody_host`
4. `custody_mode === client_local` → `capability_mode` 仅 `data_only`（其余需 hosted 数据面）
5. **不向托管 POST** `SchemeSelection` / `PrivacyModePreference`

#### `bridge_binding_get`

| | |
|--|--|
| **参数** | `{ binding_id }` |
| **返回** | `BridgeResponse<DataBindingRecord>` |

#### 占位：非 DataOnly 托管代理（转发 501）

| Command | 上游 | 说明 |
|---------|------|------|
| `bridge_custody_open_inference_peer` | `POST /v1/inference-peer/sessions` | P3 WSS 代理；**当前 501** |
| `bridge_custody_open_proof_verification` | `POST /v1/proof-verification/sessions` | P6 Verify 代理；**当前 501** |
| `bridge_custody_open_full_proxy` | `POST /v1/full-proxy/sessions` | 全量托管；**当前 501** |

请求体须含 `DataBindingRecord` + `modality_family_id` + `scheme_id`（客户端已选，托管不修改，见 [接口规格 §3.1](../architecture/vpin-custody-server-接口规格.md#31-inferencepeerservice)）。

---

### 4.3 Inference（阶段 B）

#### `bridge_inference_create_run`

| | |
|--|--|
| **参数** | `{ binding_id, model_id, startup_id, scheme_selection? }` |
| **返回** | `BridgeResponse<InferenceRun>` |
| **副作用** | 创建 `workflow_phase=inference`，`workflow_node=preflight` |

#### `bridge_inference_preflight`

| | |
|--|--|
| **参数** | `{ run_id }` |
| **返回** | `BridgeResponse<InferenceRun>` |
| **失败** | 任一项 `preflight_checks.status=fail` → `ok=true` 但 `preflight_status=fail`；或 `error.code=PREFLIGHT_FAIL` |

`capability_supported` 检查：调用 `bridge_custody_get_capabilities`，确认 `binding.capability_mode ∈ implemented`；若为 `placeholder` 仅允许 warn（开发）或 fail（生产）。

#### `bridge_inference_start`

| | |
|--|--|
| **参数** | `{ run_id, session_start: SessionStartPayload }` |
| **返回** | `BridgeResponse<{ run: InferenceRun; accept: SessionAccept }>` |
| **行为** | Rust 内建立 WSS，驱动 P1–P6；UI 仅收事件 |

#### `bridge_inference_get_run`

| | |
|--|--|
| **参数** | `{ run_id }` |
| **返回** | `BridgeResponse<InferenceRun>` |

#### `bridge_inference_list_runs`

| | |
|--|--|
| **参数** | `{ limit?: number }`（默认 20） |
| **返回** | `BridgeResponse<InferenceRun[]>` |

#### `bridge_inference_get_trace`

| | |
|--|--|
| **参数** | `{ run_id }` |
| **返回** | `BridgeResponse<AheTraceEntry[]>` |

#### `bridge_inference_cancel`

| | |
|--|--|
| **参数** | `{ run_id }` |
| **返回** | `BridgeResponse<{ cancelled: boolean }>` |

---

### 4.4 Verification（阶段 C）

#### `bridge_verification_execute`

| | |
|--|--|
| **参数** | `{ run_id }` |
| **返回** | `BridgeResponse<VerificationReport>` |
| **顺序** | 先模型推理验证器，后密态流程验证器（架构 §7.1） |

#### `bridge_verification_get_report`

| | |
|--|--|
| **参数** | `{ run_id }` |
| **返回** | `BridgeResponse<VerificationReport>` |

#### `bridge_verification_reverify`

| | |
|--|--|
| **参数** | `{ run_id }` |
| **返回** | `BridgeResponse<ClientReverify>` |

---

### 4.5 Proxy（只读）

#### 推理服务（`vpin-backend`）

Rust 使用 `reqwest` 访问 `ClientSettings.backend_url`。

| Command | 代理 |
|---------|------|
| `bridge_proxy_health` | `GET /health` |
| `bridge_proxy_list_models` | `GET /models?capability=` |
| `bridge_proxy_get_model` | `GET /models/{id}` |
| `bridge_proxy_datasets_catalog` | `GET /datasets/catalog` |
| `bridge_proxy_security_transport` | `GET /security/transport` |

#### 托管服务器（`vpin-custody-server`，默认 `:8003`）

| Command | 代理 |
|---------|------|
| `bridge_proxy_custody_health` | `GET /api/v1/health` |
| `bridge_proxy_custody_capabilities` | `GET /api/v1/capabilities`（同 `bridge_custody_get_capabilities`） |

业务写操作统一走 **§4.2** `bridge_custody_*`，不重复暴露裸 REST 给 Vue。

---

### 4.6 Settings

| Command | 参数 | 返回 |
|---------|------|------|
| `bridge_settings_get` | — | `BridgeResponse<ClientSettings>` |
| `bridge_settings_update` | `Partial<ClientSettings>` | `BridgeResponse<ClientSettings>` |

---

## 5. 工作流程图 → Command 映射

| 工作流节点 | Command / 事件 |
|------------|----------------|
| StartupOptimizer | `bridge_bootstrap_detect` |
| SchemeSelection | `bridge_scheme_select` |
| custody_mode + capability_mode | `bridge_binding_create` |
| OVDS append/verify | `bridge_custody_*_upload_session` | `bridge://custody-progress` |
| P0 | `bridge_inference_start` |
| Preflight | `bridge_inference_preflight` |
| P3 环 | `bridge://inference-event` |
| 双验证器 | `bridge_verification_execute` |
| client_reverify | `bridge_verification_reverify` |

---

## 6. 实现状态（里程碑）

| Command 组 | 目标里程碑 | 托管里程碑 | 当前 |
|------------|------------|------------|------|
| `bridge_proxy_*` (backend) | P1 | — | 未实现 |
| `bridge_bootstrap_*` | P1 | — | 未实现 |
| `bridge_custody_*` (data_only) | P3 | **M1 DataOnly** | 未实现 |
| `bridge_custody_open_*` (非 data_only) | P5+ | 托管 501 占位 | 未实现 |
| `bridge_inference_*` | P2 | — | 未实现 |
| `bridge_verification_*` | P4 | ProofVerification 占位 | 未实现 |

未实现时返回：

```json
{
  "ok": false,
  "error": {
    "code": "NOT_IMPLEMENTED",
    "message": "bridge_inference_start is not available in this build"
  },
  "request_id": "..."
}
```

---

## 7. 修订记录

| 版本 | 日期 | 说明 |
|------|------|------|
| v0.2 | 2026-07-03 | 对齐 vpin-custody-server；**[TEMP-LOCAL-CUSTODY]** 实现期本地 Shim 说明 |
| v0.1 | 2026-07-03 | 初稿 |
