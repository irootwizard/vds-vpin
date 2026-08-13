---
name: vPIN Console Tauri
overview: 停用 legacy vpin-frontend 作为默认入口；新建 vpin-console（Vue UI + src-tauri Rust 壳）为唯一桌面客户端。Client Bridge 以 Tauri Command + Event 为唯一契约（非 HTTP Agent）。首交付物为完整接口文档 docs/api/vpin-client-bridge.md。
todos:
  - id: api-doc
    content: 落盘 docs/api/vpin-client-bridge.md（Tauri IPC 命令/事件/类型全集 + 错误码）
    status: completed
  - id: ui-mock-doc
    content: 落盘 docs/api/vpin-console-ui-mock.md（Mock 三层模式、fixture、页面绑定、演示剧本）
    status: completed
  - id: api-doc-v02-custody
    content: v0.2 同步 vpin-custody-server 架构（8003、upload-sessions、capabilities、Defaults 分离）
    status: completed
  - id: api-types-rust
    content: vpin-console/src-tauri/src/bridge/types.rs 与文档同步的 serde 类型
    status: pending
  - id: api-types-ts
    content: vpin-console/src/bridge/types.ts + invoke 封装与文档同步
    status: pending
  - id: scaffold-console-tauri
    content: 新建 vpin-console/（Vue + src-tauri），devUrl :1420，productName vpin-console
    status: pending
  - id: disable-legacy
    content: 停用 legacy：vpin-frontend 保留代码但不作为 Tauri 入口；README 标注 deprecated
    status: pending
  - id: bridge-stub-rust
    content: Rust bridge 模块 stub 命令（返回 mock 或 NOT_IMPLEMENTED）供 UI 联调
    status: pending
  - id: ui-shell
    content: WorkflowNavigator + 四层空壳页 + EventLog 监听 bridge 事件
    status: pending
  - id: bridge-impl-phases
    content: 分阶段实现 Rust bridge：bootstrap → binding → inference → verification
    status: pending
  - id: temp-local-custody-shim
    content: "[TEMP-LOCAL-CUSTODY] 托管走 LocalCustodyShim，不启 vpin-custody-server；M1 就绪后删除"
    status: pending
  - id: temp-demo-timing
    content: "[TEMP-DEMO-TIMING] 计时模拟：lenet-mnist 5s/1img/s、jitter 95-105%、批量准确度 train×0.95"
    status: pending
  - id: temp-demo-llm
    content: "[TEMP-DEMO-LLM] DeepSeek 独立页+TLS密文预览；密钥仅 env；禁止入库 sk"
    status: pending
---

# vPIN Console — Tauri 客户端与 Client Bridge 接口规范

> **状态**：接口定稿（v0.2）· 实现待开发  
> **交付文件**：[`docs/api/vpin-client-bridge.md`](../../docs/api/vpin-client-bridge.md)、[`docs/api/vpin-console-ui-mock.md`](../../docs/api/vpin-console-ui-mock.md)  
> **运行时**：Rust Tauri 2 为唯一桌面壳；legacy [`vpin-frontend`](vpin_frontend/vpin-frontend) **暂时停用**（代码保留，不打包）

## 适用范围（用户已确认）

| 项 | 决策 |
|----|------|
| **目标 UI** | **新工程 `vpin-console/`** — 此前选定的 **方案 A（四层控制面板）** 绿场实现 |
| **信息架构** | L1 数据 / L2 计算 / L3 调度 / L4 结果 + `WorkflowNavigator`（阶段 0/A/B/C） |
| **交互参考** | [`vpin-平台工作流程图.html`](docs/architecture/vpin-平台工作流程图.html) 逻辑；**非** legacy 静态页视觉 |
| **Network A 时间线参考** | legacy `AheFlowTimeline` 等 **只读借鉴**，在 vpin-console **新建** `InferenceTimeline` 等组件 |
| **TEMP-DEMO-*** | 计时 / 准确度 / DeepSeek / TLS 密文预览 **全部落在 vpin-console**，见 [temp-demo-spec](../../docs/api/vpin-console-temp-demo-spec.md) |
| **不做** | 不改 `vpin_frontend` 路由、不往 `security-center.html` / `AheDemoView` 塞演示逻辑 |

---

## ⚠️ [TEMP-LOCAL-CUSTODY] 临时决策（前端实现期 · 后续必取消）

> **显著标注**：全文检索 **`TEMP-LOCAL-CUSTODY`** 定位所有临时逻辑。

