# vPIN 平台架构：独立客户端与服务端（协议合规定稿）

> **定稿前提（产品目标）**  
> - 最终交付 **两个独立程序**：**客户端**（用户设备）与 **服务端**（推理与证明方）。  
> - **AHE（指数 ElGamal 同态推理）** 与 **CP-SNARK（计算量/正确性证明）** 是 **平台级能力**，由共享密码学库实现，而非某次实验脚本。  
> - 交互必须 **真实符合 vPIN 协议语义**（Setup → 承诺 → 同态计算 → 客户端挑战 → 证明 → 客户端验证），**禁止**用「服务端自测随机数」「本地同进程 verify」冒充密码学验证。  
>  
> **本文性质**：架构与协议编排定稿；**实现顺序**见 §8。与 [技术选型对比](./vpin-技术选型-客户端服务器多方案对比.md) 关系：该文用于历史比选；**以本文为准**。  
> **顶层抽象**：六平面、三角色、OVDS 绑定与双验证器见 [vpin-平台顶层抽象架构.md](./vpin-平台顶层抽象架构.md)。

---

## 1. 目标架构一览

```
                    ┌─────────────────────────────────────┐
                    │     vpin-platform（Rust workspace）   │
                    │  ┌─────────────┐  ┌───────────────┐  │
                    │  │ vpin-ahe    │  │ vpin-cp-snark │  │
                    │  │ E2 ElGamal  │  │ ← cp-snark-full│  │
                    │  │ 编解码/同态  │  │ 承诺/证明/验证  │  │
                    │  └──────┬──────┘  └───────┬───────┘  │
                    │         └────────┬────────┘          │
                    │                  │ vpin-protocol      │
                    │            （消息类型、会话状态机）     │
                    └──────────┬───────────────┬───────────┘
                               │               │
              ┌────────────────┘               └────────────────┐
              ▼                                                  ▼
   ┌──────────────────────┐                        ┌──────────────────────┐
   │  vpin-client         │   TLS 1.3 + WS/REST    │  vpin-server         │
   │  （Tauri 桌面端）      │ ◄────────────────────► │  （无头服务）         │
   │  - UI（现有 vpin 页）  │                        │  - 模型注册 CLI       │
   │  - 私钥 / 解密 / 截断  │                        │  - 同态推理引擎       │
   │  - 采样 γ、Verify    │                        │  - Prover / witness   │
   │  - 仅持 pk 以上秘密    │                        │  - 永不持有客户端 sk   │
   └──────────────────────┘                        └──────────────────────┘
```

**与实验代码的关系**

| 路径 | 角色 |
|------|------|
| `src/cnn_networks/*.py` | **参考实现 / 回归对照**；协议合规后不得作为产品安全边界 |
| `src/cp-snark-full` | **证明内核**；迁入 `vpin-cp-snark`，由 task1 持续补齐语义 |
| `vpin-backend/`（Python） | **非终态**；仅可作 P0 联调，不承载「平台特性」与合规验证 |
| `vpin_frontend` | **客户端 UI 壳**；密码学逻辑进 `src-tauri` + `vpin-client` crate |

---

## 2. 平台特性定义（AHE + CP-SNARK）

### 2.1 平台特性 A：AHE 同态推理

**语义（论文 + 对照说明）**

- 曲线 **E₂**：Weierstrass，参数与仓库 `curveE2Info()` 一致。  
- 客户端 **KeyGen**：$h = xG$；**私钥 $x$ 永不离开客户端**。  
- 加密：$c_1=rG,\ c_2=mG+rh$；明文 $m$ 为定点整数（默认 $f=16$）。  
- 服务端仅在密文上做 **线性** 运算：点加（同态加）、标量乘（公开权重/池化系数）。  
- 非线性：**ReLU + shifting（截断）** 仅在客户端明文域完成，完成后重新加密上传。  

**平台 API（逻辑接口，实现于 `vpin-ahe`）**

| 侧 | 能力 |
|----|------|
| 客户端 | `keygen`, `encrypt`, `decrypt`, `relu`, `shift`, `serialize_ciphertext` |
| 服务端 | `hom_add`, `hom_scalar_mul`, `conv`, `avg_pool`, `fc`（拓扑驱动） |
| 共享 | `curve_params`, `fixed_point_codec`, `ciphertext_wire_format` |

**密码学硬性要求**

1. 服务端 **不得** 接收或持久化 $x$。  
2. 会话密钥材料：客户端仅上传 $(G, h, n)$ 或等价 `PublicKey` 包。  
3. 截断轮次由 **离线截断计划** + 运行时密文幅值监测触发（Task3），但 **解密与重加密动作只在客户端**。  
4. BSGS 预计算表 **只部署在客户端**（体积大、与离散对数求解开销绑定）。

