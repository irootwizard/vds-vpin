# cp-snark-full 架构草案（v0.2）

> **状态：** **M1 已落地**（`commit/`、`model/`、`trace/`、`statement/`、`prove/`、`verify/`、`protocol/` v2）；`circuit/mac_rlc` **桩已停用**（`mac_proof=None`），**勿接入** prover。  
> **总路线图（唯一权威）：** [`综合未来工作路线图.md`](./综合未来工作路线图.md)  
> **设计附录：** [`cp-snark-分层证明与RLC设计定稿.md`](./cp-snark-分层证明与RLC设计定稿.md)  
> **目的：** 统一承诺 / 陈述 / witness / **按层**证明 / 协议编排。  
> **关联：** [`layer_proof/README.md`](../src/cp-snark-full/src/layer_proof/README.md)、[`模型参数密码学绑定与客户端验证规范.md`](./模型参数密码学绑定与客户端验证规范.md)

---

## 1. 设计原则（摘要）

| # | 原则 |
|---|------|
| P1 | **承诺按数据、不按层**：一个 $\mathsf{cm}_W$（+ 可选 $\mathsf{cm}_x$），不为 Conv/Pool/FC 各建 cm |
| P2 | **陈述按层、证明按层**：每层独立 $\pi_{\mathrm{layer}}$（conv / pool / fc）；**禁止**合并 conv+fc 的单个 `mac_rlc` 桩 |
| P3 | **标量 check ≠ SNARK verify**：`check_scalar` 仅 prover/测试；客户端只验 π + transcript |
| P4 | **RLC 验证只保留式 (9)(10)**：客户端 γ 下**不**做逐格 eq5/eq8 作为必验步骤；式 (9) **计算**已在 `Server.py` `rLCL`/`rLCR` 实现 |
| P5 | **拆端最后做**：同 crate 内 `prover` / `verifier`；拆部署只动 IO |
| P6 | **模型绑定独立阶段**：Pedersen 打开 / L1 等不阻塞按层 π 骨架 |
| P7 | **三线勿混**：[A] Python 推理 · [B] 原 `vPIN_proof_generation` EC gadget · [C] 本 crate 协议（见设计定稿 §1） |

---

## 2. 目标目录树（`src/cp-snark-full/src/`）

```text
lib.rs
├── curve.rs                    # 已有：E₂ 嵌入、embed_u128
├── challenge.rs                # 已有：γ, γ′, transcript 片段
│
├── commit/                     # 从 commitment.rs 迁入（可选分文件）
│   mod.rs
│   model.rs                    # cm_W, verify_model, open（阶段 1）
│   input.rs                    # cm_x
│   transcript.rs               # append_commitments_to_transcript
│
├── statement/                  # 现 layer_proof 演进
│   mod.rs
│   layer_id.rs                 # LayerId, LayerKind { Conv, Pool, Fc }
│   conv.rs                     # ConvStatement, ConvWitness
│   pool.rs
│   fc.rs
│   stack.rs                    # NetworkTopology + LinearStackStatement
│   rlc.rs
│   check.rs                    # check_scalar_*（现 verify.rs）
│   gadget.rs                   # EcGadgetSchedule（MAC 侧需要的槽位草图）
│
├── trace/                      # 新建：Python JSON → Witness
│   mod.rs
│   load_ec.rs                  # pointAdd / pointMult JSON
│   build_stack.rs              # trace + ModelParams → LinearStackWitness
│
├── model/                      # 新建：明文 W 切片（非承诺）
│   mod.rs
│   params.rs                   # ModelParams { conv_f, fc1, fc2, ... }
│   network_a.rs                # 可选：仅实例化尺寸，不写死在 statement
│
├── circuit/
│   mod.rs
│   ec/                         # 现 point_addition + point_mult + circuit_prove 的 R1CS 部分
│   │   point_add.rs
│   │   point_mult.rs
│   mac_rlc/                    # 将来：式 (9)(10) R1CS（可 generic）
│       mod.rs
│       arithmetize.rs
│
├── prove/
│   mod.rs
│   mac.rs                      # prove_mac_rlc(stack, ch, transcript) -> MacProof
│   ec.rs                       # prove_ec_batch(network, ...) -> EcProofBundle
│   pipeline.rs                 # prover 总线
│
├── verify/
│   mod.rs
│   mac.rs
│   ec.rs
│   pipeline.rs                 # verifier 总线
│
└── protocol/
    mod.rs
    artifacts.rs                # ProtocolArtifacts v2
    prover.rs                   # 现 prover_run 逻辑
    verifier.rs                 # 现 verifier_run 逻辑
    coverage.rs                 # ProofCoverage（现 common.rs 部分）
```

