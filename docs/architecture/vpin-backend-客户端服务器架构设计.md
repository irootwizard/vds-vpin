# vPIN 客户端–服务器架构设计（Task2）

> **文档性质**：架构与协议设计说明，**不含实现代码**。  
> **RLC / 按层 π / γ 定稿：** [`cp-snark-分层证明与RLC设计定稿.md`](./cp-snark-分层证明与RLC设计定稿.md)  
> **依据**：vPIN 论文、`vPIN论文与代码对照说明.md`、`src/cnn_networks/`、`src/cp-snark-full/`、前端。  
> **前提**：CP-SNARK 在 `cp-snark-full` 演进；P4 **仅客户端** γ；`Server.py` `pf(sk)` 自检 **不得**替代 P4–P6。

---

## 1. 目标与边界

### 1.1 Task2 要解决的问题

原论文实验代码是 **单会话 TCP + pickle 分块** 的「客户端脚本 ↔ 服务端脚本」形态，与产品化前端（Tauri/Vue + 静态页 `vpin/pages/*`）不匹配。Task2 要求：

1. 给出与论文方案一致的 **客户端–服务器职责划分** 与 **最小可行（MVP）通信框架**；
2. 在 **`vpin-backend/`** 中落地基础后端，**从现有源码抽取** AHE（指数 ElGamal）与 CP-SNARK（计算量证明）能力，供后续 Task3（模型接入/解析/截断调度）复用；
3. **不修改** `src/cnn_networks`、`src/proof_generation` 等既有实验目录，仅通过引用/子进程/包内复刻对接。

### 1.2 明确不在本阶段完成的内容

| 项 | 说明 |
|----|------|
| 通用 ONNX/TF 模型自动编译为 vPIN 电路 | Task3；MVP 先支持论文已验证的 **npy 权重包 + 固定 CNN 拓扑** |
| 自动静态位宽预算器 | 对照说明 §二已注明仓库未实现；Task3 再设计截断时机算法 |
| CP-SNARK 与 Spartan 子电路的完全合并证明 | `cp-snark-full` 开发中；后端仅 **桥接** 现有 Rust 入口 |
| 生产级 PKI / 多租户 | MVP 用自签名 HTTPS 或内网 HTTP+后续 TLS |

---

## 2. 现状对照（论文 vs 仓库 vs 前端）

### 2.1 论文端到端阶段（抽象）

```
Setup(E1,E2) → 模型承诺 cm_W → 输入承诺 cm_x → 同态推理(含客户端截断) → 挑战 γ → 证明 π → 客户端 Verify
```

### 2.2 本仓库已实现片段

| 阶段 | 论文 | 现状 |
|------|------|------|
| AHE 密钥、加解密、同态线性运算 | E2 上指数 ElGamal | `Client.py` / `Server.py` 完整 |
| 非线性（ReLU + 截断 shifting） | 客户端 TReLU 类操作 | 固定轮次 `receive_decrypt → relu/shifting → encrypt` |
| 随机线性组合 RLC | 验证方采样 γ | 服务端 `rLCL/rLCR` + HMAC，**调试级** |
| 点加/点乘 R1CS 证明 | CP-SNARK 子约束 | Rust `vPIN_proof_generation`，Python 采集 witness |
| 模型承诺 cm_W、客户端 Verify | Setup 承诺协议 | **`cp-snark-full` 增补中**；原 Python 流程缺失 |
| 网络化产品接口 | — | 前端 **Mock**；无统一 REST |

### 2.3 前端期望（从 `model-center.html` 等归纳）

- **远程模型**：列表筛选、选择、拉取元数据（当前 Mock，应对接 `GET /api/v1/models`）；
- **本地模型**：HTTPS 上传 `.onnx/.pt/.pth/.h5`（Task3 解析；MVP 可先收 **vPIN 打包格式**）；
- **隐私配置**：AHE / CP-SNARK 多选（`data-config.html`）；
- **推理任务**：需会话 ID、阶段进度、截断回传事件（WebSocket 或 SSE 更合适，见 §5）。

---

## 3. 角色与信任模型

| 角色 | 职责 | 密钥/秘密 |
|------|------|-----------|
| **客户端（用户设备）** | 持有 AHE 私钥 x；加密输入；解密中间结果；ReLU/截断；验证 CP-SNARK；可选本地模型上传 | x、BSGS 表、挑战随机数 γ（验证方） |
| **推理服务器** | 加载模型权重；同态卷积/FC/池化；生成 witness；生成证明；返回密文中间结果 | 模型明文 W（服务器可见）；证明 witness |
| **前端壳（Tauri/Vue）** | UI、文件选择、调用后端 API；**不**替代密码学核心（可嵌 WASM/本地 Python 子进程，但 MVP 由浏览器/桌面访问 `vpin-backend`） | 无长期密钥（或仅存会话 token） |

**与论文差异的刻意保留**：原代码服务端同时做 RLC 自检（非交互 γ）。产品化后应把 **验证方挑战** 迁到客户端（`cp-snark-full` 的 `challenge.rs` 已朝此方向），RLC 仅作开发开关。

