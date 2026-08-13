# vPIN Console — 前端 UI Mock 方案

> **版本**：v0.2  
> **配套接口**：[vpin-client-bridge.md](./vpin-client-bridge.md)  
> **托管对齐**：[vpin-custody-server-软件架构.md](../architecture/vpin-custody-server-软件架构.md)、[vpin-custody-server-接口规格.md](../architecture/vpin-custody-server-接口规格.md)  
> **范围**：**仅**新 UI 工程 [`vpin-console/`](../../vpin-console/)（方案 A 四层控制面板 · 绿场 Vue + Tauri 2）  
> **明确排除**：**不**在 legacy [`vpin_frontend`](../../vpin_frontend/vpin-frontend) 内实现 Mock / 计时 / DeepSeek；legacy 代码保留、默认不打包  
> **运行时目标**：Rust Tauri 2（`vpin-console`）；Mock 阶段可在浏览器独立运行

---

## ⚠️ [TEMP-LOCAL-CUSTODY] 托管不启服 · 选 hosted 仍走本地（临时）

> **检索标记**：`TEMP-LOCAL-CUSTODY` — 托管服务上线后删除本节及所有引用。

| 用户可见 | 实际行为（临时） |
|----------|------------------|
| 选择「托管数据 / hosted」 | **不连接** `vpin-custody-server`；MockBridge / LocalCustodyShim 本地跑 upload → commit → binding |
| `/data/custody` 页面 | 数据来自 **fixture + 内存状态**，非 `:8003` |
| 顶栏 / 设置 | 显示 **`[本地托管模拟]`** Tag（琥珀色），提醒非生产路径 |
| `custody_host_endpoint` | 设置项**禁用**或显示「临时未使用」 |
| 非 `data_only` 能力档 | 仍灰显 / 501（与正式架构一致，**不**在本地假实现 P3/P6 代理） |

**MockBridge 实现要点**：

```typescript
// [TEMP-LOCAL-CUSTODY] — 删除时改回 HTTP 客户端
const CUSTODY_BACKEND = "local-shim"; // 非 "http://127.0.0.1:8003"
```

**Rust 侧（Tauri 实现期）**：`bridge/custody.rs` 内 `if cfg!(feature = "local_custody_shim")` 或环境变量 `VPIN_LOCAL_CUSTODY=1`（默认 **开**），不发起对 8003 的 TCP。

**不要伪造**：假装 custody-server 进程已启动；EventLog 应写 `local-shim: upload session created`，便于与真服区分。

> 计时 / LLM / TLS 临时演示见 **[vpin-console-temp-demo-spec.md](./vpin-console-temp-demo-spec.md)**（`TEMP-DEMO-*`）。

---

## 1. 目标

在 Rust Bridge **未实现**或 **部分实现**时，新 UI 仍可：

1. 跑通工作流程图 **阶段 0 → A → B → C** 全链路演示  
2. 验证四层信息架构与 `WorkflowNavigator` 交互  
3. 用固定 JSON fixture 对齐 [Client Bridge](./vpin-client-bridge.md) 字段，后续无缝切换真实 `invoke`  
4. **托管能力**与 `vpin-custody-server` 里程碑一致：仅 `data_only` 可点通；其余三档灰显 + 501 说明

---

## 1.1 与托管服务器里程碑对齐

> **⚠️ [TEMP-LOCAL-CUSTODY]**：下表「M1 实现中」在**前端实现阶段不启动 custody-server**；`data_only` 流程由 **LocalCustodyShim** 本地替代。取消临时方案后，改回对接真服。

| 托管能力 | 服务器状态（正式） | **当前 Mock / 前端实现** |
|----------|-------------------|-------------------------|
| `data_only` | M1 实现中 | **本地 Shim** 模拟 upload-session → commit → binding（**不启 :8003**） |
| `inference_peer` | 501 占位 | 卡片灰显；不本地假实现 |
| `proof_verification` | 501 占位 | 同上 |
| `full_proxy` | 501 占位 | 同上 |

**能力发现**：`bridge_custody_get_capabilities` 返回**本地固定** fixture（不请求网络）：

```json
{
  "implemented": ["data_only"],
  "placeholder": ["inference_peer", "proof_verification", "full_proxy"],
  "runtime": "local-shim",
  "_temp_note": "TEMP-LOCAL-CUSTODY — 替换为 vpin-custody-server 后 runtime 改回"
}
```

