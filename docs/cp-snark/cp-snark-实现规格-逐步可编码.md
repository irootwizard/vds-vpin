# CP-SNARK 实现规格（逐步可编码）

> **总路线图（唯一权威）：** [`综合未来工作路线图.md`](./综合未来工作路线图.md) §5（M1–M5）、§7、§10。  
> **本文：** M1 函数名、冻结事实、阻塞表的**展开附录**（编码时查阅）。  
> **设计理由：** [`cp-snark-分层证明与RLC设计定稿.md`](./cp-snark-分层证明与RLC设计定稿.md)  
> **基准网络：** A  
> **更新：** 2026-06-10

---

## 0. 读本文前先接受的冻结事实（均有代码出处）

| # | 事实 | 证据 |
|---|------|------|
| F1 | 式 (9) **计算**在 Python 完成：`rLCL` 左端 + `rLCR` 右端 + `assert` | `Server.py:337-344` |
| F2 | Python 系数是 **`pf(secret_key,i)`**，不是论文 γ^i | `Server.py:181,209,454-458` |
| F3 | Rust 标量 RLC 用 **`γ^i`**（`fold_rlc`） | `layer_proof/rlc.rs:22-29` |
| F4 | `verify_conv_eq9_rlc` **先调 eq5 再 eq9**（定稿要改掉） | `layer_proof/verify.rs:53` |
| F5 | `mac_proof` 恒为 **`None`** | `prove/pipeline.rs:86-87` |
| F6 | 客户端验 EC：**整批** `prove_point_add/mult` | `prove/ec.rs`, `load_data.rs` |
| F7 | 178 次 PtMul **无层标签**，混在全网 JSON | `rust_files/A/pointMult/weight.json` |
| F8 | Network A 卷积 trace：**16** 窗 × 9 维，`output_flat` 长 16 | `model_exports/A/conv_trace.json` |
| F9 | Network A 池化 trace：4 窗，每窗 4 值；`output_flat` = 窗内**求和** | `pool_trace.json`（如 10+20+50+60=140） |
| F10 | `fc_trace.json` 的 `layers: []`；内置 `load_model_params("A")` 的 `fc: vec![]` | `fc_trace.json`, `model/load.rs:222` |
| F11 | `rlc_binding_hex` = `γ·Σw + (1-γ)·Σa`（与式 9 **无关**） | `prove/pipeline.rs:91-93`, `challenge.rs:88-92` |

---

## 1. 三层对象（写代码时禁止混名）

```text
陈述 S_layer   — 公开/witness 满足的代数关系（式 7/9/10）
witness W_layer — 从 trace JSON 或推理填写的数值/点
证明 π_layer     — Spartan SNARK 字节（当前仅有 π_ec 整批）
```

| 层 | 陈述（客户端要信什么） | witness 来源（今天） | π（今天） |
|----|------------------------|----------------------|-----------|
| Conv | 式 (9)，公开 γ | `conv_trace.json` | 无；EC 混在 178 PtMul 里 |
| Pool | 式 (7) 求和 | `pool_trace.json` | 无；PtAdd 混在 2144 批里 |
| FC | 式 (10)，公开 γ′ | `fc_trace.json`（A 为空） | 无 |

---

## 2. 式 (9)(10)(7) 的精确定义（与 `rlc.rs` 一致）

### 2.1 卷积 — 式 (9)

- 输入 witness（prover 提供，客户端可读自 trace 或承诺打开）：
  - `filter_flat: [u128; 9]`
  - `windows: Vec<[u128;9]>`，长度 `R`
  - `output_flat: [u128; R]`
- 公开输入：`γ_conv`（`ClientChallenge.gamma` → `Scalar`）
- 检查（**唯一**客户端标量检查，**不**做逐格 eq5）：

```text
fold_rlc(output_flat, γ)  ==  conv_rlc_right(filter_flat, windows, γ)
```

- 已实现函数：`conv_rlc_left` / `conv_rlc_right`（`rlc.rs:42-56`）
- **待改函数：** 新增 `verify_conv_eq9_rlc_only`（不调用 eq5）；或给 `verify_conv_eq9_rlc` 加 `skip_per_cell: bool`

### 2.2 池化 — 式 (7)

- 对每个池化窗 `w`：`sum(w) == output_sums[i]`（**缩放前**）
- 公开：`inv_k_squared_fp` **不进**此检查（乘缩放在 AHE 侧）
- 函数：`verify_pool_eq7_per_cell`（`verify.rs:66-90`）— **保留**

### 2.3 全连接 — 式 (10)

- 公开：`γ′`（`ClientChallenge.gamma_mult`）
- 检查（**不**做逐格 eq8）：

```text
fc_rlc_left(outputs, γ′) == fc_rlc_right(inputs, weights, bias, γ′)
```