| 项 | 正式架构 | **当前前端实现** |
|----|----------|------------------|
| `vpin-custody-server` | `:8003` 独立进程 | **不启动、不连接** |
| 用户选 `hosted` / 阶段 A | HTTPS upload-sessions | **LocalCustodyShim**（Tauri 内存 + fixture） |
| `bridge_custody_*` | reqwest → 托管 API | 默认 `VPIN_LOCAL_CUSTODY=1` 走本地 |
| 设置 `custody_host_endpoint` | 必填 | **禁用**，顶栏 Tag `[本地托管模拟]` |
| `custody_jwt` | 生产必填 | 实现期跳过 |

**取消条件**：`vpin-custody-server` M1 `data_only` 稳定可用。  
**取消动作**：删 `local_custody_shim` 模块；`bridge_custody_*` 改 HTTP；恢复设置页与 JWT。

---

## ⚠️ [TEMP-DEMO-*] 临时演示层（计时 / LLM / TLS · 后续必删）

> 全文规格：[docs/api/vpin-console-temp-demo-spec.md](../../docs/api/vpin-console-temp-demo-spec.md)  
> 检索：`TEMP-DEMO-TIMING` | `TEMP-DEMO-LLM` | `TEMP-DEMO-TLS`

| 标记 | 内容 | 要点 |
|------|------|------|
| **TIMING** | CNN Mock 推理按**真实秒数**推进 UI | lenet-mnist 单图 **5s**、批量 **1 img/s**；lenet 扩展 **8s / 0.6 img/s**；resnet18-cifar **占位** |
| **TIMING** | 正态 jitter | 基准 × **N(1,σ)** 裁剪到 **95%–105%** |
| **TIMING** | 批量准确度 | 仅批量；`display_acc = train_acc × 0.95`；`wrong = round(n×(1-acc))` |
| **TLS** | LLM 演示 | 标准 HTTPS；UI 展示**演示用**密文 hex（非真 record） |
| **LLM** | DeepSeek | 独立路由 `/demo/llm`；模型默认 `deepseek-v4-pro`；**密钥仅 `VITE_DEEPSEEK_API_KEY`**，**禁止写入仓库** |
| **LLM** | 系统提示词 | 问模型信息 →「密视小团队自行训练」话术（见 spec） |

参考 UI：`AheFlowTimeline` / `AheBatchProgressHeader`（legacy 只读参考，在 vpin-console 新实现）。

---

## 0. 架构变更摘要

| 项 | 旧方案 | 新方案（当前） |
|----|--------|----------------|
| 默认 UI | vpin-frontend + 旧 Tauri | **vpin-console** |
| Bridge 传输 | localhost HTTP `:9210` | **Tauri `invoke` + `emit` 事件** |
| 客户端实现 | Python vpin-client 子进程为主 | **Rust `src-tauri/bridge/`** 编排；必要时 spawn `ahe-cli` / Python |
| legacy UI | 并行 / 开关 | **停用**；`VPIN_UI=legacy` 仅开发回溯 |

```mermaid
flowchart TB
  subgraph tauri [vpin-console Tauri Rust]
    Bridge[bridge 模块]
    Cmd[#[tauri::command]]
    Ev[AppHandle.emit]
  end
  subgraph ui [vpin-console Vue]
    Views[四层页面]
    SDK[bridge/invoke.ts]
  end
  subgraph external [外部]
    Backend[vpin-backend :8000]
    Custody[OVDS HTTPS]
    AheCli[ahe-cli / 子进程]
  end
  Views --> SDK
  SDK -->|invoke| Cmd
  Cmd --> Bridge
  Bridge --> Backend
  Bridge --> Custody
  Bridge --> AheCli
  Bridge --> Ev
  Ev -->|listen| SDK
```

---

## 1. 工程结构

```
vpin-console/                      # 唯一 Tauri 应用根
├── package.json                   # Vue 3 + Vite
├── vite.config.ts                 # port 1420（与现 tauri.conf 一致）
├── src/                           # 新 UI（方案 A 四层）
│   ├── bridge/
│   │   ├── types.ts               # 与 Rust / 文档 同源生成或手同步
│   │   ├── invoke.ts              # 统一 invoke + 错误映射
│   │   └── events.ts              # listen bridge 事件
│   ├── workflow/
│   ├── views/
│   └── design/
├── src-tauri/
│   ├── Cargo.toml
│   ├── tauri.conf.json            # productName: vpin-console
│   └── src/
│       ├── lib.rs                 # register bridge commands
│       └── bridge/
│           ├── mod.rs
│           ├── types.rs           # 全部 serde 类型
│           ├── bootstrap.rs
│           ├── custody.rs
│           ├── inference.rs
│           ├── verification.rs
│           └── proxy.rs           # 转发 backend REST
└── README.md

vpin_frontend/vpin-frontend/       # LEGACY — 暂不打包、不 dev 默认启动
docs/api/
└── vpin-client-bridge.md          # 本文人类可读版
```