### 2.2 平台特性 B：CP-SNARK 计算量证明

> **设计定稿：** [`cp-snark-分层证明与RLC设计定稿.md`](./cp-snark-分层证明与RLC设计定稿.md)

**语义**

证明方（服务端）向验证方（客户端）证明：在已承诺的 $\mathbf{W}$ 与输入 $x$ 上，**各线性层**满足论文式 (7)(9)(10)（客户端挑战 $\gamma,\gamma'$），且各层 **EC gadget（PtAdd/PtMul）** 正确。  
**式 (9)(10) 计算**已在 `Server.py` `rLCL`/`rLCR` 实现；平台化须改为**客户端 γ** + **按层 π**，非合并 `mac_rlc` 桩。

**协议阶段（与 `cp-snark-full/src/protocol.rs` 对齐并扩展）**

| 阶段 | 执行方 | 产物 | 客户端必须保存 |
|------|--------|------|----------------|
| P0 Setup | 双方 | $E_1/E_2$ 参数、算法版本 | 公开参数指纹 |
| P1 模型承诺 | 服务端 → 客户端 | $\mathsf{cm}_W$ | 绑定所选 `model_id` |
| P2 输入承诺 | 客户端 → 服务端（或双方各提交哈希） | $\mathsf{cm}_x$ | 与加密输入一致 |
| P3 同态计算 | 服务端（客户端多轮截断） | witness 轨迹、运算计数 | 会话日志（可选） |
| P4 挑战 | **仅客户端** | $\gamma, \gamma_{add}, \gamma_{mult}$ | 本地随机源 |
| P5 证明 | 服务端 | $\pi$（子电路证明 + 绑定字段） | — |
| P6 验证 | **仅客户端** | accept / reject | 验证报告 |

**密码学硬性要求**

1. $\gamma$ **必须由客户端 CSPRNG 生成**（`ClientChallenge::sample` 语义），经 **TLS 会话内明确消息** 发给服务端后再 `prove`；服务端 **不得** 代采 $\gamma$ 作为生产路径。  
2. 客户端 `verify` **不得** 依赖服务端回传的 witness 文件路径；仅依赖：公开参数、$\mathsf{cm}_W$、$\mathsf{cm}_x$、$\gamma$、$\pi$、以及协议规定的公开输入编码。  
3. $\mathsf{cm}_W$、$\mathsf{cm}_x$ 必须在 transcript 中 **先于** $\gamma$ 与证明（与现 `append_challenge_to_transcript` 顺序一致）。  
4. 工程自检（原 `Server.py` 的 `rLCL`/`rLCR` + `assert`）**不得**替代 P4–P6；最多作为服务端 **非安全** 调试开关。

**当前 `cp-snark-full` 与「真实协议」差距（必须在平台化前闭合）**

见 [CP-SNARK自检与计算量预估.md](./CP-SNARK自检与计算量预估.md) 摘要；**密码学绑定与客户端 Verify 规范**见 [模型参数密码学绑定与客户端验证规范.md](./模型参数密码学绑定与客户端验证规范.md)：

| 缺口 | 平台化要求 |
|------|------------|
| $\mathsf{cm}_W$ 仅覆盖 `weight.json` 标量 | 承诺 **完整模型张量** 或论文允许的 Merkle/分块承诺，并与拓扑绑定 |
| $\mathsf{cm}_x$ 仅嵌入曲线系数 $a$ | 承诺 **客户端输入**（定点明文哈希或密文承诺方案） |
| witness 与同态推理未电路绑定 | 推理引擎输出 witness 与 R1CS 输入 **同一管道** 生成 |
| 验证方重算权重 | 客户端验证时不应需要服务端磁盘上的 `weight.json`；应仅依赖 $\mathsf{cm}_W$ 与 $\pi$ 中公开部分 |

> **结论**：平台特性 B 的 **代码归宿** 是 Rust `vpin-cp-snark`；在缺口闭合前，产品可标注「证明覆盖范围」并在 UI 明示，但 **不得** 宣称完整论文命题已证。

---

## 3. 独立客户端与服务端职责

### 3.1 客户端（`vpin-client` + Tauri）

