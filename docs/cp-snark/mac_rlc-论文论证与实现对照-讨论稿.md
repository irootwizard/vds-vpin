# π_mac / `mac_rlc`：论文论证与实现对照（讨论稿）

> **⚠️ 部分已 superseded（2026-06-10）**  
> **定稿请读：** [`cp-snark-分层证明与RLC设计定稿.md`](./cp-snark-分层证明与RLC设计定稿.md)  
> - **废弃：** 合并 `MacRlcProof`、`circuit/mac_rlc` 桩（电路外 left/right）、客户端必验 eq5+eq9 双检。  
> - **保留讨论价值：** 式 (5)–(10) 符号对照、π_ec 与 RLC 分工、按层 π 目标。  
> **状态快照：** `mac_proof: null`；式 (9) **计算**已在 `Server.py` `rLCL`/`rLCR` 实现。

---

## 0. 讨论目标（请数学 agent 重点回答）

1. **陈述完备性：** 当前标量路径 +（规划中的）`mac_rlc` R1CS，是否足以使验证方相信「服务器在声明模型 W、输入 x 上完成了论文 §IV–V 的线性层计算」？
2. **式 (9)(10) in-circuit：** 应将哪些量设为 **公开输入 / witness / 常量**？γ、γ′ 如何进入约束才满足 soundness（相对 Python `pf(sk)` 自检）？
3. **层粒度：** 一个 `MacRlcProof` 合并 Conv(9)+FC(10)，还是 `conv_rlc` + `fc_rlc` 两个子证明？对 transcript 与约束规模的影响？
4. **与 π_ec 分工：** 178 PtMul / 2144 PtAdd 证明的是什么代数对象？为何**不能**用 π_ec 替代式 (9)？
5. **池化 (7)：** 确认「不进 π_mac、仅 PtAdd + 标量 check」是否与论文一致。
6. **当前桩电路：** `left == right`（left/right 电路外预计算）的 SNARK 证了什么、**没证什么**？升级到 in-circuit RLC 的最小约束递推方案？

---

## 1. 论文符号与仓库编码（对照表）

| 论文符号 | 含义 | 仓库类型 / 字段 | 编码 |
|----------|------|-----------------|------|
| $\mathbf{W}^*$ / $f$ | 静态模型（卷积核、FC 权重/bias） | `full_weights.json`（1219 维）；`ConvLayerProofSpec.filter_flat`（9） | `u128`；`curve::embed_u128_to_scalar` |
| $\hat{a}_r$ / `output_flat` | 卷积第 $r$ 格输出 | `conv_trace.json` → `ConvLayerProofSpec.output_flat` | 同上 |
| `window_r` | 第 $r$ 格 $k^2$ 窗口 | `conv_trace.json` → `ConvLayerProofSpec.windows` | 同上 |
| $\gamma$ | 验证方挑战（式 (9)） | `ClientChallenge.gamma` | `Scalar`；`challenge.gamma_scalar()` |
| $\gamma'$ | FC 挑战（式 (10)） | `ClientChallenge.gamma_mult` | `challenge.gamma_mult_scalar()` |
| $\llbracket\cdot\rrbracket_2$ | 同态密文（EC 点） | `rust_files/A/pointMult/*.json` 等 | PtMul/PtAdd witness；**非** mac_rlc 直接输入 |
| $\mathsf{cm}_W,\mathsf{cm}_x$ | 模型/输入承诺 | `ProtocolArtifacts.model_commitment` 等 | Pedersen + transcript |