**停用 legacy 操作**（实施时）：
- 新 Tauri 在 `vpin-console/src-tauri/`，不修改 legacy 的 `beforeDevCommand` 除非 monorepo 根脚本统一
- 根目录 `start-ahe.ps1` 等脚本改为 `cd vpin-console && npm run tauri dev`
- legacy 目录加 `README` 标注 `DEPRECATED — use vpin-console`

---

## 2. 调用约定

### 2.1 Command 命名

- Rust：`snake_case`，注册名为 `bridge_<domain>_<action>`
- 前端：`invoke('bridge_bootstrap_detect', { consent: true })`

### 2.2 统一响应信封

所有 command 返回 `BridgeResponse<T>`：

```rust
#[derive(Serialize, Deserialize)]
pub struct BridgeError {
    pub code: String,       // NOT_IMPLEMENTED | PREFLIGHT_FAIL | NETWORK | ...
    pub message: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub details: Option<serde_json::Value>,
}

#[derive(Serialize, Deserialize)]
pub struct BridgeResponse<T> {
    pub ok: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub data: Option<T>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<BridgeError>,
    pub request_id: String,   // UUID v4
}
```

前端 TypeScript 镜像同名类型。

### 2.3 事件（Tauri Event）

| 事件名 | payload | 说明 |
|--------|---------|------|
| `bridge://workflow-updated` | `WorkflowRun` | 阶段/节点变化 |
| `bridge://inference-event` | `InferenceEvent` | P3 环实时消息 |
| `bridge://custody-progress` | `{ session_id, chunks_done, chunks_total, state }` | OVDS 上传 |
| `bridge://log` | `{ level, message, ts }` | 底部 EventLog |

订阅：`import { listen } from '@tauri-apps/api/event'`

### 2.4 错误码

| code | HTTP 类比 | 说明 |
|------|-----------|------|
| `OK` | 200 | 成功 |
| `NOT_FOUND` | 404 | run/binding 不存在 |
| `NOT_IMPLEMENTED` | 501 | Rust 未实现，UI 显示「待升级」 |
| `BLOCKED` | 403 | `execution_trust=untrusted` |
| `PREFLIGHT_FAIL` | 422 | Preflight 门禁未过 |
| `CUSTODY_ERROR` | 502 | OVDS/托管方错误 |
| `INFERENCE_ERROR` | 502 | WS/推理中断 |
| `VERIFY_FAIL` | 422 | 验证未通过（业务 fail，非异常） |
| `INTERNAL` | 500 | 未预期错误 |

---

## 3. 共享类型（完整字段）

> 来源：[`vpin-平台顶层抽象架构.md`](docs/architecture/vpin-平台顶层抽象架构.md) 附录 C + [`messages.py`](vpin-backend/vpin_backend/protocol/messages.py)

### 3.1 WorkflowRun

```typescript
interface WorkflowRun {
  run_id: string;
  workflow_phase: "bootstrap" | "custody" | "inference" | "verification" | "done";
  workflow_node: string;
  lane?: "client" | "custody" | "gov" | "vads" | "infer" | "verify";
  status: "idle" | "running" | "pass" | "fail" | "blocked";
  updated_at: string; // ISO8601
}
```

### 3.2 DeviceProfile

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
  device_class: "edge_cpu" | "edge_gpu" | "compute_cpu" | "compute_gpu" | "cloud_vm" | "cloud_gpu";
  cpu_cores: number;
  memory_available_mb: number;
  accelerator: "none" | "integrated_gpu" | "discrete_gpu" | "cloud_gpu";
  network_rtt_ms: number;
  execution_trust: "trusted" | "constrained" | "untrusted";
  secure_execution: SecureExecutionSignals;
  detect_mode: "full" | "skipped_user_refused";
  detect_timestamp: string;
}
```

### 3.3 InferenceOptimizerProfile

```typescript
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
```

### 3.4 CustodyOptimizerProfile

```typescript
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
```

### 3.5 DeploymentRecommendation

```typescript
interface DeploymentRecommendation {
  custody_mode: "hosted" | "client_local";
  inference_peer: "client_local" | "custody_host";
  verifier_target: "client_local" | "custody_host";
  offload_policy: InferenceOptimizerProfile["offload_policy"];
  rationale: "edge_low_compute" | "detection_skipped" | "network_degraded" | "user_override";
  user_confirm_required: boolean;
}
```

### 3.6 StartupOptimizerResult

```typescript
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