**优化器分离**：UI **不**提供「向托管上传 CustodyOptimizerProfile」表单；`/data/custody` 可选只读展示 `CustodyServerDefaultsView`（**本地 fixture 模拟**，非真服 Defaults）。

**端点（临时）**：

- `backend_url` = `http://127.0.0.1:8000/api/v1`（推理 backend，仍可用）
- ~~`custody_host_endpoint` = `:8003`~~ → **实现期不使用**；设置页标注 `[TEMP-LOCAL-CUSTODY]`

---

## 2. 工程与运行模式

### 2.1 目录（计划，实施下一阶段）

```
vpin-console/
├── src/
│   ├── bridge/
│   │   ├── types.ts              # 与 API 文档 §3 同步
│   │   ├── client.ts             # 统一入口：自动选择 mock | tauri
│   │   ├── tauri-invoke.ts       # 真实 invoke
│   │   └── mock/
│   │       ├── MockBridge.ts     # 实现全部 command 接口
│   │       ├── fixtures/         # JSON 静态数据
│   │       ├── scenarios/        # 场景脚本（事件时序）
│   │       └── event-simulator.ts
│   ├── workflow/
│   ├── views/
│   └── mocks/                    # 仅 UI 展示用（图表趋势等）
└── src-tauri/                    # 后续：stub 返回 fixture 或 NOT_IMPLEMENTED
```

### 2.2 三种运行模式

| 模式 | 条件 | Bridge 实现 |
|------|------|-------------|
| **MOCK** | `import.meta.env.VITE_BRIDGE_MODE=mock` 或浏览器无 Tauri | `MockBridge.ts` |
| **TAURI_STUB** | Tauri 存在，Rust 返回 fixture | Rust 读 `fixtures/` 或硬编码 |
| **TAURI_LIVE** | Rust 真实实现 | `tauri-invoke.ts` |

```typescript
// src/bridge/client.ts（设计）
export function getBridge(): BridgeClient {
  if (import.meta.env.VITE_BRIDGE_MODE === "mock") return mockBridge;
  if (isTauri()) return tauriBridge;
  return mockBridge;
}
```

**开发默认**：`VITE_BRIDGE_MODE=mock`，`npm run dev` 在浏览器打开即可审阅 UI。

---

## 3. 视觉与布局（独立于工作流 HTML）

| 维度 | 规范 |
|------|------|
| 风格 | 运维控制面板（Temporal / Grafana 类），**非**工作流 SVG 泳道色 |
| 壳色 | `#111827` 顶栏/侧栏；内容 `#f9fafb` |
| 强调 | 琥珀 `#f59e0b` 操作；青 `#06b6d4` 数据流 |
| 字体 | UI：IBM Plex Sans SC；字段：`IBM Plex Mono` 12–13px |
| 布局 | 左四层导航 + 中 `WorkflowNavigator` + 右 `StagePanel` + 底 `EventLog` |

### 3.1 全局布局线框

```
┌─ Header: vPIN Console │ run_id │ execution_trust │ [MOCK] tag ─────────┐
├─ Nav ──┬─ WorkflowNavigator ──┬─ StagePanel ─────────────────────────┤
│ 总览   │ ▼ 0 Bootstrap    ✓   │  （当前步骤 UI）                      │
│ L1数据 │ ▼ A Custody      ●   │                                      │
│ L2计算 │ ▼ B Inference    ○   │                                      │
│ L3调度 │ ▼ C Verification ○   │                                      │
│ L4结果 │                      │                                      │
│ 设置   │                      │                                      │
├────────┴──────────────────────┴──────────────────────────────────────┤
│ EventLog ▼  [10:26:01] bridge://inference-event phase_changed P3      │
└──────────────────────────────────────────────────────────────────────┘
```

### 3.2 响应式

| 断点 | 布局 |
|------|------|
| ≥1200px | 三栏：Nav 200px + Navigator 240px + StagePanel flex |
| 768–1199px | Navigator 收成顶栏阶段条；Nav 抽屉 |
| <768px | 底栏四图标（0/A/B/C）；EventLog 上滑抽屉 |

---

## 4. 页面清单与 Mock 数据绑定

### 4.1 路由