**论文参考：** [vPIN arXiv:2411.07468](https://arxiv.org/pdf/2411.07468) §IV–V；仓库文字版 [`各层计算量证明算法-论文对齐.md`](./各层计算量证明算法-论文对齐.md)。

---

## 2. 论文各式：数学形式与代码落点

### 2.1 卷积

**逐格 MAC（式 (5)(6) 精神）：**

$$
\hat{a}_r = \langle f,\, \text{window}_r \rangle = \sum_{k=0}^{K^2-1} f[k]\cdot \text{window}_r[k]
$$

| 实现 | 路径 |
|------|------|
| 标量 | `layer_proof/verify.rs::verify_conv_eq5_per_cell` |
| MAC 核 | `layer_proof/rlc.rs::mac_filter_window` |

**随机线性组合（式 (9)）：**

$$
\sum_{r=0}^{R-1} \gamma^r \cdot \hat{a}_r
\;=\;
\sum_{r=0}^{R-1} \gamma^r \cdot \langle f,\, \text{window}_r \rangle
$$

| 实现 | 路径 |
|------|------|
| 左端 $\sum \gamma^r \hat{a}_r$ | `rlc.rs::conv_rlc_left` → `fold_rlc(outputs, γ)` |
| 右端 $\sum \gamma^r \text{MAC}(f,\text{win}_r)$ | `rlc.rs::conv_rlc_right` |
| 标量验证 | `verify.rs::verify_conv_eq9_rlc`（先 eq5 再 eq9） |
| **SNARK（桩）** | `circuit/mac_rlc/build.rs`：电路外算 left/right，R1CS 约束 $(v_0 - v_1)\cdot 1 = 0$ |

**讨论点：** 式 (9) 在标量域用**客户端** $\gamma$；Python `Server.py` 用 `pf(secret_key,i)` 自检 — soundness 差异需在论证中明确。

### 2.2 平均池化

**式 (7)（同态求和，缩放公开）：**

$$
JB_{i,j} = \sum_{(i',j') \in \text{window}} JA_{i',j'}
\quad;\quad
\text{输出} = JB \times (1/\hat{k}^2)_{\text{fixed-point}}
$$

| 实现 | 路径 |
|------|------|
| 标量（缩放前） | `verify.rs::verify_pool_eq7_per_cell` |
| `output_sums` | `pool_trace.json` → `PoolLayerProofSpec.output_sums` |
| 公开 $1/\hat{k}^2$ | `ModelParams.pool.inv_k_squared_fp` |

**架构定案：** 池化**不进** $\pi_{\mathrm{mac}}$ / `mac_rlc` R1CS；仅 PtAdd 链（π_ec）+ 标量 eq7。

### 2.3 全连接

**式 (8)（逐输出）：**

$$
t[j] = \sum_k W[k,j]\cdot d[k] + b[j]
$$

**式 (10)（RLC）：**

$$
\sum_j \gamma'^j \cdot t[j]
=
\sum_k d[k]\cdot\Big(\sum_i \gamma'^i W[k,i]\Big)
+ \sum_j \gamma'^j b[j]
$$

| 实现 | 路径 |
|------|------|
| eq8 | `verify.rs::verify_fc_eq8_per_output` |
| eq10 | `verify.rs::verify_fc_eq10_rlc`；`rlc.rs::fc_rlc_left/right` |
| SNARK | **未实现**（`mac_rlc` 仅 conv） |

**Network A 现状：** `fc_trace.json` 的 `layers: []` → `check_all_scalar` **跳过 FC**。

---

## 3. 两条证明族（数学对象必须分开论证）

### 3.1 $\pi_{\mathrm{mac}}$ — MAC + RLC 证明族

| 属性 | 说明 |
|------|------|
| **意图** | 证明线性层 **标量 MAC 关系** 在 RLC 压缩后成立（式 (9)(10)） |
| **代码** | `circuit/mac_rlc/*`，`prove/mac.rs`，`verify/mac.rs` |
| **产物** | `ProtocolArtifacts.mac_proof: Option<MacRlcProof>` |
| **当前** | `mac_proof = null`（管线关闭） |

### 3.2 $\pi_{\mathrm{ec}}$ — EC gadget 证明族

| 属性 | 说明 |
|------|------|
| **意图** | 证明同态推理轨迹上 **PtMul / PtAdd** 的 R1CS 代数正确 |
| **代码** | `circuit_prove.rs`，`prove/ec.rs`，`circuit/ec/` |
| **产物** | `EcProofBundle { point_add, point_mult }` |
| **当前** | **在跑**；Network A：2144 PtAdd + 178 PtMul |

**关键区分（§11.2 架构草案）：** 178 次 PtMul 证的是 **EC 标量乘 gadget**，不是「对每格完整 $k^2$ 窗口的式 (9) 陈述」。卷积 RLC 仍需 `ConvWitness`（`conv_trace.json`）或等价公开输入。

---

## 4. 对哪一层「生成证明」？

### 4.1 按层：标量 check vs SNARK

| 层 | 论文式 | 挑战 | 标量 `check_all_scalar` | `mac_rlc` SNARK（设计） | `mac_rlc` SNARK（现状） | π_ec |
|----|--------|------|-------------------------|-------------------------|-------------------------|------|
| 卷积 | (5)(6)+(9) | $\gamma$ | ✅ | ✅ 应覆盖 | ⚠️ 桩，未启用 | 混合在 178 PtMul |
| 池化 | (7) | — | ✅ | ❌ 不进 | ❌ | PtAdd 链 |
| FC | (8)+(10) | $\gamma'$ | ⏸ 无 trace | ✅ 应覆盖 | ❌ 未实现 | 混合在 PtMul |
| TReLU | — | — | ❌ 客户端 | ❌ | ❌ | ❌ |

### 4.2 标量检查顺序

`ServerLinearProofStack::verify_all`（`layer_proof/stack.rs`）：

```text
conv  → verify_conv_eq9_rlc
pool  → verify_pool_eq7_per_cell
fc[]  → verify_fc_eq10_rlc   (每层)
```

在 `prove/pipeline.rs` 中 **`run_scalar_check` 强制于 prove 之前**；失败则 abort。

---

## 5. 源码索引（mac_rlc 全链路）

### 5.1 R1CS 子电路

| 文件 | 函数 / 类型 | 职责 |
|------|-------------|------|
| `circuit/mac_rlc/mod.rs` | `MacRlcProof` | 序列化产物 |
| `circuit/mac_rlc/build.rs` | `build_conv_rlc_circuit`, `build_mac_rlc_circuit` | 构建 Instance；**仅 conv** |
| `circuit/mac_rlc/prove.rs` | `prove_mac_rlc_snark` | `SNARK::prove`（**非** `my_lib_prove`） |
| `circuit/mac_rlc/verify.rs` | `verify_mac_rlc_snark` | 重建 stack + `SNARK::verify` |

**当前 R1CS（桩）：**

- 约束数：逻辑 1 → Spartan 填充后 2
- Witness：$v_0=\text{left}$，$v_1=\text{right}$（**电路外**由 `conv_rlc_left/right` 计算）
- 公开输入：$\gamma$，常量 tag `9`（**未出现在 A/B/C 矩阵中**）

### 5.2 证明编排

| 文件 | 状态 |
|------|------|
| `prove/mac.rs` | `prove_mac_rlc` → 调 `prove_mac_rlc_snark` |
| `prove/pipeline.rs` | **已关闭**：`mac_proof = None`（见 §6） |
| `verify/mac.rs` | 薄封装 `verify_mac_rlc_snark` |
| `verify/pipeline.rs` | `mac_proof.is_some()` 时才验 |
| `protocol/artifacts.rs` | `mac_proof`, `prove_mac_ms`, `proof_coverage` |

### 5.3 Witness 组装（mac_rlc 输入）

| 文件 | 职责 |
|------|------|
| `trace/build.rs` | `build_linear_stack` → `ServerLinearProofStack` |
| `trace/conv.rs` | `conv_trace.json` → `ConvLayerProofSpec` |
| `trace/pool.rs` | `pool_trace.json` |
| `trace/fc.rs` | `fc_trace.json` |
| `model_exports/A/conv_trace.json` | filter、windows、output_flat（16 cells） |

### 5.4 标量层（与 mac_rlc 共享数学，无 SNARK）

| 文件 | 职责 |
|------|------|
| `layer_proof/rlc.rs` | 式 (9)(10) RLC 代数 |
| `layer_proof/verify.rs` | eq5/7/8/9/10 |
| `layer_proof/stack.rs` | `check_all_scalar` |
| `statement/mod.rs` | 架构别名；`statement::check::*` |

### 5.5 对照：π_ec 证明生成

| 文件 | 职责 |
|------|------|
| `prove/ec.rs` | `prove_point_add`, `prove_point_mult` |
| `circuit_prove.rs` | `my_lib_prove`，分块 witness 承诺 |
| `rust_files/A/pointAdd|pointMult/*.json` | EC 轨迹 witness |

---

## 6. 证明生成接入流程（设计 vs 现状）

### 6.1 架构草案 prover 总线

```text
commit(cm_W, cm_x)
  → ClientChallenge (γ, γ′, num_point_adds, num_point_mults)
  → [1] stack.check_all_scalar(challenge)     # 标量，prover 必跑
  → [2] prove_mac_rlc(stack, cm, challenge)   # π_mac SNARK
  → [3] prove_ec_batch(network, cm, challenge) # π_ec SNARK
  → ProtocolArtifacts
```

### 6.2 现状（2026-06-05）

```text
[1] check_all_scalar     ✅ 通过（conv+pool；fc 空）
[2] prove_mac_rlc        ❌ 关闭（mac_proof = null）
[3] prove_ec_batch       ✅ ~208s，verify 通过
```

`proof_coverage`：**`ec_plus_l1_binding`**（非 `ec_plus_mac_rlc`）。

### 6.3 Transcript 片段（mac_rlc 设计）

```text
transcript = "cp_snark_vpin"
  → append(cm_W, cm_x)
  → append(γ, γ_add, γ_mult, ...)
  → append_message("sub_circuit", "mac_rlc_conv_eq9")
  → Spartan FS 挑战 → SNARK proof
```

与 EC 子电路共用同一 transcript 前缀；子电路以 `sub_circuit` 标签区分。

---

## 7. 已知实现问题（供数学论证时纳入「当前系统能证什么」）

### 7.1 工程 blocker：Spartan 路径不兼容

- `mac_rlc/prove.rs` 使用裸 **`SNARK::prove`**
- EC 子电路使用 **`my_lib_prove`** + `padded_vars_para` / `padded_vars_input`（`circuit_prove.rs`）
- 启用 mac_rlc 时运行时 panic：`commitments.rs` 断言 `8 vs 4`（多项式承诺维度）

**推论：** 在论证「客户端可验证 π_mac」之前，需先统一证明路径（数学陈述不变，实现阻塞）。

### 7.2 语义 gap：桩电路

| 已证（若 SNARK 跑通） | 未证 |
|----------------------|------|
| 两个 field 元素 $v_0,v_1$ 相等 | windows、filter、outputs 与 $v_0,v_1$ 的绑定 |
| transcript 绑定了 cm_W、cm_x、γ | $\gamma$ 出现在公开输入但未进约束 |
| — | 式 (10) FC |
| — | in-circuit $\gamma^r$ 累加 |

标量层 `verify_conv_eq9_rlc` 在 **prover 本地** 做了完整 eq5+eq9，但 **客户端不重新跑**（除非另接 verify 逻辑）；客户端目前主要验 π_ec + 承诺。

### 7.3 验证方数据依赖

`verify_mac_rlc_snark` 调用 `build_stack_for_network` 重建 witness，隐式依赖 `model_exports/{net}/*.json`，非纯 `protocol.json` 自包含。

---

## 8. 开放数学问题清单（建议 agent 逐条给论证）

### 8.1 Soundness

- [ ] 仅 prover 跑 `check_all_scalar` + 客户端验 π_ec，是否足以蕴含式 (9)(10)？
- [ ] 若 π_mac 仅为 $v_0=v_1$ 且 $v_0,v_1$ 由 prover 自选 witness，soundness 是否退化为平凡？
- [ ] 将 left/right 改为 witness 并由 R1CS 约束其与 **公开** filter/windows 的 MAC 关系，最小约束集是什么？

### 8.2 公开输入设计

- [ ] $\gamma$ 应为公开输入还是 transcript 挑战后隐式进入？当前 `build.rs` 写入 `inputs[0]=γ` 但矩阵未引用。
- [ ] `cm_W` 是否应通过 opening 将 $f$ 绑定为 witness 或公开输入？L1 仅 18/178 PtMul 命中 W\*。

### 8.3 与 π_ec 组合

- [ ] 命题「服务器推理正确」的合取范式：$(\text{eq9}) \land (\text{eq7}) \land (\text{eq10}) \land (\text{EC})$？缺一项时的攻击面？
- [ ] `rlc_binding_hex`（权重/公开输入标量和的 RLC）在论证中的角色？

### 8.4 R1CS 规模（架构草案估 +5–15%）

- [ ] in-circuit `fold_rlc` 递推：$O(R)$ 乘法约束 vs 一次压缩等式？
- [ ] 单 `mac_rlc` vs 拆 `conv_rlc` + `fc_rlc` 对约束数与 transcript 的影响？

### 8.5 池化

- [ ] 确认式 (7) 不需 γ 压缩的论文依据；PtAdd 链 + 公开缩放是否完备？

---

## 9. 建议论证输出格式（给协作 agent）

请按以下结构回复，便于回写实现：

1. **命题陈述** $P(\mathsf{cm}_W,\mathsf{cm}_x,\gamma,\ldots)$：客户端应相信什么。
2. **子引理：** $L_{\mathrm{conv}}^{(9)}$, $L_{\mathrm{pool}}^{(7)}$, $L_{\mathrm{fc}}^{(10)}$, $L_{\mathrm{ec}}$ 的定义与依赖。
3. **当前系统：** 对每个 $L_*$ 标 ✅ 标量 / ✅ SNARK / ❌ / ⚠️ 桩。
4. **目标系统：** in-circuit mac_rlc 应证的布尔关系或代数关系（显式 witness 向量）。
5. **迁移步骤：** 数学上必须先证什么再接入 R1CS（可与 §8 开放问题对应）。

---

## 10. 复现命令与数据

```bash
cd src/cp-snark-full
cargo run -- prove A          # mac_proof=null, ec_plus_l1_binding
cargo run -- verify A
python python/check_model_exports.py --network A
```

**关键数据：**

- `model_exports/A/conv_trace.json` — 16 cells，filter 与 W\*[:9] 一致
- `model_exports/A/pool_trace.json` — Eq.7 raw sum
- `model_exports/A/fc_trace.json` — `layers: []`
- `artifacts/A/protocol.json` — `mac_proof: null`

---

## 11. 修订记录

| 日期 | 说明 |
|------|------|
| 2026-06-05 | 初稿：供 mac_rlc 论文数学论证协作；含代码索引、层覆盖、开放问题 |