### 3.7 PrivacyModePreference

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
```

### 3.8 ComputeParityGate

```typescript
interface ComputeParityGate {
  eligible: boolean;
  parity_mode?: "client_vs_inference" | "custody_vs_inference";
  custody_non_collusion?: boolean;
  peer_compute_delta_ratio?: number;
}
```

### 3.9 SchemeSelection

```typescript
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

### 3.10 DataBindingRecord

```typescript
interface DataBindingRecord {
  binding_id: string;
  owner_id: string;
  tenant_id?: string;
  custody_mode: "hosted" | "client_local";
  auth_target: "custody_host" | "inference_server";
  inference_peer: "client_local" | "custody_host";
  verifier_target: "client_local" | "custody_host";
  ovds_file_id?: string;
  vads_indices?: number[];
  data_digest: string;
  ovds_verify_ref?: string;
  binding_timestamp: string;
}
```

### 3.11 CustodySession

```typescript
type CustodySessionState =
  | "CREATED" | "UPLOADING" | "READY" | "COMMITTING"
  | "COMMITTED" | "CANCELLED" | "FAILED";

interface CustodySession {
  session_id: string;
  state: CustodySessionState;
  tenant_id: string;
  file_id: string;
  file_revision?: string;
  custody_host_endpoint: string;
  chunks_total?: number;
  chunks_done?: number;
  ovds_verify_ref?: string;
  recomposed_hash?: string;
}
```

### 3.12 InferenceRun & Preflight

```typescript
type ProtocolPhase = "P0" | "P1" | "P2" | "P3" | "P4" | "P5" | "P6";

interface PreflightCheck {
  id: "binding_valid" | "device_trust" | "parity_gate" | "model_deployable" | "scheme_compatible";
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
```

### 3.13 SessionStart（P0 扩展）

```typescript
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

### 3.14 P3 协议消息（UI 元数据视图）

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

### 3.15 VerificationReport

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

---

## 4. Tauri Command 清单（v0.1）

### 4.1 Bootstrap（阶段 0）

| Command | 参数 | 返回 `BridgeResponse<>` |
|---------|------|-------------------------|
| `bridge_bootstrap_detect` | `{ consent: boolean }` | `StartupOptimizerResult` |
| `bridge_bootstrap_get` | — | `StartupOptimizerResult \| null` |
| `bridge_bootstrap_redetect` | — | `StartupOptimizerResult` |
| `bridge_scheme_select` | `SchemeSelectionRequest` | `SchemeSelection` |
| `bridge_workflow_get` | `{ run_id?: string }` | `WorkflowRun` |

### 4.2 Custody & Binding（阶段 A）

| Command | 参数 | 返回 |
|---------|------|------|
| `bridge_custody_create_session` | `{ tenant_id, file_id, custody_host_endpoint, chunk_size_mb? }` | `CustodySession` |
| `bridge_custody_upload_chunk` | `{ session_id, chunk_index, path_or_bytes }` | `{ accepted: boolean }` |
| `bridge_custody_commit` | `{ session_id }` | `CustodySession` |
| `bridge_custody_get_session` | `{ session_id }` | `CustodySession` |
| `bridge_custody_list_sessions` | `{ state?: CustodySessionState }` | `CustodySession[]` |
| `bridge_binding_create` | 见下表 | `DataBindingRecord` |
| `bridge_binding_get` | `{ binding_id }` | `DataBindingRecord` |

**`bridge_binding_create` 参数**：

```typescript
interface CreateBindingRequest {
  custody_mode: "hosted" | "client_local";
  inference_peer: "client_local" | "custody_host";
  verifier_target: "client_local" | "custody_host";
  custody_session_id?: string;   // hosted
  local_data_digest?: string;    // client_local
  owner_id: string;
  tenant_id?: string;
}
```

### 4.3 Inference（阶段 B）

| Command | 参数 | 返回 |
|---------|------|------|
| `bridge_inference_create_run` | `{ binding_id, model_id, startup_id, scheme_selection? }` | `InferenceRun` |
| `bridge_inference_preflight` | `{ run_id }` | `InferenceRun` |
| `bridge_inference_start` | `{ run_id, session_start: SessionStartPayload }` | `{ run: InferenceRun, accept: SessionAccept }` |
| `bridge_inference_get_run` | `{ run_id }` | `InferenceRun` |
| `bridge_inference_list_runs` | `{ limit?: number }` | `InferenceRun[]` |
| `bridge_inference_get_trace` | `{ run_id }` | `AheTraceEntry[]` |
| `bridge_inference_cancel` | `{ run_id }` | `{ cancelled: boolean }` |

**说明**：P1–P6 消息交换在 Rust 内驱动；UI 仅 invoke 启停 + listen 事件，不直连 WebSocket。

### 4.4 Verification（阶段 C）

| Command | 参数 | 返回 |
|---------|------|------|
| `bridge_verification_execute` | `{ run_id }` | `VerificationReport` |
| `bridge_verification_get_report` | `{ run_id }` | `VerificationReport` |
| `bridge_verification_reverify` | `{ run_id }` | `ClientReverify` |

### 4.5 Proxy（只读转发 backend）

| Command | 参数 | 返回 |
|---------|------|------|
| `bridge_proxy_health` | — | backend health JSON |
| `bridge_proxy_list_models` | `{ capability?: string }` | models 列表 |
| `bridge_proxy_get_model` | `{ model_id }` | model 详情 |
| `bridge_proxy_datasets_catalog` | — | catalog |
| `bridge_proxy_security_transport` | — | transport 状态 |

Rust 内使用 `reqwest` 调 `VPIN_BACKEND_URL`（默认 `http://127.0.0.1:8000/api/v1`）。

