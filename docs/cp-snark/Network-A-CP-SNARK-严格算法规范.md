# Network A CP-SNARK — 严格算法规范（论文对齐 · 唯一实施依据）

> **状态：** 2026-07-03 · **范围：** Network A（$N_W=1219$，paper_proof：178 PtMul / 2144 PtAdd）  
> **论文：** arXiv:2411.07468v2 §IV-B.4、§V Table I、Fig.7  
> **配套推导：** [`模型参数绑定计算轨迹-数学推导.md`](模型参数绑定计算轨迹-数学推导.md)  
> **计数公式：** [`论文EC-Witness计数规范-NetworkA.md`](论文EC-Witness计数规范-NetworkA.md)  
> **RLC/分层原则：** [`cp-snark-分层证明与RLC设计定稿.md`](cp-snark-分层证明与RLC设计定稿.md)

本文是 **Network A 计算量证明的唯一算法正文**：承诺用什么、证什么、按什么顺序、如何绑定 $\mathbf W^*$ 与 EC 轨迹。实现须与此一致；禁止 silent fallback、禁止把 AHE 朴素 ~18.5k 计数当作 SNARK witness。

---

## 1. 密码学前提

| 符号 | 含义 | 本仓库 |
|------|------|--------|
| $q_1$ | Spartan / Ristretto 标量域 | `libspartan::Scalar` |
| $n_2$ | $E_2$ 基域 | `curve.rs` `CurveE2Params`；**须 $n_2=q_1$** |
| $q_2$ | ElGamal 标量阶 | AHE 加密随机数；≠ $q_1$ |
| $\iota$ | 定点整数 → $\mathbb F_{q_1}$ | `embed_u128_to_scalar`（two's-complement mod $2^{32}$ 再嵌入） |

---

## 2. 承诺（Commitments）

论文 Fig.7：**一个**模型承诺 $\widehat{\mathsf{cm}} \leftarrow \mathsf{CPS.Comm}(\mathbf W^*)$，各层 aux 另承诺；**不为每层单独建 cm_W**。

### 2.1 主承诺 — Spartan PC over $\mathbf W^*$（B′ · 生产路径）

| 项 | 规范 |
|----|------|
| **对象** | 扁平 $\mathbf W^*$，1219 维 u128，顺序见 §3 |
| **算法** | `DensePolynomial::commit(gens_pc, tape)`（Spartan 多项式承诺） |
| **代码** | `commit::cps::cps_comm_w_star` → `ProtocolArtifacts.cps_commitment` |
| **验证** | `cps_ver_w_star(w_star, cm)` — 重建 PC 与 `cm_hex` 一致 |
| **Transcript** | EC-SNARK 的 Merlin **必须先** `append_message(b"cm_W", &cm.poly_comm_hex[0])`（Z.8） |

Pedersen `commit_model` 仅作 **诊断/过渡**（`model_commitment` 字段）；**防替换以 Spartan PC 为准**。

### 2.2 输入承诺 — $\mathsf{cm}_x$

| 项 | 规范 |
|----|------|
| **公开输入** | $E_2$ 曲线系数 $a$ + 可选 `input_binding.json` 的 SHA256 digest |
| **代码** | `commit_public_inputs` → `input_commitment` |
| **Opening** | `input_opening`（Pedersen）；verify 优先 opening |

### 2.3 Aux 承诺（Fig.7）

| 项 | 规范 |
|----|------|
| **对象** | 模型 opening / aux witness（Pedersen 明文 opening 包） |
| **代码** | `cps_comm_aux_witness(model_opening)` → `cps_aux_commitment` |

### 2.4 Trace digest（M1 绑定）

| 项 | 规范 |
|----|------|
| **对象** | `conv_trace.json` ∥ `pool_trace.json` ∥ `fc_trace.json` 原始字节 |
| **算法** | SHA-256 → hex |
| **代码** | `trace::digest::scalar_trace_digest_hex` → `ProtocolArtifacts.scalar_trace_digest_hex` |
| **验证** | verify 时按 `VPIN_TRACE_ROOT` 重算并比对 |

### 2.5 训练 run 为唯一数据源

| 数据 | 路径（标准 run `20260622_184254`） |
|------|-----------------------------------|
| $\mathbf W^*$ | `{run_dir}/proof_artifacts/full_weights.json` + `weight_fc*.npy` |
| MAC trace | `{run_dir}/proof_artifacts/*_trace.json`（`export_proof_artifacts.py` 定点前向） |
| EC px/py + PtMul 槽 | `{run_dir}/proof_artifacts/ec_witness/`（`paper_proof_witness_exporter` 对齐 W*；px/py 来自既有 bundle，**非** AHE rLCR 导出） |

**禁止**默认读 `rust_files/A` 或 `model_exports/A/toy` 作为生产 witness。

---