---

## 4. 最小可行三层架构

```
┌─────────────────────────────────────────────────────────────┐
│  vpin_frontend (Tauri + Vue + public/vpin 静态页)              │
│  - 模型中心 / 数据配置 / 任务看板                              │
└───────────────────────────┬─────────────────────────────────┘
                            │ HTTPS (REST) + WSS/SSE (推理会话)
┌───────────────────────────▼─────────────────────────────────┐
│  vpin-backend (Python FastAPI)                               │
│  ├─ api/          REST 路由、上传、健康检查                    │
│  ├─ crypto/ahe/   指数 ElGamal（自 Client.py 抽取）            │
│  ├─ crypto/cp_snark/  子进程桥接 src/cp-snark-full           │
│  ├─ inference/    会话状态机（封装原 Server 流水线，渐进）     │
│  ├─ storage/      模型索引 SQLite + 权重文件目录（Task3）    │
│  └─ cli/          服务端命令行注册预训练 npy 包               │
└───────────────────────────┬─────────────────────────────────┘
                            │ cargo run (不改动原 crate 源码路径)
┌───────────────────────────▼─────────────────────────────────┐
│  src/cp-snark-full (Rust)  +  src/proof_generation (R1CS)    │
└─────────────────────────────────────────────────────────────┘
```

**选型理由（MVP）**：

- **FastAPI**：与前端 JSON 对接简单；`UploadFile` 支持大模型包；易挂 uvicorn + TLS。
- **保留 Python 同态层**：论文实验已在 Python；迁 Rust 成本高，MVP 复用 `Server.py` 逻辑为 **可导入服务模块**（后续逐步迁入 `vpin_backend/inference/`）。
- **CP-SNARK 走子进程**：与 `run_protocol.py` 一致，避免改 `vPIN_proof_generation` 构建图；开发中协议变更仅动 Rust 侧。

---

## 5. 通信协议设计

### 5.1 传输层

| 场景 | 协议 | 说明 |
|------|------|------|
| 模型元数据、健康检查、承诺摘要 | **HTTPS + REST/JSON** | 与前端 `fetch` 同源或 CORS 配置 |
| 大文件上传 | **HTTPS multipart/form-data** | 分块可选；上限与 nginx/uvicorn 配置一致 |
| 推理多轮交互 | **WebSocket**（首选）或 **SSE** | 每轮：服务端推送「需截断」事件 + 密文句柄；客户端 POST 重加密载荷 |
| 原论文 pickle 大块密文 | **内部仍可用分块二进制帧** | 封装在 WS 二进制消息内，保留 30KB 分块思想，避免单 JSON 膨胀 |

**不推荐 MVP 继续裸 TCP**：防火墙、浏览器安全策略、与 Tauri 混合内容限制均不利；TCP 可作为 **CLI 压测** 保留在 `src/cnn_networks` 不动。