**命名迁移对照：**

| 现状 | 草案 |
|------|------|
| `layer_proof::verify::*` | `statement::check::*` |
| `layer_proof::*ProofSpec` | `statement::*Witness` + `statement::*Statement` |
| `circuit_prove.rs` | `prove/ec.rs` + `verify/ec.rs` + `circuit/ec/` |
| `protocol.rs` | `protocol/{artifacts,prover,verifier}.rs` |
| `commitment.rs` | `commit/` |

---

## 3. 核心类型草案（Rust 草图）

### 3.1 层标识与拓扑

```rust
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum LayerKind {
    Convolution,
    AveragePooling,
    FullyConnected,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct LayerId {
    pub kind: LayerKind,
    /// 同 kind 多实例时递增，如 FC0 / FC1
    pub index: u8,
}

/// 网络实例（Network A 只是其中一个 const 构造器）
pub struct NetworkTopology {
    pub network_id: String,           // "A" | "L2" | ...
    pub layers: Vec<LayerId>,         // 有序：Conv → Pool → Fc(0) → Fc(1)
}
```

### 3.2 模型参数（调用方传入，非承诺）

```rust
/// 明文模型切片；与 .npy / 推理用 W 一致，由服务器在 prove 前持有
pub struct ModelParams {
    pub conv_filter_flat: Vec<u128>,       // F, len k²
    pub fc: Vec<FcParams>,                 // 每层 FC 一项
}

pub struct FcParams {
    /// W[k][j], rows = in_dim
    pub weights: Vec<Vec<u128>>,
    pub bias: Vec<u128>,
}

/// 公开超参（非学习参数）
pub struct LayerHyper {
    pub conv: Option<ConvHyper>,
    pub pool: Option<PoolHyper>,
}

pub struct ConvHyper { pub stride: usize, pub padding: usize }
pub struct PoolHyper {
    pub kernel: usize,
    pub stride: usize,
    pub inv_k_squared_fp: u128,
}
```

### 3.3 每层：Statement（公开） vs Witness（证明者持有）

**卷积**

```rust
pub struct ConvStatement {
    pub layer_id: LayerId,
    pub filter_len: usize,              // k²，与 ModelParams 对齐检查
    pub num_outputs: usize,
}

pub struct ConvWitness {
    pub filter_flat: Vec<u128>,         // 必须与 ModelParams.conv 一致（L3 前仅 check）
    pub windows: Vec<Vec<u128>>,
    pub output_flat: Vec<u128>,
}

impl ConvWitness {
    pub fn statement(&self, id: LayerId) -> ConvStatement { ... }
    pub fn check_scalar(&self, ch: &ClientChallenge) -> Result<(), StatementError> {
        // eq5 + eq9，现 verify_conv_*
    }
    pub fn ec_schedule(&self, ch: &ClientChallenge) -> EcGadgetSchedule { ... }
}
```

**池化**

```rust
pub struct PoolStatement {
    pub layer_id: LayerId,
    pub num_windows: usize,
    pub inv_k_squared_fp: u128,         // 公开
}

pub struct PoolWitness {
    pub windows: Vec<Vec<u128>>,
    pub output_sums: Vec<u128>,
}
```

**全连接**

```rust
pub struct FcStatement {
    pub layer_id: LayerId,
    pub in_dim: usize,
    pub out_dim: usize,
}

pub struct FcWitness {
    pub weights: Vec<Vec<u128>>,
    pub bias: Vec<u128>,
    pub inputs: Vec<u128>,
    pub outputs: Vec<u128>,
}
```

**整栈**

```rust
pub struct LinearStackWitness {
    pub topology: NetworkTopology,
    pub conv: Option<ConvWitness>,
    pub pool: Option<PoolWitness>,
    pub fc: Vec<FcWitness>,
}

impl LinearStackWitness {
    /// Prover 侧：生成 π_mac 前必跑（便宜）
    pub fn check_all_scalar(&self, ch: &ClientChallenge) -> Result<(), StatementError>;

    /// 绑定：每层输出索引与下一层输入（层间一致性，仍可用标量或将来进 R1CS）
    pub fn check_layer_wiring(&self) -> Result<(), StatementError>;
}
```

### 3.4 统一层 trait（可选，便于 stack 泛化）