## 3. $\mathbf W^*$ 布局（Network A）

```text
conv(9) | fc1_weights(64×16) | fc1_bias(16) | fc2_weights(16×10) | fc2_bias(10)
```

下标：$O_{\mathrm{conv}}=0$，$O_{\mathrm{fc1}}=9$，$O_{\mathrm{b1}}=1033$，$O_{\mathrm{fc2}}=1049$，$O_{\mathrm{b2}}=1209$。

来源：`{run_dir}/proof_artifacts/full_weights.json`（**禁止**默认读 `rust_files`）。

---

## 4. 客户端挑战（一轮交互 · P4）

| 挑战 | 字段 | 用于 |
|------|------|------|
| $\gamma$ | `ClientChallenge.gamma` | 卷积式 **(9)** |
| $\gamma'$ | `ClientChallenge.gamma_mult` | FC 式 **(10)** + L1 FC PtMul 槽 |
| $\gamma_{\mathrm{add}}$ | `ClientChallenge.gamma_add` | PtAdd 批（**不**用于池化 RLC） |
| 计数 | `num_point_mults` / `num_point_adds` | 来自 `ec_witness_schedule`（**非硬编码 178**） |

**须客户端采样**；服务器预知 $\gamma$ 且仅做链外标量 check → Freivalds 失效。

---

## 5. 分层陈述与验证（M1 · 链外 · 客户端必验）

验证方在随机 $\gamma,\gamma'$ 下 **只验压缩式**，不验逐格 eq5/eq8：

| 层 | 论文式 | 验证函数 | 输入 witness |
|----|--------|----------|--------------|
| Conv | **(9)** $\sum_r \gamma^r \hat a_r = \sum_r \gamma^r \langle f,\mathrm{win}_r\rangle$ | `verify_conv_eq9_rlc_only` | `conv_trace.json` + $f=\mathbf W^*_{0..8}$ |
| Pool | **(7)** 窗口求和 | `verify_pool_eq7_per_cell` | `pool_trace.json` |
| FC1/FC2 | **(10)** $\sum_j \gamma'^j t_j = \sum_k d_k(\sum_i \gamma'^i W_{k,i}) + \sum_j \gamma'^j b_j$ | `verify_fc_eq10_rlc_only` | `fc_trace.json` 激活 + **W* 中 FC 权重/偏置** |

代码入口：`ServerLinearProofStack::verify_all_client`（**不得** `fc_layers.clear()` fallback）。

---

## 6. 模型 ↔ EC 轨迹绑定（L1）

178 个 PtMul 乘数 $a_j$ 与 $\mathbf W^*$ 的代数关系（prove 前 `sync_ptmul_weights_for_challenge` 用 $\gamma'$ 写 FC 槽）：