| 路由 | 页面 | 工作流阶段 |
|------|------|------------|
| `/` | 系统态势 | 全局 |
| `/data/custody` | 数据托管 | A |
| `/data/catalog` | 数据集目录 | A |
| `/models` | 模型与密态方案 | 0 + B 输入 |
| `/runs` | 推理运行列表 | B |
| `/runs/new` | 新建运行向导 | 0+A 配置 |
| `/runs/:id` | 运行现场（驾驶舱） | B |
| `/verification/:runId` | 验证报告 | C |
| `/privacy` | 隐私与策略 | 0 + L4 |
| `/link-monitor` | 链路监视 | 横切 |
| `/settings` | 环境与连接 | 0 |

**设置页 Mock 字段**：`backend_url`、`custody_host_endpoint`（`:8003`）、`custody_jwt`（dev token 占位）、`inference_ws_url`。

### 4.2 各页 Mock 要点

#### `/` 系统态势

| 区块 | 数据来源 | Mock fixture |
|------|----------|--------------|
| 活跃 run 摘要 | `bridge_inference_list_runs` | `fixtures/runs/active.json` |
| 启动配置折叠 | `bridge_bootstrap_get` | `fixtures/bootstrap/result-edge.json` |
| 部署推荐条 | `StartupOptimizerResult.deployment_recommendation` | 同上 |
| 指标四格 | 聚合 runs | 静态数字 |

#### `/runs/new` 五步向导

| 步 | UI 组件 | Mock command |
|----|---------|----------------|
| 1 数据与托管 | `CustodyModeCards` + `CapabilityModeCards` | 先 `bridge_custody_get_capabilities`；`bridge_custody_create_upload_session` |
| 2 模型与方案 | 模型表 + `PrivacyModeRadar` | `bridge_proxy_list_models` + `bridge_scheme_select`（**不经托管**） |
| 3 角色拓扑 | `PeerVerifierMatrix` | 本地状态 → `bridge_binding_create` |
| 4 Preflight | `PreflightChecklist` | `bridge_inference_preflight` |
| 5 启动 | 摘要 + 按钮 | `bridge_inference_create_run` + `bridge_inference_start` |