| 职责 | 说明 |
|------|------|
| 身份与密钥 | 生成并安全存储 $x$；可选 OS keychain |
| 模型选择 | 拉取服务端模型目录；**在发送输入前** 校验 $\mathsf{cm}_W$ 指纹 |
| 数据与加密 | 图像/特征定点化 → 加密 → 上传 |
| 截断交互 | 收到 `TruncateRequest(bits)` → 解密 → relu/shift → 重加密 → 回复 |
| 挑战 | 根据会话统计（#PtAdd, #PtMul）采样 `ClientChallenge` |
| 验证 | 收到 $\pi$ 后本地 `verifier_run` 等价逻辑；生成 Task3 验证报告 |
| UI | 现有 `public/vpin/pages/*`，经 Tauri `invoke` 调 Rust |

**禁止**：在客户端进程内运行完整同态推理；禁止将 $\gamma$ 生成委托给服务端。

### 3.2 服务端（`vpin-server`）

| 职责 | 说明 |
|------|------|
| 模型接入 | **CLI** 注册预训练包（Task3）；解析、存储、生成 $\mathsf{cm}_W$ |
| 推理会话 | 维护状态机；同态执行；记录运算次数供挑战计数 |
| 证明 | 收到客户端 $\gamma$ 后调用 `prover_run` |
| 存储 | 权重文件、模型索引 DB、会话元数据；**不存** 客户端私钥 |
| API | HTTPS REST（模型元数据）+ WSS（推理与证明） |

**禁止**：持有客户端私钥；在证明路径中使用「验证方未参与」的随机挑战。

---

## 4. 密码学合规的会话交互（消息级）

以下为 **生产路径** 消息编排（类型名供 `vpin-protocol` crate 实现）。

### 4.1 会话建立

```
Client ──TLS──► Server
Client ──SessionStart{ client_version, ahe_params_id }──►
Server ──SessionAccept{ session_id, server_version, model_catalog_epoch }──►
```

### 4.2 模型绑定（必须先于输入）

```
Client ──ModelSelect{ model_id }──►
Server ──ModelCommitment{ cm_W, e2_digest, topology_hash, truncation_plan }──►
Client 本地校验：catalog 中 model_id 与 cm_W 一致，否则中止
```

### 4.3 输入与 AHE 推理

```
Client ──InputCommitment{ cm_x, ciphertext_meta }──►   // cm_x 与将发送的密文绑定
Client ──PublicKey{ h, curve_meta }──►
Client ──CiphertextChunk* ──►                        // 二进制帧，非 JSON 点坐标

loop 服务端同态层:
  Server ──TruncateRequest{ phase_id, bits, shape }──►
  Client ──CiphertextChunk*（重加密后）──►

Server ──InferenceComplete{ num_pt_add, num_pt_mult, witness_root? }──►
```

**合规要点**

- `TruncateRequest` 对应论文 **客户端截断**；服务端 **不得** 在服务端进程内做 relu/shift 代替客户端。  
- 密文传输：**长度前缀 + bincode/protobuf**；禁止 pickle 跨语言。

### 4.4 证明与验证

```
Client ──ClientChallenge{ gamma, gamma_add, gamma_mult, num_pt_add, num_pt_mult }──►
Server ──ProofBundle{ pi_add?, pi_mult?, rlc_binding, prove_time_ms }──►
Client 本地 Verify →
Client ──VerificationReport{ session_id, ok, cm_W, cm_x, gamma_prefix, ... }──►  // 可选上报审计
```

**合规要点**

- `ClientChallenge` **仅由客户端生成**；服务端 `prover_run(network, challenge)` 的 `challenge` 参数必须来自该消息。  
- 验证失败：客户端 UI 必须 **拒绝** 展示「验证通过」，不得 fallback 到 Mock。

### 4.5 与实验代码的差异对照

| 实验代码行为 | 产品合规行为 |
|--------------|--------------|
| TCP + pickle | TLS + 结构化二进制 |
| 服务端 `os.urandom` RLC assert | 调试开关；安全路径用客户端 $\gamma$ + CP-SNARK |
| 同进程 `run_full_protocol` 自证 | 客户端独立 `verifier_run` |
| 无 $\mathsf{cm}_W$ 下发 | `ModelCommitment` 强制步骤 |

---

## 5. 仓库与 Crate 规划（终态）

```
vPIN-main/
├── crates/
│   ├── vpin-protocol/      # 消息、会话状态、错误码
│   ├── vpin-ahe/           # E2 AHE（从 Client/Server 语义移植到 Rust）
│   ├── vpin-cp-snark/      # 包装 cp-snark-full，闭合 §2.2 缺口
│   └── vpin-common/        # 曲线常量、哈希、版本
├── apps/
│   ├── vpin-client/        # Tauri 应用（依赖上述 crates）
│   └── vpin-server/        # axum + tokio 二进制
├── src/cp-snark-full/      # 保持 task1 开发，被 vpin-cp-snark 依赖
├── src/cnn_networks/       # 回归测试黄金对照
└── vpin_frontend/          # 逐步迁入 apps/vpin-client 或作为 UI 资源目录
```