| $j$ 区间 | 层 | 关系 |
|----------|-----|------|
| $[0,18)$ | Conv × $B{=}2$ | $a_j = \mathbf W^*_{j \bmod 9}$ |
| $[18,146)$ | FC1 × $B{=}2$ | $a_j = \sum_{i=0}^{15} (\gamma')^i \mathbf W^*_{9+p\cdot16+i}$，$p=(j-18)\bmod 64$ |
| $[146,178)$ | FC2 × $B{=}2$ | $a_j = \sum_{i=0}^{9} (\gamma')^i \mathbf W^*_{1049+p\cdot10+i}$，$p=(j-146)\bmod 16$ |

Bias：**不在** PtMul 乘数；`check_fc_bias_wstar_bindings` 绑 `fc_trace` 偏置 ↔ $\mathbf W^*_{1033..1048}$、$[1209..1218]$。

代码：`circuit/bind_l1.rs` — `check_l1_ptmul_bindings`、`ptmul_source_for_j`。

---

## 7. EC-SNARK（整批 gadget · 论文 Table I 压缩轨迹）

| 项 | 规范 |
|----|------|
| **证什么** | 每条 PtMul / PtAdd 的 $E_2$ 代数 gadget 正确（**不**单独陈述式 9/10） |
| **Witness** | `{run_dir}/proof_artifacts/ec_witness/pointMult/*`、`pointAdd/*` |
| **计数** | `EcWitnessMode::paper_proof` → schedule 推导（A：178 / 2144） |
| **代码** | `prove_ec_timed` / `verify_ec_bundle`；子电路 `point_mult.rs`、`point_addition.rs` |
| **Transcript 顺序** | ① Spartan `cm_W` ② Pedersen cm_W/cm_x ③ $\gamma,\gamma',\gamma_{\mathrm{add}}$ ④ sub_circuit 标签 ⑤ FS 挑战 → $\pi$ |

**禁止：** 默认读 `rust_files/A`；`VPIN_ALLOW_LEGACY_WITNESS=1` 仅单元测试。

---

## 8. 分层证明产物（M5 · 目标形态）

论文 Fig.7：$\phi_{\mathrm{cnv}},\phi_{\mathrm{pl}},\phi_{\mathrm{fc}}$ **按层**证明，共享 transcript。

| 产物 | 陈述 | 现状 |
|------|------|------|
| `π_conv` | 式 (9) in-circuit + 该层 EC | **stub**（`circuit/layer/conv_mac.rs`） |
| `π_pool` | 式 (7) + PtAdd | **stub** |
| `π_fc[k]` | 式 (10) + gadget | **stub** |

**MVP 闭合路径（无 stub 冒充）：** M1 链外验式 (7)(9)(10) + L1 + CPS.Ver + EC-SNARK + trace digest。  
`layer_proofs` stub 仅标记结构位；`proof_coverage: layer_proofs_plus_cps` **不**表示 eq9/7/10 已 in-circuit。

---

## 9. Prove / Verify 算法（端到端）

### 9.1 Prove（服务端 · 已知 $\mathbf W^*$ 与 witness）

```text
输入: model_id=A, run_dir, ClientChallenge (γ, γ′, …)

1. ProofPlan.activate_witness()  → VPIN_EC_WITNESS_ROOT, VPIN_TRACE_ROOT
2. W* ← full_weights.json
3. sync_ptmul_weights_for_challenge(ec_witness, W*, challenge)   // FC 槽写 γ′ 列
4. check_fc_bias_wstar_bindings(A, W*)
5. check_l1_ptmul_bindings(A, W*, challenge)  → 失败则 abort
6. M1 ← verify_all_client(challenge) on conv/pool/fc traces  → 失败则 abort
7. cm_W ← cps_comm_w_star(W*)
8. cm_aux ← cps_comm_aux_witness(model_opening)
9. trace_digest ← SHA256(conv∥pool∥fc traces)
10. π_ec ← Spartan.prove(PtAdd ∥ PtMul) with transcript(cm_W, cm_x, γ, …)
11. layer_proofs ← prove_layer_stack (stub)
12. 输出 ProtocolArtifacts v3
```

### 9.2 Verify（客户端 · 仅 opening 或已知 W* 子集）

```text
1. scalar_trace_digest 与 run_dir traces 一致
2. M1: verify_all_client(γ, γ′) — conv (9), pool (7), fc (10)
3. L1: sync_ptmul + check_l1_ptmul_bindings + bias + Merkle(W*)
4. CPS.Ver(cm_W) 对 opening 中 W*
5. verify_ec_bundle(π_ec, cm_W in transcript)
6. verify_layer_stack (stub 标记)
```

---

## 10. Witness 导出（Python）

| 文件 | 职责 |
|------|------|
| `export_proof_artifacts.py` | 训练 run 定点前向 → trace + full_weights + 触发 rLCR EC |
| `export_rlcr_ec_witness.py` | **训练 `*.npy` 权重** + Server.py rLCR → ec_witness px/py |
| `paper_proof_witness_exporter.py` | conv PtMul 槽 ← $\mathbf W^*_{0..8}$（FC 槽 prove 时写 $\gamma'$） |
| `ec_witness_schedule.py` | paper_proof 计数与层区间 |

标准 run：`model_training/outputs/20260622_184254`（**训练 checkpoint + compact_weights**）。

| 产物 | 来源 |
|------|------|
| `full_weights.json` / MAC trace | 训练 run 定点前向 `export_proof_artifacts.py` |
| `ec_witness` px/py | 训练权重 rLCR `export_rlcr_ec_witness.py`（**须** FC 中间值 ≤ BSGS 表；20260622 当前 **超界**，见 §11） |
| PtMul conv 槽 | 训练 $\mathbf W^*_{0..8}$ |

**禁止**默认读 `rust_files/A`。

---

## 11. 诚实边界

| 已闭合（MVP） | 未闭合 |
|---------------|--------|
| paper_proof 计数 + schedule | M5 全量 in-circuit eq9/7/10 |
| M1 + L1 + CPS + EC + Z.8 transcript（**W* / trace 来自训练 run**） | 训练 run rLCR EC px/py（FC1 超 BSGS 表，20260622） |
| 客户端 γ/γ′ | TReLU（客户端截断，不证） |

---

## 12. 代码索引

| 模块 | 路径 |
|------|------|
| Prove/Verify | `src/cp-snark-full/src/prove/pipeline.rs`, `verify/pipeline.rs` |
| M1 | `src/cp-snark-full/src/layer_proof/` |
| L1 | `src/cp-snark-full/src/circuit/bind_l1.rs` |
| CPS | `src/cp-snark-full/src/commit/cps.rs` |
| EC SNARK | `src/cp-snark-full/src/circuit_prove.rs` |
| Trace digest | `src/cp-snark-full/src/trace/digest.rs` |
| Witness 导出 | `model_training/network_a/paper_proof_witness_exporter.py` |