- 函数：`fc_rlc_left/right`（`rlc.rs:58-83`）
- **待改：** `verify_fc_eq10_rlc` 去掉对 `verify_fc_eq8` 的强制前置

---

## 3. 协议消息序（可编码的 P0–P6）

```text
P0  Setup     — 曲线/AHE 参数（已有）
P1  cm_W      — ModelCommitmentBundle + opening（已有）
P2  cm_x      — InputCommitmentBundle + input_binding.json（已有）
P3  Infer     — [A] Server 推理 + 导出 trace + rust_files JSON（已有）
P4  Challenge — ClientChallenge { gamma, gamma_mult, ... }（已有 API）
P5  Prove     — prover_pipeline(challenge) → ProtocolArtifacts（已有）
P6  Verify    — verifier_pipeline(artifacts)（需改：加标量 eq9/7/10）
```

**Transcript 顺序（已有，勿改）：** `cp_snark_vpin` → cm_W → cm_x → γ → γ_add → γ_mult → sub_circuit 名（`circuit_prove.rs:90-93`）

**硬性规则：** P4 的 `challenge` 必须在 P5 之前生成；`prover_pipeline` 收到的 `challenge` 即 P4 消息。

---

## 4. `ProtocolArtifacts` 今天 vs 目标

### 4.1 今天（`protocol/artifacts.rs`）

```rust
// 已有且继续用
model_commitment, input_commitment, client_challenge
ec_proof: Option<EcProofBundle>  // 整批 PtAdd + PtMul
mac_proof: None                   // 保持 None 直到 in-circuit 完成

// 定稿弱化/删除
rlc_binding_hex  // 与式 (9) 无关 → 验证侧忽略或删除写入
```

### 4.2 目标（按层，**后续 milestone**）

```rust
// 建议 v3 字段（名称可在编码时定）
pub layer_scalar: Option<LayerScalarBundle>,  // 客户端验 eq9/7/10 的输入
pub layer_proofs: Option<LayerProofBundle>,   // π_conv, π_pool, π_fc[*]
```

**M1 不要求** 立刻改 schema；可先在 `verifier_pipeline` 内从 `model_exports/{net}/*.json` 读 trace（与 prover 相同路径），与 artifacts 中的 `client_challenge` 做标量验。

---

## 5. 实现里程碑（严格顺序）

### M1 — 客户端标量验证（**可立即编码，无 SNARK 新电路**）

| 步骤 | 文件 | 动作 |
|------|------|------|
| M1.1 | `layer_proof/verify.rs` | 拆出 `verify_conv_eq9_rlc_only`（无 eq5） |
| M1.2 | 同上 | `verify_fc_eq10_rlc_only`（无 eq8） |
| M1.3 | `layer_proof/stack.rs` | `verify_all_client` 只调 eq9/7/10-only |
| M1.4 | `verify/pipeline.rs` | 在 `verify_ec_bundle` **之前** 调 `build_stack` + `verify_all_client` |
| M1.5 | `verify/pipeline.rs` | **删除或 `#[cfg]` 关闭** `rlc_binding_hex` 比对 |
| M1.6 | `prove/pipeline.rs` | `run_scalar_check` 改用 `verify_all_client`（与客户端一致） |
| M1.7 | 测试 | `cargo test layer_proof` + 用 A 的 `conv_trace` 手算/已有 toy test |

**M1 完成标准：** `verifier_pipeline` 在**不读 `weight.json`**（有 opening）时，仍能用 γ 验证 conv+pool 标量式。

**M1 不做：** 新 R1CS；改 Python；拆 PtMul。

---

### M2 — 协议跨进程闭合（**大部分已有**）

| 步骤 | 文件 | 动作 |
|------|------|------|
| M2.1 | `protocol/cross_process.rs` | 确认 `sample-challenge` / `prove-with-challenge` 测试 |
| M2.2 | `vpin-backend/.../bridge.py` | 文档化 P4→P5 顺序（已有 r4） |
| M2.3 | `ProtocolArtifacts` | `proof_coverage` 仅反映 M1：`ec_plus_scalar_check` |

**M2 完成标准：** 客户端 JSON challenge → 服务端 prove → 客户端 `verify-file` 通过（含 M1 标量）。

---

### M3 — Python 推理与客户端 γ 对齐（**改 [A]，可选但推荐**）

| 步骤 | 文件 | 动作 |
|------|------|------|
| M3.1 | `Server.py` | `rLCL`/`rLCR` 增加参数 `coeff(i)` 回调；默认仍 `pf(sk,i)` |
| M3.2 | 同上 | 协议模式：`coeff(i) = γ^i mod field`（与 `fold_rlc` 同域） |
| M3.3 | 同上 | 无 `secret_key` 时由调用方传入 `gamma_bytes` |

**M3 完成标准：** 同一 trace 下，Python `assert` 与 Rust `verify_conv_eq9_rlc_only` 使用**同一 γ** 均通过。