### 5.2 REST API 轮廓（版本前缀 `/api/v1`）

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/health` | 存活、cp-snark 二进制是否可用 |
| GET | `/models` | 远程模型列表（对接前端筛选字段） |
| GET | `/models/{id}` | 元数据 + `cm_W` 摘要（承诺就绪后） |
| POST | `/models/upload` | 客户端 HTTPS 上传（Task3） |
| POST | `/models/register` | **服务端 CLI 等价 HTTP** 或仅 CLI |
| POST | `/sessions` | 创建推理会话（model_id、privacy_flags） |
| POST | `/sessions/{id}/input` | 客户端提交加密输入或明文由服务端代加密（仅开发模式） |
| GET | `/sessions/{id}/events` | SSE：阶段/截断/证明状态 |
| WS | `/ws/sessions/{id}` | 双向：密文轮次、客户端截断响应 |
| POST | `/proof/{session_id}/challenge` | 客户端提交 γ（CP-SNARK 就绪后） |
| GET | `/proof/{session_id}/artifact` | 下载 `protocol.json` 或证明包 |

### 5.3 消息载荷（逻辑字段，非代码）

**模型注册（服务端）**：`model_id`, `name`, `topology`（如 `cnn_mnist_v1`）, `weight_manifest[]`, `uploaded_at`, `commitment_digest`, `truncation_plan`（Task3 离线生成）。

**推理会话事件**：

- `phase`: `encrypt_input | conv1 | pool | fc1 | client_truncate | fc2 | prove | verify`
- `truncate_request`: `{ "bits": 26, "tensor_shape": ... }` — 通知客户端执行 `shifting(bits)`
- `ciphertext_chunk`: 引用 ID 或 base64（开发）

**CP-SNARK 桥接**：`network_id`（A–E 对应原 `VERSION_TO_FOLDER`）、`artifact_path`、`verify_ok`。

---

## 6. 密码学子系统职责划分

### 6.1 AHE（`vpin_backend/crypto/ahe/`）

从 `src/cnn_networks/Client.py` **语义等价抽取**（曲线参数与 `curveE2Info()` 一致）：

| 模块 | 函数族 | 来源 |
|------|--------|------|
| `curve.py` | `curve_e2_info`, `key_gen` | Client L154–175 |
| `codec.py` | 定点编解码、`encrypt`/`decrypt`、BSGS | Client + `Pre_computed_table/table.pickle` |
| `homomorphic.py` | 密文点加、标量乘 | Server 同态路径 |
| `activation.py` | `relu`, `shifting` | Client L268–278 |

**BSGS 表路径**：默认指向仓库 `src/Pre_computed_table/table.pickle`（可通过环境变量覆盖）。

### 6.2 CP-SNARK（`vpin_backend/crypto/cp_snark/`）

| 能力 | 实现方式 |
|------|----------|
| Setup + 模型/输入承诺 | `cargo run -- setup {network}` → `artifacts/{network}/protocol.json` |
| 完整协议 | `full` 子命令 |
| 验证 | `verify` 子命令 |
| Python 驱动 | 对齐 `src/cp-snark-full/python/run_protocol.py` |

**状态**：开发中接口以 **`CpSnarkBridge` 状态机** 暴露：`idle → setup_done → proved → verified`；失败时 API 返回 `503` 与明确错误，不假装验证通过。

**与 AHE 的曲线关系**：论文曲线嵌入 **$n_2 = q_1$**（$n_2$ 为 E₂ **基域**，非 `curveOrder`）已在 `curveE2Info()` 与 `point_mult.rs` / `point_addition.rs` 中实现；`cp-snark-full/curve.rs` 的 `CurveE2Params::vpin_default()` 与 Python 常数一致。集成测试可再自动化断言，但**非**「尚未实现嵌入」。

---

## 7. 推理会话状态机（对齐原 `inferenceCNN`）

原 `cnn_networks/Server.py` 在固定阶段调用 `interactionClient`（无阈值分支）。MVP 状态机：

```
CREATED → KEY_EXCHANGED → INPUT_ENCRYPTED
  → CONV1_DONE → [CLIENT_TRUNCATE_26] → POOL_FLATTEN_DONE
  → FC1_DONE → [CLIENT_RELU_TRUNCATE_32]
  → FC2_DONE → WITNESS_EXPORTED
  → CP_SNARK_SETUP → CP_SNARK_PROVE → CLIENT_VERIFY → CLOSED
```

带 `[]` 的节点为 **必须回传客户端** 的截断点（与对照说明一致）。Task3 将把固定 `bits` 换成 **离线预算算法** 输出。

---

## 8. 存储与部署（MVP）

| 数据 | 建议 |
|------|------|
| 模型权重 `.npy` | 文件系统 `vpin-backend/data/models/{id}/` |
| 索引元数据 | SQLite `vpin-backend/data/vpin.db` |
| witness / rust_files | `data/witness/{network}/` 或由 Server 推理后生成 |
| CP-SNARK artifacts | 复用 `src/cp-snark-full/artifacts/` |

**进程模型**：单 uvicorn worker 即可做 MVP；CPU 密集同态可后续用 `ProcessPoolExecutor`。Rust 证明单独子进程，避免 GIL。

**配置**：`.env` — `VPIN_REPO_ROOT`, `VPIN_BSGS_TABLE`, `VPIN_TLS_CERT`, `CP_SNARK_MANIFEST`。

---

## 9. 与 Task3 的衔接点

Task2 框架为 Task3 预留：

1. `storage.models` 表结构：`id, name, framework, task, params_count, input_shape, commitment_json, truncation_plan_json`；
2. `POST /models/upload` 解析管道入口；
3. `truncation_plan` 由离线分析器写入（对照说明 §二静态预算公式）；
4. 前端 Mock 列表改为读 `/api/v1/models`。

---

## 10. 风险与决策记录

| 风险 | 缓解 |
|------|------|
| CP-SNARK API 变动 | 仅通过 `CpSnarkBridge` 适配；版本钉死在 `protocol.json` schema |
| 密文过大 | WS 二进制分块 + 服务端流式存储 |
| 前端与后端分离部署 CORS | FastAPI `CORSMiddleware` 允许 Tauri `localhost` 源 |
| 原 TCP 与 REST 双轨 | 实验脚本不动；产品走 REST/WS |

---

## 11. 实施顺序建议

1. **本文档评审**（Task2 交付物 ①）  
2. **`vpin-backend` 骨架**：FastAPI + health + AHE 自检端点  
3. **AHE 模块单元对齐**：与 `Client.py` 加解密往返测试（同一曲线、同一明文）  
4. **CpSnarkBridge**：能跑通 `network=A` 的 setup/verify（与 `run_protocol.py` 一致）  
5. **CLI `vpin-admin register-model`**：注册 `Pre_trained_model` 对应包  
6. **前端改 Mock → 真实 API**（可与 Task3 并行）  
7. **WS 推理会话**（替换 TCP 交互）

---

*文档版本：Task2 初稿；CP-SNARK 以 `src/cp-snark-full` 当前 `protocol.json` 结构为准，随开发更新 §6.2 字段说明。*