### 4.6 Settings

| Command | 参数 | 返回 |
|---------|------|------|
| `bridge_settings_get` | — | `ClientSettings` |
| `bridge_settings_update` | `Partial<ClientSettings>` | `ClientSettings` |

```typescript
interface ClientSettings {
  backend_url: string;
  custody_host_endpoint?: string;
  inference_ws_url?: string;
  repo_root?: string;
}
```

---

## 5. 工作流程图节点 → Command 映射

| 工作流节点 | workflow_node | 触发 Command |
|------------|---------------|--------------|
| StartupOptimizer | `bootstrap_detect` | `bridge_bootstrap_detect` |
| 同意检测? | `detect_consent` | （同上 consent 参数） |
| SchemeSelection | `scheme_select` | `bridge_scheme_select` |
| custody_mode? | `custody_mode_decision` | `bridge_binding_create` 参数 |
| append/verify | `ovds_upload` | `bridge_custody_*` |
| DataBindingRecord | `binding_ready` | `bridge_binding_create` |
| P0 SessionStart | `p0_session_start` | `bridge_inference_start` |
| Preflight | `preflight` | `bridge_inference_preflight` |
| P3 环 | `p3_truncate_loop` | 事件 `bridge://inference-event` |
| InferenceComplete | `inference_complete` | 事件 |
| 双验证器 | `verify_dual` | `bridge_verification_execute` |
| client_reverify | `client_reverify` | `bridge_verification_reverify` |

---

## 6. Rust 实现分期

| 期 | Bridge 模块 | 依赖 |
|----|-------------|------|
| **P0 文档** | 类型 + stub 返回 mock | 无 |
| **P1** | `proxy.*` + `bootstrap_detect`（基线 Fallback） | reqwest |
| **P2** | `inference_*` 复用现有 lib.rs AHE 子进程逻辑 | ahe-cli |
| **P3** | `custody_*` OVDS HTTP | reqwest + JWT 配置 |
| **P4** | `verification_*` CP-SNARK 路径 | backend crypto 路由 |

现有 [`lib.rs`](vpin_frontend/vpin-frontend/src-tauri/src/lib.rs) 中 AHE 命令**迁移**至 `vpin-console/src-tauri`，legacy 不删除。

---

## 7. 前端 SDK 示例

```typescript
// src/bridge/invoke.ts
import { invoke } from "@tauri-apps/api/core";

export async function bridgeBootstrapDetect(consent: boolean) {
  const res = await invoke<BridgeResponse<StartupOptimizerResult>>(
    "bridge_bootstrap_detect",
    { consent },
  );
  if (!res.ok) throw new BridgeError(res.error!);
  return res.data!;
}
```

```typescript
// src/bridge/events.ts
import { listen } from "@tauri-apps/api/event";

export function onInferenceEvent(cb: (ev: InferenceEvent) => void) {
  return listen<InferenceEvent>("bridge://inference-event", (e) => cb(e.payload));
}
```

---

## 8. 实施顺序（用户确认后执行）

1. **写** `docs/api/vpin-client-bridge.md`（本文 §3–§5 导出）
2. **脚手架** `vpin-console/` + `src-tauri` + stub commands
3. **Vue 壳** + WorkflowNavigator + mock 数据
4. **迁移** legacy Tauri AHE 命令到 bridge
5. **脚本** 根目录启动指向 vpin-console；legacy 标记 DEPRECATED

**明确不做**：修改 legacy Vue 页面逻辑（仅停用作入口）。