```rust
pub trait LayerCheck {
    fn layer_id(&self) -> LayerId;
    fn check_scalar(&self, ch: &ClientChallenge) -> Result<(), StatementError>;
}

pub trait LayerEcSchedule {
    fn ec_gadget_schedule(&self, ch: &ClientChallenge) -> EcGadgetSchedule;
}
```

---

## 4. 证明族与 `ProtocolArtifacts` v2

### 4.1 按层 π（**定稿：每层分开，禁止合并桩**）

> **⚠️ 2026-06-10 修订：** 此前「合并 `mac_rlc`」方案 **已废弃**。见 [`cp-snark-分层证明与RLC设计定稿.md`](./cp-snark-分层证明与RLC设计定稿.md) §5。

| 层 | 陈述（公开输入含挑战） | 证明块 |
|----|------------------------|--------|
| 卷积 | 式 **(9)** + **γ** | `π_conv`（RLC in-circuit + 该层 EC gadget 子集） |
| 池化 | 式 **(7)**，**无** γ | `π_pool`（PtAdd 链） |
| FC | 式 **(10)** + **γ′** | `π_fc[k]` |

- **原 `circuit/mac_rlc`：** 电路外预计算 left/right，与标量 check 重复 → **不接入** `prover_pipeline`（`mac_proof=None`）。
- **原 Python `rLCL`/`rLCR`：** 式 (9)(10) 的**计算侧**已实现；cp-snark 负责**客户端可验**绑定，而非重写算法。

```rust
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct MacRlcProof {
    pub proof_bytes: Vec<u8>,
    pub circuit_id: String,              // "mac_rlc_v1" — 含 conv(9) + fc(10)，非仅 FC
    pub num_cons: usize,
    pub num_vars: usize,
    /// 公开输入：如 γ 绑定哈希、层数、输出维度摘要等
    pub public_inputs_hex: Vec<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct EcProofBundle {
    pub point_add: Option<SubCircuitProof>,   // 现 SubCircuitProof
    pub point_mult: Option<SubCircuitProof>,
}
```

### 4.2 协议产物（客户端一次收齐）

```rust
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ProtocolArtifacts {
    pub version: u32,                        // 2
    pub network: String,
    pub topology: NetworkTopology,

    // L0 承诺
    pub model_commitment: ModelCommitmentBundle,
    pub input_commitment: InputCommitmentBundle,

    // L1 挑战（客户端采样或确认）
    pub client_challenge: ClientChallenge,

    // L3 证明
    pub mac_proof: Option<MacRlcProof>,        // 未实现前 None
    pub ec_proof: EcProofBundle,

    // 诚实披露 + 计时
    pub proof_coverage: ProofCoverageV2,
    pub prove_time_ms: ProveTiming,

    // 可选：标量 RLC 绑定 hex（弱绑定，保留至 L2 进电路）
    #[serde(default)]
    pub rlc_binding_hex: Option<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ProveTiming {
    pub check_scalar_ms: u128,
    pub prove_mac_ms: u128,
    pub prove_ec_ms: u128,
    pub total_ms: u128,
}

#[derive(Clone, Copy, Debug, Serialize, Deserialize)]
pub enum ProofCoverageV2 {
    EcOnly,              // 现 ec_gadget_only
    EcPlusScalarCheck,   // prover 跑了 check_all_scalar，无 π_mac
    EcPlusMacRlc,        // 完整 L2 目标
}
```

**与 v1 兼容：** `version` 缺省为 1 时按现 `protocol.json` 反序列化；`version: 2` 含 `mac_proof`、`topology`。

---

## 5. Transcript 顺序（Fiat–Shamir 单一来源）

```text
label "cp_snark_vpin_v2"
  → cm_W (point + digest)
  → cm_x
  → client_gamma
  → client_gamma_add      // 仅 EC 批若需要
  → client_gamma_mult     // FC RLC / π_mac
  → topology_digest       // hash(network_id || layer_ids)
  → sub_circuit "mac_rlc"   // π_mac（将来）
  → sub_circuit "point_add"
  → sub_circuit "point_mult"
```

**规则：** $\gamma$ 必须在 **任何** `prove_mac` / `prove_ec` 之前写入；子证明共享同一 `Transcript` 克隆或连续 append。

---

## 6. 调用流草案

### 6.1 服务器（Prover）