**注意：** M1 可在 M3 之前工作（只验 trace 与 γ 的代数关系，不要求推理时用了 γ）。

---

### M4 — EC witness 按层切分（**改 [A] 导出**）

| 步骤 | 文件 | 动作 |
|------|------|------|
| M4.1 | `Server.py` | `points_mult`/`point_one_Add` 记录 `{layer, index}` |
| M4.2 | 导出 | `rust_files/A/pointMult/manifest.json` 含层区间 |
| M4.3 | `load_data.rs` | 按层切片或分文件加载 |

**阻塞：** 在 M4 之前**不能**声称 `π_conv` 只覆盖卷积 EC。

---

### M5 — 按层 SNARK（**in-circuit，长期**）

| 步骤 | 内容 |
|------|------|
| M5.1 | `π_conv`：公开输入 `[γ, digest(trace)]`；R1CS 编码式 (9) 或子关系 |
| M5.2 | `π_pool`：式 (7) + 该层 PtAdd 子集 |
| M5.3 | `π_fc[k]`：式 (10) + 该层 PtMul/PtAdd 子集 |
| M5.4 | 删除 `circuit/mac_rlc/` 桩或仅留测试 |

**依赖：** M4（层区间）+ M1（陈述清晰）。

---

## 6. 函数级调用图（M1 完成后）

```text
verifier_pipeline(artifacts)
  ├─ resolve_weight_scalars / resolve_public_scalars  (已有)
  ├─ build_stack_for_network(network)               (已有)
  ├─ stack.verify_all_client(&artifacts.client_challenge)  [M1 新增]
  ├─ verify_ec_bundle(...)                            (已有)
  └─ (移除 rlc_binding_hex 检查)                      [M1.5]
```

```text
prover_pipeline(network, challenge)
  ├─ commit cm_W, cm_x                                (已有)
  ├─ build_stack + verify_all_client(challenge)       [M1 与客户端对齐]
  ├─ mac_proof = None                                 (保持)
  └─ prove_ec_timed(...)                              (已有)
```

---

## 7. 明确阻塞 / 不可写进代码的幻觉

| 幻觉 | 真相 |
|------|------|
| 「`mac_rlc` 已实现 π_mac」 | `build.rs` 电路外算 left/right；`mac_proof=None` |
| 「eq5 必须客户端验」 | 定稿：仅 eq9 + 随机 γ |
| 「改 cp-snark 就实现了式 (9) 计算」 | 计算在 `Server.py`；cp-snark 只做**验证绑定** |
| 「178 PtMul = 卷积式 (9)」 | PtMul 证 EC gadget；式 (9) 是标量 RLC  sobre `conv_trace` |
| 「pool output_flat 一定错」 | A 上网内求和与 `output_flat` 一致（140 等）；若用缩放后值会失败 |
| 「A 上能验 FC 式 (10)」 | `fc_trace.layers` 空；需先导出 FC trace + `model_export` 中 fc 权重 |
| 「`pf(sk,i)` 与 `γ^i` 可混用」 | 自检可混；**客户端验证必须用 P4 的 γ** |

---

## 8. M1 编码清单（复制给实现 agent）

```rust
// layer_proof/verify.rs — 新增
pub fn verify_conv_eq9_rlc_only(spec: &ConvLayerProofSpec, challenge: &ClientChallenge) -> LayerProofResult<()>
pub fn verify_fc_eq10_rlc_only(spec: &FcLayerProofSpec, challenge: &ClientChallenge) -> LayerProofResult<()>

// layer_proof/stack.rs — 新增
impl ServerLinearProofStack {
    pub fn verify_all_client(&self, challenge: &ClientChallenge) -> LayerProofResult<()> { ... }
}

// verify/pipeline.rs — 修改 verifier_pipeline
// 1) after opening checks
let witness = build_stack_for_network(&artifacts.network).map_err(...)?;
witness.stack.verify_all_client(&artifacts.client_challenge)?;
// 2) remove rlc_binding_hex block
// 3) then verify_ec_bundle(...)
```

```rust
// prove/pipeline.rs — run_scalar_check 内
w.stack.verify_all_client(challenge)  // 替换 check_all_scalar
```

**测试：**

```bash
cd src/cp-snark-full && cargo test layer_proof
# 加集成：load artifacts A + verify_pipeline 仅 conv+pool
```

---

## 9. 与定稿文档的索引

| 定稿 § | 本规格 § |
|--------|----------|
| 三线 [A][B][C] | §0 F1–F7, §1 |
| γ 客户端化 | §3 P4, M2–M3 |
| 废弃 mac_rlc | §4.1, M5, §7 |
| 按层 π | §4.2, M4–M5 |
| 不重复 eq5 | §2.1, M1 |

---

## 10. 修订记录

| 日期 | 说明 |
|------|------|
| 2026-06-10 | 初版：冻结事实、M1–M5、函数名、阻塞表 |
