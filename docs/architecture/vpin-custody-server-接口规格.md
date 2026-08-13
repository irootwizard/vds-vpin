# vPIN 信任数据托管服务器 · 接口规格

> **文档性质**：托管服务器 trait 与 HTTP API 的字段级契约；与 [软件架构](./vpin-custody-server-软件架构.md)、[平台顶层抽象架构](./vpin-平台顶层抽象架构.md) 附录 C 一致。  
> **状态**：随 `vpin-custody-server` Rust 代码增量落地；未标注「实现」的条目均为占位。

---

## 1. 领域类型

### 1.1 `CustodyCapabilityMode`

| 值 | 说明 | 实现 |
|----|------|------|
| `data_only` | 仅 OVDS/VADS | 里程碑 1 |
| `inference_peer` | 仅 P3 代理 | 占位 |
| `proof_verification` | 仅 P6 Verify | 占位 |
| `full_proxy` | 全量代理 | 占位 |

### 1.2 `DataBindingRecord` 扩展

在顶层附录 C.1 基础上，托管侧建议携带：

| 字段 | 类型 | 说明 |
|------|------|------|
| `capability_mode` | `CustodyCapabilityMode` | 可选；缺省 `data_only` |

### 1.3 `AuthContext`

| 字段 | 类型 | 说明 |
|------|------|------|
| `subject_id` | string | JWT `sub` |
| `tenant_id` | string | 租户 |
| `roles` | string[] | RBAC 角色 |
| `session_id` | string? | 上传/代理会话 |
| `client_ip` | string? | 审计 |

### 1.4 `CustodyServerDefaults`

见 [软件架构 §5.2](./vpin-custody-server-软件架构.md#52-custodyserverdefaults服务端写死最优配置)。

---

## 2. 密码引擎 trait（`custody-vads`）

```rust
pub trait VadsEngine: Send + Sync {
    fn setup(&self, params: SetupParams) -> Result<SetupOutput, VadsError>;
    fn sign_block(&self, index: u64, data: &[u8]) -> Result<SignedBlock, VadsError>;
    fn append(&self, item: AppendItem) -> Result<(), VadsError>;
    fn query(&self, index: u64) -> Result<QueryResult, VadsError>;
    fn verify(&self, index: u64, data: &[u8], proof: &QueryProof) -> Result<bool, VadsError>;
    // batch_*, update, audit, judge — 见 OVDS 托管文档 §10.1
}

pub trait IndexAllocator: Send + Sync {
    fn reserve(&self, count: u64) -> Result<u64, VadsError>;
    fn current(&self) -> Result<u64, VadsError>;
}
```

**Stub**：`UnimplementedVadsEngine` 统一返回 `VadsError::NotImplemented`。

---

## 3. 占位 trait（非 DataOnly）

### 3.1 `InferencePeerService`

```rust
pub trait InferencePeerService: Send + Sync {
    fn open_session(&self, req: InferencePeerOpenRequest) -> Result<InferencePeerSessionHandle, CustodyError>;
    // WSS 数据面：TruncateRequest / CiphertextPayload — 未实现
}

pub struct InferencePeerOpenRequest {
    pub binding: DataBindingRecord,
    pub modality_family_id: String,  // cnn | llm | ...
    pub scheme_id: String,           // 客户端 P0 已选，托管不修改
}
```

### 3.2 `ProofVerificationService`

```rust
pub trait ProofVerificationService: Send + Sync {
    fn verify_inference(&self, req: ProofVerificationRequest) -> Result<ProofVerificationResult, CustodyError>;
}
```

### 3.3 `FullProxyOrchestrator`

```rust
pub trait FullProxyOrchestrator: Send + Sync {
    fn start_session(&self, req: FullProxyStartRequest) -> Result<FullProxySessionHandle, CustodyError>;
}
```

---

## 4. HTTP API

### 4.1 通用

- 前缀：DataOnly 业务 `/v1/`；运维 `/api/v1/`
- 认证：`Authorization: Bearer <JWT>`
- 错误体：`{ "error": string, "message"?: string, "mode"?: CustodyCapabilityMode }`

| HTTP | 含义 |
|------|------|
| 401 | 未认证 |
| 403 | ACL 拒绝 |
| 409 | revision / 并发冲突 |
| 410 | 会话已取消 |
| 422 | 分片校验失败 |
| 501 | 能力模式未实现 |

### 4.2 DataOnly（里程碑 1）

| 方法 | 路径 | 请求要点 | 响应要点 |
|------|------|----------|----------|
| GET | `/api/v1/health` | — | `{ "status": "ok", "runtime": "vpin-custody-server" }` |
| GET | `/api/v1/capabilities` | — | `{ "implemented": ["data_only"], "placeholder": [...] }` |
| POST | `/v1/files/upload-sessions` | `file_id?`, `total_chunks`, `capability_mode?` | `session_id`, `index_base`, chunk URLs |
| PUT | `/v1/upload-sessions/{sid}/chunks/{k}` | 分片体 + 客户端签名 | `chunk_index`, `vads_index` |
| POST | `/v1/upload-sessions/{sid}/commit` | `idempotency_key?` | `file_revision`, manifest 摘要 |
| DELETE | `/v1/upload-sessions/{sid}` | — | 204 |
| GET | `/v1/files/{fid}` | — | FileManifest |
| GET | `/v1/files/{fid}/download` | `batch` 查询参数 | 分批下载计划 + verify_mode |
| POST | `/v1/bindings` | `file_id`, `vads_indices`, … | `DataBindingRecord` |

### 4.3 占位路由（501）

| 方法 | 路径 | `capability_mode` |
|------|------|-------------------|
| POST | `/v1/inference-peer/sessions` | `inference_peer` |
| POST | `/v1/proof-verification/sessions` | `proof_verification` |
| POST | `/v1/full-proxy/sessions` | `full_proxy` |

---

## 5. 客户端 Profile 与服务端 Defaults

| 类型 | 产生方 | 消费方（当前） |
|------|--------|----------------|
| `CustodyOptimizerProfile` | 客户端 `CustodyOptimizer` | **仅客户端**上传/拉取并行度 |
| `InferenceOptimizerProfile` | 客户端 `InferenceOptimizer` | **仅客户端** P0/P3 |
| `CustodyServerDefaults` | 托管服务器常量 | UploadCoordinator、VerifyOrchestrator |

**不向托管服务器 POST Profile**（当前里程碑）；未来若启用 `CustodyRuntimePlanner`，再扩展可选头 `X-Custody-Profile` 或会话字段。

---

## 6. 交叉引用

| 顶层附录 | 本服务器 |
|----------|----------|
| C.1 `DataBindingRecord` | BindingService、`POST /v1/bindings` |
| C.6 `CustodyOptimizerProfile` | 客户端专用；Defaults 与之数值对齐但独立 |
| §5.3.0 TLS | 生产 HTTPS 必须 |
| §10.2 upload-coordinator / verify-orchestrator | custody-services |