```rust
pub fn prover_pipeline(
    network: &str,
    model: &ModelParams,
    trace: &EcTraceFromJson,
    challenge: ClientChallenge,
) -> Result<ProtocolArtifacts, ProverError> {
    let topology = NetworkTopology::for_network(network)?;
    let (cm_w, _, _) = commit::model::commit(model)?;
    let (cm_x, _) = commit::input::commit_public(network)?;

    // 1. 组装 witness（trace + model）
    let stack = trace::build_stack(&topology, model, trace)?;

    // 2. 标量预检（便宜，~毫秒）
    let t0 = now();
    stack.check_all_scalar(&challenge)?;
    stack.check_layer_wiring()?;
    let check_ms = elapsed(t0);

    // 3. π_mac（将来）
    let mac_proof = None; // prove::mac::prove(&stack, &challenge, &cm_w, &cm_x)?;

    // 4. π_ec（现最重）
    let t1 = now();
    let ec_proof = prove::ec::prove_batch(network, &cm_w, &cm_x, &challenge)?;
    let prove_ec_ms = elapsed(t1);

    Ok(ProtocolArtifacts { version: 2, mac_proof, ec_proof, ... })
}
```

### 6.2 客户端（Verifier）

```rust
pub fn verifier_pipeline(art: &ProtocolArtifacts) -> Result<(), VerifyError> {
    ensure_coverage_supported(art.proof_coverage)?;

    // 1. 承诺（本地 W* 或仅 cm）
    commit::model::verify_digest(&art.model_commitment, ...)?;
    commit::input::verify(&art.input_commitment, ...)?;

    // 2. 重放 γ（或对比本地采样）
    replay_challenge(&art.client_challenge)?;

    // 3. π_mac
    if let Some(mac) = &art.mac_proof {
        verify::mac::verify(mac, &art, ...)?;
    }

    // 4. π_ec（可并行）
    verify::ec::verify_bundle(&art.ec_proof, &art, ...)?;

    // 5. 关系钉合（L2：轨迹乘数 = MAC 输出）— 将来在 R1CS 或显式 check
    Ok(())
}
```

**注意：** 客户端 **不** 调用 `check_scalar`（除非 debug）；那是 prover 自检。

---

## 7. `trace` 模块：JSON → Witness（性能相关）

```rust
pub struct EcTraceFromJson {
    pub point_adds: Vec<(u128, u128)>,      // 与现 point_one_Add 对应
    pub point_mults: Vec<(base, weight)>,
}

pub fn load_ec_trace(network: &str) -> io::Result<EcTraceFromJson>;

/// 将 EC 轨迹 + ModelParams 填成 LinearStackWitness
/// 卷积 windows / outputs 来源：同态中间结果或从 mult 轨迹反推（实现选项）
pub fn build_stack(
    topology: &NetworkTopology,
    model: &ModelParams,
    ec: &EcTraceFromJson,
) -> Result<LinearStackWitness, TraceError>;
```

**性能建议：**

- JSON **只读一次**，构造 `LinearStackWitness` 后复用；
- `build_stack` 与 `check_all_scalar` 放 rayon 可选并行（仅层内独立时）；
- 不在 prove 路径重复 `load_weights_only` + `load_data` 若已含于 `ModelParams`。

---

## 8. 性能与证明规模（决策表）

| 方案 | 约束量级（相对） | prove 时间 | 建议 |
|------|------------------|------------|------|
| 仅 $\pi_{\mathrm{ec}}$（现状） | 1.0×（~638k） | ~201s debug | 保留为基线 |
| + 标量 `check_all_scalar` | +0 | +毫秒 | **立即做** |
| 每层独立 $\pi_{\mathrm{mac}}$ | ×层数 | 线性恶化 | **避免** |
| ~~全栈一个 `mac_rlc`~~ | — | — | **⛔ 已废止**；改 **按层** `π_conv`/`π_fc`（设计定稿 §5） |
| FC naive MAC 进 R1CS | ~7.6× | 不可接受 | **禁止** |
| 每层独立 cm | 证明规模不变 | 协议/存储变差 | **禁止** |

---

## 9. 分阶段落地（与路线图对齐）

| 阶段 | 交付 | 改动面 |
|------|------|--------|
| **M0**（当前+文档） | `layer_proof` + README + 本草案 | 无破坏性重构 |
| **M1** | ✅ `model/`、`trace/`、`prove::prover_pipeline`、`ProtocolArtifacts` v2、`convertFormatForRust_conv` | 见 [`model-trace-接口与卷积windows方案.md`](./model-trace-接口与卷积windows方案.md)；`conv_trace` 需补全 windows 数据 |
| **M2** | 目录重命名 `layer_proof` → `statement`，`check.rs` | 类型拆 Statement/Witness |
| **M3** | 按层 `π_conv`/`π_pool`/`π_fc` in-circuit（**非**合并 `mac_rlc`） | R1CS 设计评审 |
| **M4** | L1 打开 / `w_i` 绑定进 MAC 或 EC | `commit::open` |
| **M5** | `protocol/verifier` 独立 crate 或 FFI | 只迁 artifacts IO |