**Python `vpin-backend`**：标记 **deprecated / 联调专用**；不实现 §4 合规证明路径。

---

## 6. 前端（Tauri）定位

Tauri **不是** 第三方浏览器方案，而是 **客户端发行形态**：

- **WebView**：展示 `vpin/pages`（模型中心、数据配置、验证报告）。  
- **`src-tauri`**：平台特性的 **唯一本地入口**（`invoke` 调 `vpin-ahe` + `vpin-cp-snark` 验证器）。  
- **网络**：WebView 内 JS **不直接** 持有私钥；敏感操作走 `invoke`（避免 XSS 泄露 $x$）。

远程服务端地址通过客户端配置（`server_url`），开发可用 mkcert 自签 TLS。

---

## 7. Task3 在合规架构下的落点

| Task3 需求 | 合规落点 |
|------------|----------|
| 服务端模型 CLI 接入 | `vpin-server` admin 子命令 → 生成 $\mathsf{cm}_W$ → 写入索引 |
| 客户端 HTTPS 上传模型 | `POST /v1/models` + 解析管道；上传后客户端也应收到 $\mathsf{cm}_W$ |
| 截断时机算法 | 离线写 `truncation_plan` 进 `ModelCommitment`；运行时触发 §4.3 `TruncateRequest` |
| 模型参数承诺 | 与 P1 合并；依赖 task1 承诺方案升级，而非仅 `weight.json` |

---

## 8. 实施路线图（协议优先）

| 顺序 | 交付物 | 合规里程碑 |
|------|--------|------------|
| **R0** | `vpin-protocol` 消息定义 + TLS 骨架 + 空会话状态机 | 双进程可握手 |
| **R1** | `vpin-ahe` 与 Python 对照测试（加解密、同态加、一轮截断） | AHE 特性可测 |
| **R2** | `vpin-server` 同态推理（可先 FFI 包装 Python，**但消息已合规**） | 截断轮次由客户端执行 |
| **R3** | P1–P2：$\mathsf{cm}_W$ / $\mathsf{cm}_x$ 闭合（task1） | 承诺可绑定模型与输入 |
| **R4** | P4–P6 跨进程：客户端发 $\gamma$，服务端回 $\pi$，客户端 verify | **计算量证明特性合规** |
| **R5** | 同态引擎 Rust 化（替换 Python FFI） | 性能达标 |
| **R6** | Task3 模型解析、索引、上传 | 产品功能完整 |

**原则**：R3/R4 **早于** R5。宁可同态暂时较慢，不可证明路径不合规。

**与 cp-snark / task3 的合并排期（阶段 0–7、P0/P1 等）：** 见 [`综合未来工作路线图.md`](./综合未来工作路线图.md)。

---

## 9. 验收标准（平台级）

1. **进程独立**：客户端与服务端可在两台机器上运行并完成一次完整会话。  
2. **密钥隔离**：服务端磁盘与日志中无 $x$；抓包可见 $\mathsf{cm}_W$、密文、$\gamma$、$\pi$，不可见 $x$。  
3. **挑战归属**：删除客户端后服务端无法完成有效 prove（$\gamma$ 缺失或重放被拒绝）。  
4. **验证独立**：客户端在无 witness 目录权限时仍可 verify（仅依赖公开材料 + $\pi$）。  
5. **降级诚实**：若 $\mathsf{cm}_W$ 仍为弱语义，UI 与 API 返回 `proof_coverage: "ec_gadget_only"`，不误导为全文定理。

---

## 10. 对既往文档与代码的裁决

| 项 | 裁决 |
|----|------|
| [技术选型对比](./vpin-技术选型-客户端服务器多方案对比.md) | 方案 **A（Rust 客户端 + Rust 服务端）** 为终态；Python 仅 R2 过渡 |
| [vpin-backend 架构设计](./vpin-backend-客户端服务器架构设计.md) | 降级为实验笔记；通信编排以本文 §4 为准 |
| `vpin-backend/` Python 代码 | 暂停扩展；待 R0 起建 `apps/vpin-server` |

---

*定稿版本：与「独立客户端/服务端 + 平台 AHE/CP-SNARK + 真实协议交互」产品陈述对齐；cp-snark 语义以 task1 与自检文档迭代为准。*