**CapabilityMode 四档卡片**（[托管软件架构 §3](../architecture/vpin-custody-server-软件架构.md#3-四档托管能力模式)）：

| 值 | 卡片标题 | Mock 行为 |
|----|----------|-----------|
| `data_only` | 仅数据托管 | `implemented` → 可走 upload-session |
| `inference_peer` | P3 代行 | `placeholder` → 灰显 + 501 |
| `proof_verification` | P6 验证代行 | 灰显 |
| `full_proxy` | 全量托管 | 灰显 +「薄客户端占位」 |

#### `/data/custody`

| 区块 | 数据来源 |
|------|----------|
| 能力条 | `bridge_custody_get_capabilities` |
| Defaults 只读 | `bridge_custody_get_defaults_view` |
| 会话队列 | `bridge_custody_list_sessions` |
| 详情 | `session_id`、`index_base`、每 chunk `vads_index` |
| 进度 | `bridge://custody-progress` |

#### `/runs/:id` 运行现场

| 区块 | 数据来源 |
|------|----------|
| P0–P6 协议轨 | `InferenceRun.protocol_phase` + 事件 |
| 主监视器 Tab「相位」 | `bridge_inference_get_trace` + 实时 `inference-event` |
| 主监视器 Tab「指标」 | `InferenceComplete` mock |
| 检查器 | `bridge_binding_get` + `bridge_proxy_security_transport` |

Mock 时由 `scenarios/cnn-mnist-happy-path.ts` **定时 emit** 事件模拟 P3 三轮截断。

#### `/verification/:runId`

| 区块 | 数据来源 |
|------|----------|
| 双验证器时间线 | `bridge_verification_execute` |
| 工件折叠 | `VerificationReport.artifacts` |
| 本地复核按钮 | `bridge_verification_reverify` |

---

## 5. Mock Bridge 实现规范

### 5.1 接口抽象

```typescript
interface BridgeClient {
  bootstrapDetect(consent: boolean): Promise<StartupOptimizerResult>;
  bootstrapGet(): Promise<StartupOptimizerResult | null>;
  schemeSelect(req: SchemeSelectionRequest): Promise<SchemeSelection>;
  bindingCreate(req: CreateBindingRequest): Promise<DataBindingRecord>;
  inferenceCreateRun(params: CreateRunParams): Promise<InferenceRun>;
  inferencePreflight(runId: string): Promise<InferenceRun>;
  inferenceStart(runId: string, start: SessionStartPayload): Promise<StartResult>;
  inferenceGetRun(runId: string): Promise<InferenceRun>;
  inferenceGetTrace(runId: string): Promise<AheTraceEntry[]>;
  verificationExecute(runId: string): Promise<VerificationReport>;
  verificationReverify(runId: string): Promise<ClientReverify>;
  proxyListModels(capability?: string): Promise<ModelSummary[]>;
  custodyGetCapabilities(): Promise<CustodyCapabilities>;
  custodyCreateUploadSession(params: CreateUploadSessionParams): Promise<UploadSessionCreated>;
  custodyUploadChunk(params: UploadChunkParams): Promise<ChunkUploadResult>;
  custodyCommitUploadSession(sessionId: string): Promise<CustodySession>;
  // ... 其余 command 同 API 文档 v0.2
  subscribe(event: BridgeEventName, handler: (payload: unknown) => void): () => void;
}
```

### 5.2 Fixture 文件约定

```
src/bridge/mock/fixtures/
├── bootstrap/
│   ├── result-edge-skipped.json      # detect_mode=skipped_user_refused
│   └── result-compute-full.json      # detect_mode=full, compute
├── scheme/
│   └── cnn-mnist-e2.json
├── bindings/
│   ├── hosted-data-only.json
│   └── client-local.json
├── custody/
│   ├── capabilities.json
│   ├── server-defaults-view.json
│   ├── upload-session-created.json
│   └── session-committed.json
├── runs/
│   ├── run-preflight-fail.json
│   └── run-p3-active.json
├── verification/
│   ├── report-pass.json
│   └── report-reverify-mismatch.json
└── proxy/
    ├── custody-capabilities.json
    ├── custody-health.json
    ├── models-ahe.json
    └── datasets-catalog.json
```

每个 fixture **必须符合** [API 文档 §3](./vpin-client-bridge.md) 类型；字段名 camelCase（TS 侧）。

### 5.3 场景脚本（Happy Path）

**`scenarios/cnn-mnist-happy-path.ts`** 在用户点击「启动推理」后：

1. emit `workflow-updated` → `workflow_node=p0_session_start`  
2. 500ms 后 `phase_changed` P1 → P2  
3. 循环 3 次：`truncate_request` → `ciphertext_payload`（间隔 800ms）  
4. `inference_complete` + `phase_changed` P4 → P5 → P6  
5. 自动导航可选：提示进入 `/verification/:runId`

**`scenarios/custody-upload.ts`**：`bridge_custody_create_upload_session` 后，每 200ms `upload_chunk`，`ChunkUploadResult.vads_index = index_base + k`；最后 `commit` → `COMMITTED`。

**`scenarios/custody-501.ts`**：用户强选 `inference_peer` 时，`bridge_custody_open_inference_peer` 返回 `CUSTODY_CAPABILITY_NOT_IMPLEMENTED`，`details.mode = inference_peer`。

### 5.4 错误场景（可切换）

环境变量或设置页开关：

| 场景 ID | 触发 | 行为 |
|---------|------|------|
| `mock-preflight-fail` | Preflight | 返回 `preflight_checks` 含 fail |
| `mock-blocked-trust` | bootstrap detect | `status=blocked` |
| `mock-not-implemented` | 任意非 mock 命令 | 抛 `NOT_IMPLEMENTED` |
| `mock-verify-mismatch` | reverify | `client_reverify.status=mismatch` |

---

## 6. UI 组件与 Mock 状态对照

| 组件 | 文件（计划） | Mock 输入 |
|------|--------------|-----------|
| `WorkflowNavigator` | `workflow/WorkflowNavigator.vue` | `WorkflowRun` + 节点枚举表 |
| `StagePanel` | `workflow/StagePanel.vue` | 当前 `workflow_node` → 动态组件 |
| `BootstrapDetectModal` | `workflow/stages/BootstrapDetect.vue` | `bridge_bootstrap_detect` |
| `CapabilityModeCards` | `components/CapabilityModeCards.vue` | `CustodyCapabilities.implemented` / `placeholder` |
| `CustodyDefaultsPanel` | `components/CustodyDefaultsPanel.vue` | 只读 `CustodyServerDefaultsView` |
| `PeerVerifierMatrix` | `components/PeerVerifierMatrix.vue` | 与 `capability_mode` 联动校验 |
| `PreflightChecklist` | `components/PreflightChecklist.vue` | `PreflightCheck[]` |
| `PhaseTraceTimeline` | `components/PhaseTraceTimeline.vue` | `AheTraceEntry[]` + events |
| `VerifierPipeline` | `components/VerifierPipeline.vue` | `VerificationReport` |
| `EventLog` | `components/EventLog.vue` | 所有 `bridge://*` 事件 |
| `MockBadge` | `components/MockBadge.vue` | `VITE_BRIDGE_MODE===mock` 时顶栏显示 |

---

## 7. Mock 与 Rust Stub 对齐

实施 Tauri 时，Rust stub 应：

1. 读取与 `fixtures/` **同结构** JSON（可放 `src-tauri/resources/fixtures/`）  
2. Command 名与文档 **完全一致**  
3. 未覆盖 command 返回 `NOT_IMPLEMENTED`（与 Mock 的 `mock-not-implemented` 场景一致）

这样 UI 层 `getBridge()` 在 MOCK / Tauri stub 下行为一致，仅 EventLog 来源不同（本地 timer vs Rust emit）。

---

## 8. 演示剧本（评审用）

### 剧本 A：边缘设备 + 托管数据（默认）

1. 打开 Console → Mock 弹窗「跳过检测」  
2. 新建运行 → `hosted` + `data_only` → 选 `cnn-mnist` → `balanced`  
3. Preflight 全绿 → 启动 → 观看 P3 时间线  
4. 验证报告 `pass` → 点击本地复核 `pass`

### 剧本 B：Preflight 失败

1. 设置开启 `mock-preflight-fail`  
2. 新建运行 → 第 4 步清单红项 → 禁止启动

### 剧本 C：capability 501

1. Mock 强制 `capabilities.placeholder` 含 `inference_peer`
2. 用户仍选 `inference_peer`（需开启「演示非 M1」开关）
3. Preflight `capability_supported` = fail；EventLog 显示 501 错误体

### 剧本 E：[TEMP-DEMO-TIMING] lenet-mnist 批量

1. 新建运行 → `lenet-mnist` → 批量 N=20  
2. 启动后时间线按 ~1 img/s（jitter）推进，约 20s 完成  
3. 结束显示准确度 ≈ `train_acc×0.95`，错误张数 = `round(20×(1-acc))`  
4. 单图模式不显示准确度，总时长 ~5s

### 剧本 F：[TEMP-DEMO-LLM] DeepSeek 演示

1. 打开 `/demo/llm`（顶栏 `[TEMP-DEMO-LLM]`）  
2. 配置 `.env.local` 中 `VITE_DEEPSEEK_API_KEY`（勿提交 git）  
3. 发送消息 → 侧栏展示 TLS 状态 + 演示密文 hex → 流式回复  
4. 问「你是什么模型」→ 应答密视小团队自行训练话术

---

## 9. 与 legacy 关系

| 项 | 说明 |
|----|------|
| legacy UI | 不加载、不引用；代码冻结 |
| 复用 | 可参考 [`AheDemoView`](../../vpin_frontend/vpin-frontend/src/views/demo/AheDemoView.vue) **交互**（时间线），不复制样式 |
| 后端 | Mock 的 `proxy_*` 形状对齐现有 `/api/v1/models`、`/datasets/catalog` |

---

## 10. 实施顺序（Mock 阶段）

1. `types.ts` 从 API 文档 §3 抄写  
2. `fixtures/` JSON + `MockBridge.ts`  
3. `client.ts` 模式切换 + `EventLog`  
4. 全局布局 + `WorkflowNavigator`  
5. `/runs/new` + `/runs/:id` + `/verification/:id` 三页优先  
6. 场景脚本 `cnn-mnist-happy-path`  
7. 其余列表页用静态 fixture 填充  

**本阶段不做**：`src-tauri` 真实 Rust、`vpin-frontend` 任何修改。

---

## 11. 修订记录

| 版本 | 日期 | 说明 |
|------|------|------|
| v0.2 | 2026-07-03 | 对齐 custody 架构；**[TEMP-LOCAL-CUSTODY]** 不启服、hosted 本地 Shim |
| v0.1 | 2026-07-03 | 初稿 |