---

## 10. Explicit 非目标（防止 scope creep）

- 每层 `cm_conv` / `cm_pool` / `cm_fc`
- 在 `statement` 内 `prove` / `my_lib_verify`
- 客户端跑完整 `Server.py` 同态推理
- TReLU 服务器 SNARK
- 未接线前把 `proof_coverage` 标成 `EcPlusMacRlc`

---

## 11. 开放问题（实现前需拍板）

### 11.1 卷积 `windows` 与现有 JSON trace（已定案：现状无独立字段）

**当前仓库事实（Network A）：**

| 数据 | 是否在 `rust_files/A/` | 说明 |
|------|------------------------|------|
| PtMul 点坐标 `point_mult_px/py_byte.json` | ✅ | 整批 EC 标量乘 witness |
| `weight.json`（178 项） | ✅ | `weights_array`，对应每次 PtMul 的标量权重，**混合**卷积 rLCR 与 FC rLCR |
| 卷积 `window_list` / `output_flat` | ❌ | `myConv2d` 在 Python 内构造，**未** `convertFormatForRust_*` 导出 |

因此 **不能** 指望「从现有独立 trace 字段解析 windows」——除非扩展 Python 导出，例如：

```text
rust_files/{net}/conv/
  filter_flat.json      # 或继续从 ModelParams
  windows.json          # 每输出格 k² 窗口（密文标量/点编码）
  output_flat.json
```

**`build_stack` 推荐路线（按优先级）：**

1. **M1 推荐：** Server 在 `inferenceCNN` 末尾增加 `convertFormatForRust_conv()`，与 pointMult 同级导出 windows + outputs。  
2. **备选：** 另存客户端加密输入 + 明文 F，在 Rust 用 `from_plaintext_conv` 同构重算 windows（仅当 witness 为明文标量实验路径）。  
3. **不推荐：** 仅从 178 路 PtMul **反推** windows——轨迹是 rLCR 压缩后的乘加链，与「每格完整 $k^2$ 窗口」不是一一对应，易错。

**与 $\pi_{\mathrm{ec}}$ 关系：** 178 次 PtMul 证明的是 **EC gadget 代数**，不是式 (9) 的 RLC 陈述；卷积 MAC/RLC 仍需 `ConvWitness` 或等价公开输入，不能单靠 $\pi_{\mathrm{ec}}$ 替代。

### 11.2 按层 π 与 RLC（**定稿 2026-06-10**）

| 层 | 论文式 | 挑战 | 证明块 |
|----|--------|------|--------|
| 卷积 | **(9)** | 客户端 γ | **`π_conv`** |
| 平均池化 | **(7)** | — | **`π_pool`**（PtAdd；无 γ） |
| 全连接 | **(10)** | 客户端 γ′ | **`π_fc[k]`** |

**已定案：** **每层分开出证明**；禁止合并 `mac_rlc` 桩。式 (9)(10) **计算**见 [A] `Server.py` `rLCL`/`rLCR`。

### 11.3 其他

3. **层间 wiring：** 仅文档约束 vs `check_layer_wiring` 标量等式 vs 进 R1CS？  
4. **验证方权重：** 继续读 `weight.json` 还是仅 `protocol.json` 中的 cm？

---

## 12. 修订记录

| 版本 | 日期 | 说明 |
|------|------|------|
| v0.1 | 2026-06-04 | 初稿：模块树、类型、Artifacts v2、prover/verifier 管线、迁移阶段 |
| v0.1.1 | 2026-06-04 | §11.1 卷积 windows/trace 定案；§11.2 澄清 π_mac 含 Conv(9)+FC(10)，池化无 RLC |
| v0.2 | 2026-06-10 | 对齐 [`cp-snark-分层证明与RLC设计定稿.md`](./cp-snark-分层证明与RLC设计定稿.md)；废止合并 mac_rlc；P2/P4/§4.1/§11.2 修订 |
| v0.2 | 2026-06-04 | 代码 M1：`commit/model/trace/statement/prove/verify/protocol`；`Server.py` 导出 `conv_trace.json` |
