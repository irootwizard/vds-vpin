# CP-SNARK 自检报告与计算量预估

> **总路线图（排期/摘要）：** [`综合未来工作路线图.md`](./综合未来工作路线图.md) **§1.4**（承诺）、**§12**（计算量对照表）  
> **设计定稿：** [`cp-snark-分层证明与RLC设计定稿.md`](./cp-snark-分层证明与RLC设计定稿.md)  
> 文档对象：`src/cp-snark-full`（[C]）+ 原 [A][B] 路径  
> 基准网络：CNN **A**  
> 论文参考：[vPIN (arXiv:2411.07468)](https://arxiv.org/pdf/2411.07468)  
> **说明：** 本文 = 自检结论 + **完整** R1CS 推导；排期用表以路线图 §12 为准。

---

## 一、自检目标

判断当前实现能否向客户端密码学证明：

> **「客户端选定的模型 W，在指定输入 x 上，完成了声明的 vPIN 同态推理计算。」**

---

## 二、自检结论（摘要）

| 判定维度 | 结论 |
|----------|------|
| 严格密码学 / 论文语义 | **不能** ❌ |
| 弱语义（witness 标量 + EC 运算代数正确） | **部分满足** ⚠️ |
| 工程演示（协议流程 + 本地 verify 通过） | **满足** ✅ |

**一句话：** 当前 `cp-snark-full` 完成了 CP-SNARK **协议骨架**与 **PtAdd/PtMul 子电路证明**，但**不能**等价于「完整模型 + 指定输入 → 完整推理正确」的端到端证明。

---

## 三、命题分解与满足情况

| 编号 | 子命题 | 是否满足 | 说明 |
|------|--------|----------|------|
| P1 | 选定模型 W 被正确承诺 | ⚠️ 弱 | `cm_W` 仅承诺 `weight.json` 中 178 个标量，非 `.npy` 完整 CNN 参数 |
| P2 | 指定输入 x 被绑定 | ❌ | `cm_x` 仅承诺曲线系数 **a**，非客户端图像/密文 |
| P3 | 完整网络计算正确 | ❌ | 无卷积/FC/池化 MAC 层 R1CS，仅有 EC gadget 证明 |
| P4 | witness 与推理一致 | ❌ | 未在电路中证明「witness 轨迹 = 同态推理产物」 |
| P5 | 客户端独立验证 | ⚠️ 弱 | Rust 可独立 `verify`，但仍依赖本地 `rust_files` JSON |
| P6 | EC 子电路代数正确 | ✅ | PtAdd/PtMul R1CS + Spartan 验证通过 |

---

## 四、现状实现逐项核对

### 4.1 已正确实现

1. **协议阶段**：Setup → 模型承诺 → 输入承诺 → 客户端挑战 γ → 证明 → 验证（`protocol.rs`）。
2. **子电路证明**：点加 2144 次、点乘 178 次，R1CS 满足 RevBin + PA + PD + MUX（`point_addition.rs` / `point_mult.rs`）。
3. **Transcript 绑定**：`cm_W`、`cm_x`、`γ` 写入 `cp_snark_vpin` transcript，再进入 Spartan FS 挑战。
4. **协作证明变体**：分块 witness 承诺（`vars_para` / `vars_input`）+ `my_lib_prove` / `my_lib_verify`（复用 `commit_test.rs`）。
5. **论文曲线嵌入（E₂ 基域 $n_2=q_1$）**：已在原仓库实现——`curveE2Info()` 的 `curveBaseField` = Ristretto $q_1$；`point_mult.rs` 将 E₂ 系数 **a** 与 witness 坐标经 `from_bytes_mod_order` 映射到 SNARK 标量域；与论文 ECB 参数及附录 Setup 一致（**不是** cp-snark-full 待补项）。

### 4.2 关键缺口

#### （1）模型承诺 ≠ 完整 W

```text
commit_model()  ← load_weights_only() ← weight.json (178 个标量)
完整 W            ← Pre_trained_model/*.npy (卷积核 + FC1/FC2 + bias)
```

- `weight.json` 来自推理时 `weights_array`（rLCR 路径上的标量乘权重），**不是**全网参数张量。
- 网络 A 完整参数量级约 **|W| ≈ 1.2×10³**（见 §六），与 178 不等。

#### （2）输入承诺未绑定 x

- `public_inputs_for_network()` 仅嵌入曲线 Weierstrass 系数 **a**。
- 客户端加密输入、固定点编码、密文 **均未进入** R1CS 公开输入。

#### （3）cm_W 与 R1CS vars_para 无电路级等式

- 点乘 `vars_para` 槽位存标量乘权重；点加 `vars_para` **全零**。
- `cm_W` 的 Pedersen 承诺 + SHA256 摘要与 SNARK 内 `comm_vars_para` **两套独立机制**。
- transcript 绑定 **不改变 R1CS 可满足性语义**。

#### （4）cp-snark-full 承诺路径与 witness 编码路径不统一

| 路径 | 编码 |
|------|------|
| `commit_model`（cp-snark-full） | `libspartan::Scalar::from_bytes_wide`（mod $q_1$） |
| `point_mult` witness（原仓库） | `curve25519_dalek::Scalar::from(u128)` + `to_bytes()` |

这与**论文曲线嵌入**无关：嵌入已在 `point_mult` 对 **a / px / py** 的 `from_bytes_mod_order` 中完成。此处风险是 cp-snark-full **Pedersen 承诺**与 Spartan witness 权重槽若编码函数不同，可能削弱「承诺权重 = 证明权重」。对落在 `u128` 范围内的整数，两种写法 mod $q_1$ 结果相同；部分 `weight.json` 项超过 `u128`，原 `point_mult` 本身存在截断风险，属独立问题。

#### （5）验证方依赖 prover 侧文件

- `verifier_run()` 从 `rust_files/{network}/pointMult/weight.json` **重新读取**权重再比对 `digest_hex`。
- 未验证 Pedersen 点 `point_hex` 打开；非论文「客户端仅持 cm 验证」模型。

#### （6）RLC 绑定过弱 + 与 [A] 重复

- `rlc_binding_hex` 在 SNARK **外**，无密码学关联（**定稿：不作为安全依据**）。
- 式 (9) 标量检查在 `layer_proof` 与 [A] `Server.py` assert **语义重复**；`mac_rlc` 桩 **已停用**（见设计定稿 §2.3）。

### 4.3 实测基准（network=A，debug 构建）

来源：`cargo run -- full A` / `artifacts/A/protocol.json`

| 指标 | 点加 | 点乘 | 合计 |
|------|------|------|------|
| 运算次数 | 2 144 | 178 | — |
| 证明大小 | 78 176 B | 180 840 B | **≈259 KB** |
| 证明生成时间 | — | — | **≈201 s** |
| 验证时间 | — | — | **≈54 s** |

---

## 五、论文与代码中的计算量符号

### 5.1 基本 gadget 约束（代码精确式）

记标量乘比特宽 **n = 128**（`load_data.rs`），则：

| 符号 | 含义 | 代码/论文对应 |
|------|------|----------------|
| **C_PtAdd** | 单次点加 R1CS 约束数 | **10**（`point_addition.rs`） |
| **C_PtMul(n)** | 单次标量乘 gadget 约束数 | **27n + 8 = 3464**（`point_mult.rs`） |
| **V_PtAdd** | 单次点加 witness 变量 | **15** |
| **V_PtMul(n)** | 单次标量乘 witness 变量 | **n + 10 + 26n = 3466** |
| **\|PtAdd\|** | 推理产生的点加次数 | network A：**2144** |
| **\|PtMul\|** | 推理产生的标量乘次数 | network A：**178** |
| **\|W\|** | 模型参数总数 | 卷积核 + FC 权重 + bias（§六） |
| **\|x\|** | 输入固定点标量数 | 与图像尺寸/池化后 flatten 相关 |
| **g, h** | FC 输出/输入维度 | 式 (8)(10)；A 网 FC1：g=16, h=64 |
| **γ, γ'** | 客户端随机挑战 | 式 (9)(10) 随机线性组合 |

### 5.2 论文层 MAC / 线性层（符号）

| 公式 | 含义 | 论文约束量级 |
|------|------|--------------|
| 式 (6) | 同态卷积 MAC | 每个输出窗口 **O(k²)** 次乘加 → EC 上多次 PtMul/PtAdd |
| 式 (7) | 平均池化 | 窗口求和 + 定点倒数标量乘 |
| 式 (8) | 全连接 MAC | **O(g·h)** 次乘加 |
| 式 (9) | 卷积随机线性组合 | 验证方 **γ** 压缩为 **1** 次 EC 一致性 |
| 式 (10) | FC 随机线性组合 | 由 **O(g·h)** 压缩到 **O(g)** 量级点乘约束 |

> 论文要点（见对照说明 §八）：FC 先 naive **O(g·h)**，再借式 (10) 降到 **O(g)**；池化可用 PtAdd gadget 表述。

### 5.3 当前实现的 R1CS 总规模（network A）

$$
C_{\text{current}}
= |PtAdd| \cdot C_{PtAdd} + |PtMul| \cdot C_{PtMul}(n)
= 2144 \times 10 + 178 \times 3464
= \mathbf{638\,032}
$$

$$
V_{\text{current}}
= |PtAdd| \cdot V_{PtAdd} + |PtMul| \cdot V_{PtMul}(n) + O(1)
\approx 2144 \times 15 + 178 \times 3466 + 1
= \mathbf{649\,125}
$$

与源码一致：

- `point_addition`: `num_cons = 10 × 2144 = 21 440`
- `point_mult`: `num_cons = 3464 × 178 = 616 592`

### 5.4 Spartan 证明开销渐近（CP-SNARK 证明器）

记 **C** = R1CS 约束数，**V** = witness 变量数，Spartan 系：

| 阶段 | 渐近 | 对应当前量级 |
|------|------|--------------|
| 证明生成 | **Õ(C)**（sumcheck + 多项式承诺） | C ≈ 6.4×10⁵ → 实测 **~201 s** |
| 证明大小 | **Õ(√V · log C)** | V ≈ 6.5×10⁵ → 实测 **~259 KB** |
| 验证 | **Õ(C)** 但常数小 | 实测 **~54 s** |

（Õ 忽略 log 因子；实测含矩阵构造、JSON 读写、debug 构建，release 会更快。）

---

## 六、网络 A 参数量与 witness 规模对照

| 对象 | 数量 | 来源 |
|------|------|------|
| 卷积核 | 3×3 = **9** | `Server.py` 固定滤波器 |
| FC1 权重 | 64×16 = **1 024** | `weight_fc1_64_16.npy` |
| FC1 bias | **16** | `bias_fc1_16.npy` |
| FC2 权重 | 16×10 = **160** | `weight_fc2_16_10.npy` |
| FC2 bias | **10** | `bias_fc2_10.npy` |
| **\|W\| 合计** | **≈ 1 219** | — |
| **weight.json（cm_W 实际承诺）** | **178** | rLCR 标量乘权重 |
| **\|PtMul\|** | **178** | 与 weight.json 一一对应 |
| **\|PtAdd\|** | **2 144** | 同态加轨迹 |

→ 完整 W 比当前承诺对象大约 **6.9×**；且 178 个标量是**运行时 MAC 系数**，不是独立存储的 W 切片。

---

## 七、增强方案：完整模型承诺 + 输入承诺 + 电路级绑定

### 7.1 三种增强层级

| 层级 | 内容 | 安全语义 |
|------|------|----------|
| **L1 最小绑定** | cm_W 覆盖完整 \|W\|；cm_x 覆盖 \|x\|；R1CS 增加 `w_i = witness_i` 等式 | 证明使用的标量与承诺一致，**仍不**证明 MAC/推理 |
| **L2 层间 MAC + 式 (10)** | 卷积/FC 增加 MAC 关系 + γ' 压缩；witness 标量与 cm_W 打开绑定 | 接近论文 FC/卷积证明语义 |
| **L3 端到端** | L2 + 密文/明文编码链 + 截断(TReLU) + 式 (9) 验证方 γ | 完整 vPIN 可验证推理 |

以下计算量预估 **L1 / L2**；L3 涉及交互协议与 AHE 编码电路，开销另计（通常 **≥ L2**）。

### 7.2 L1：电路级绑定（等式约束）

**模型绑定：** 对每个出现在 witness 中的权重槽位 i，增加：

$$
w_i \cdot 1 = \text{witness\_para}_i \quad (\text{1 条 R1CS})
$$

**输入绑定：** 对每个公开输入 x_j：

$$
x_j \cdot 1 = \text{input\_slot}_j \quad (\text{1 条 R1CS})
$$

**链外承诺（Setup）：**

- Pedersen **cm_W**：**O(|W|)** 次群标量乘（|**1 219** 量级，毫秒级）
- Pedersen **cm_x**：**O(|x|)**（例如 flatten 后 **64–784**，仍毫秒级）

**R1CS 增量（network A）：**

$$
\Delta C_{L1}
= k_w \cdot C_{eq} + |x| \cdot C_{eq},
\quad C_{eq} \approx 1\text{–}3
$$

取 **k_w = |PtMul| = 178**，**|x| ≈ 64**（池化后 8×8 假设）：

$$
\Delta C_{L1} \approx (178 + 64) \times 2 \approx \mathbf{484}
\quad\Rightarrow\quad
\frac{\Delta C_{L1}}{C_{\text{current}}} \approx \mathbf{0.08\%}
$$

**预估证明开销倍率：**

| 指标 | 倍率（相对当前） |
|------|------------------|
| 约束数 C | **≈ 1.001** |
| 证明大小 | **≈ 1.001 – 1.01** |
| 证明时间 | **≈ 1.001 – 1.02** |
| 验证时间 | **≈ 1.001 – 1.02** |

**结论：** L1 对 **638k** 约束规模几乎**可忽略**；主要工作量在工程（编码统一、Pedersen 打开验证），不在 R1CS 膨胀。

---

### 7.3 L1′：Merkle 打开绑定（完整 |W| 承诺、稀疏访问）

若 cm_W 为 Merkle 根，每次使用权重 w_i 需 **log|W|** 深度哈希路径。

$$
\Delta C_{L1'} \approx k_w \cdot C_{merkle}(|W|),
\quad C_{merkle}(|W|) \approx c_h \cdot \log_2 |W|
$$

|c_h| 取决于哈希 gadget（Poseidon 约 200–300 约束/轮；SHA256 更高）。  
**|W| = 1219 → log₂|W| ≈ 10**：

$$
\Delta C_{L1'} \approx 178 \times 10 \times c_h
\approx \mathbf{3\,560 \text{–}53\,400} \quad (c_h = 2 \sim 30)
$$

| 指标 | 保守估计倍率 |
|------|--------------|
| C | **+0.6% – +8%** |
| 证明时间 | **+0.6% – +10%** |
| 证明大小 | **+1% – +12%** |

仍远小于 L2。

**$|W| \gtrsim 10^6$：** 上式中 $\log_2|W|$ 增至 $\approx 20$；若 $k_w \sim 10^4$，$\Delta C_{L1'}$ 可达 $10^6$ 约束量级，仍常小于 L2 naive。Setup 链外须改用 Merkle 流式建树，勿用 `commitment.rs` 逐元 Pedersen 循环。详见 [`大模型模型承诺优化方案.md`](./大模型模型承诺优化方案.md)。

---

### 7.4 L2：论文 MAC 层 + 式 (10) 压缩（FC 为主）

对 FC 层，论文 naive 约束：

$$
C_{FC,naive} = g \cdot h \cdot C_{MAC}
$$

其中 **C_MAC** 为一次乘加在 R1CS 上的表述成本。在同态推理中，一次 MAC 最终体现为 **1 次 PtMul + 若干 PtAdd**，故粗估：

$$
C_{MAC} \approx C_{PtMul}(n) + \alpha \cdot C_{PtAdd},
\quad \alpha \approx 2\text{–}4
$$

network A：**FC1** g=16, h=64；**FC2** g=10, h=16。

**Naive（无式 10 压缩）：**

$$
C_{FC,naive} = (16 \cdot 64 + 10 \cdot 16) \cdot (3464 + 3 \cdot 10)
= 1200 \times 3494
\approx \mathbf{4.19 \times 10^6}
$$

$$
\frac{C_{\text{current}} + C_{FC,naive}}{C_{\text{current}}}
\approx \frac{638032 + 4190400}{638032}
\approx \mathbf{7.6\times}
$$

**含式 (10) 压缩到 O(g)：** 每层约 **g** 次聚合 MAC 检查：

$$
C_{FC,compressed} = (g_1 + g_2) \cdot C_{PtMul}(n)
= (16 + 10) \times 3464
\approx \mathbf{90\,064}
$$

$$
\frac{C_{\text{current}} + C_{FC,compressed}}{C_{\text{current}}}
\approx \frac{638032 + 90064}{638032}
\approx \mathbf{1.14\times} \quad (+14\%)
$$

**再加卷积式 (9) + 池化 PtAdd：**

卷积输出通道×空间位置 × k² MAC；network A 输入小、单通道，粗估 **10²–10³** 量级 MAC，压缩后 **O(1)** 次 γ 组合：

$$
\Delta C_{conv+pool} \approx C_{PtMul}(n) + |PtAdd|_{pool} \cdot C_{PtAdd}
\approx 3464 + 10^2 \times 10
\approx \mathbf{4\,500 – 15\,000}
$$

**L2 合计约束（粗估）：**

$$
C_{L2} \approx C_{\text{current}} + C_{FC,compressed} + \Delta C_{conv+pool} + \Delta C_{L1}
\approx 638032 + 90064 + 10000 + 500
\approx \mathbf{7.4 \times 10^5}
$$

| 指标 | 相对当前 | 说明 |
|------|----------|------|
| 约束 C | **≈ 1.15 – 1.25×** | 式 (10) 压缩 indispensable |
| 证明大小 | **≈ 1.1 – 1.3×** | √V 增长 |
| 证明时间 | **≈ 1.15 – 1.35×** | Õ(C) |
| 验证时间 | **≈ 1.1 – 1.3×** | 同上 |

若 **不做式 (10) 压缩**（L2-naive）：

| 指标 | 相对当前 |
|------|----------|
| 约束 C | **≈ 7 – 8×** |
| 证明时间 | **≈ 7 – 10×**（粗估 **25–35 min** 级） |
| 证明大小 | **≈ 2.5 – 4×**（粗估 **0.6 – 1 MB**） |

---

### 7.5 L3：端到端（论文完整 CP-SNARK）

在 L2 基础上还需：

- 输入密文/固定点编码电路（**O(|x|)** 乘法约束）
- 客户端截断 TReLU / shifting 位宽控制（**O(|x|)** 比较/截断，实现方式影响大）
- 验证方采样的 **γ** 进入 RLCC 电路（式 9），而非服务端 `pf(secret_key)`

粗估在 L2 基础上再 **+30% – +100%** 约束（高度依赖截断 gadget 选型）；LeNet 规模（\|PtMul\| ~6000）下可能 **10× 于 network A**。

---

## 八、计算量对比总表（network A）

| 方案 | R1CS 约束 C | 相对 C_current | 证明时间（估） | 证明大小（估） | 能否证「W+x→推理」 |
|------|-------------|----------------|----------------|----------------|---------------------|
| **当前 cp-snark-full** | 638 032 | **1.00×** | **~201 s**（实测） | **~259 KB**（实测） | ❌ |
| **+ L1 等式绑定** | ≈638 500 | **1.001×** | **~202 s** | **~260 KB** | ⚠️ 仅绑定承诺 |
| **+ L1′ Merkle 绑定** | ≈642k–691k | **1.01–1.08×** | **~203–220 s** | **~262–290 KB** | ⚠️ |
| **+ L2（式10压缩）** | ≈740k | **1.16×** | **~230–270 s** | **~300–340 KB** | ⚠️ 线性层 |
| **+ L2-naive（无压缩）** | ≈4.8M | **7.6×** | **~25–35 min** | **~0.6–1 MB** | ⚠️ 仍缺 AHE 链 |
| **+ L3 端到端** | 10⁶–10⁷ 级 | **2–15×+** | **分钟–小时级** | **MB 级** | ✅ 论文目标 |

---

## 九、Spartan 证明器开销分解（符号对照）

当前单次子证明（点乘 dominant）主要耗时在：

$$
T_{prove} \approx T_{encode}(C) + T_{commit}(V) + T_{sumcheck}(C) + T_{eval}(C)
$$

| 项 | 符号含义 | network A 量级 |
|----|----------|----------------|
| **T_encode** | R1CS 矩阵承诺 `SNARK::encode` | O(nnz)，nnz_mult ≈ **737 600** |
| **T_commit** | witness 分块多项式承诺 | O(V log V)，V ≈ **6.5×10⁵** |
| **T_sumcheck** | 两阶段 sumcheck | O(C log C) |
| **T_eval** | 矩阵求值证明 | O(nnz) |

**L1** 几乎不增加 C、V 主项 → **T_prove 不变**。  
**L2** 增加 **~10⁵** 约束 → **T_prove 线性增加 ~15–25%**（实测需 benchmark 确认）。

---

## 十、与 AHE 同态计算量的关系（论文曲线嵌入）

> **论文依据：** §IV-B「Setup procedure」、式 (5) 及紧随其后的曲线嵌入说明；附录 Setup 伪代码；§VI「System Parameters」。  
> **编码必读：** 嵌入解决的是 **「把 AHE 点运算写进 SNARK 电路时的跨模数证明成本」**，不是替代 AHE 推理本身，也不等于 CP-SNARK 承诺/验证全流程已实现。

### 10.1 为什么需要曲线嵌入（问题从哪来）

vPIN 的服务器在 **AHE 密文** 上做 CNN 线性层（点加、标量乘点），客户端要验证这些运算正确。验证工具是 **CP-SNARK（E₁）**，电路里的赋值域是 **$\mathbb{Z}_{q_1}$**（本仓库为 Ristretto255 标量域）。

AHE 侧（E₂）同态运算发生在：

- **密文点坐标** $(x_c,y_c)$ 属于 **$\mathbb{F}_{n_2}$**（Weierstrass 曲线 $E_2/\mathbb{F}_{n_2}$）；
- **明文标量** $w$、加密随机数、私钥等属于 **$\mathbb{Z}_{q_2}$**（子群阶，指数 ElGamal 的离散对数空间）。

服务器要证明的正是：**在 E₂ 上对密文做的那次点加/倍点/标量乘**，与声明的代数关系一致。因此 SNARK 电路必须能表达 E₂ 上的坐标运算。若 **$n_2 \neq q_1$**（E₂ 基域与 SNARK 域不同），电路里每次坐标乘加都要写成「先 mod $n_2$，再 mod $q_1$」——论文式 (5) 的朴素写法。

### 10.2 嵌入前：式 (5) 为何极其昂贵（论文原意）

论文以一次同态相关的点运算（倍点/加法的坐标公式）为例，写出 CP-SNARK 中一组约束，典型形如：

$$
\text{aux} = (\cdots \bmod n_2) \bmod q_1
$$

即 **每个中间量都带「证明 mod $n_2$」**。论文指出（§IV-B）：

- 证明一次 $\hat{x}\cdot\hat{y} \bmod n_2$ 的最优 gadget 约需 **23** 条 R1CS 约束；
- 由此推得：证明 **一次点倍** 约 **161** 条、**一次点加** 约 **230** 条；
- 若用式 (4) 的 128-bit 标量乘点流程迭代这些 gadget，仅 **一次点乘** 可达约 **76834** 条约束。

因此瓶颈不是 Python `ecdsa` 里那一次实椭圆曲线运算，而是 **「在 $q_1$ 上证明另一素数域 $n_2$ 上的模运算」** 的电路开销。

### 10.3 曲线嵌入做什么（论文解法）

**曲线嵌入（curve embedding）** 不是把两条曲线方程改成同一条，而是 **在 Setup 里选取 E₂，使其基域与 E₁ 的群阶对齐**：

$$
\boxed{n_2 = q_1}
$$

其中 **$n_2$ 在论文中指 E₂ 的基域大小**（坐标 $x,y$ 所在的 $\mathbb{F}_{n_2}$），**$q_1$ 指 E₁ 的群阶 / SNARK 赋值域**。

附录 Setup 伪代码写得更直白：

```text
Find E1: base field n1, prime order q1
Find E2: base field q1, prime order q2   ← E2 的基域直接取 q1
```

**后果（论文逻辑）：**

1. 密文坐标本来在 $\mathbb{F}_{n_2}$ 上算；嵌入后 $n_2=q_1$，坐标运算与 SNARK 约束 **同一域**。
2. 式 (5) 中「先 mod $n_2$ 再 mod $q_1$」在赋值语义上 **合并为 $\bmod q_1$ 上的原生算术**（本原运算，而非「异国模」模拟电路）。
3. 不再需要为 **证明 mod $n_2$** 单独铺设大量 gadget → 约束数从式 (5) 量级降到本仓库 **点加 10 条 / 点乘 3464 条** 这类 **专用 EC gadget**（`point_addition.rs` / `point_mult.rs`）。

论文 §VI 用 **ECB toolkit** 生成 E₂ 的 $(\alpha_2,\beta_2)$，使 E₂ 基域 $= 2^{252}+277423\ldots989$，与 E₁（curve25519-dalek / Ristretto）的 **阶 $q_1$** 一致；E₂ 的 **群阶 $q_2$** 为另一素数（约 $2^{252}-124614\ldots947$），用于 ElGamal 标量，**故意不等于 $q_1$**。

### 10.4 两套运算域：编码时勿混（论文 vs 本仓库）

| 对象 | 论文符号 | 数学域 | 本仓库变量 / API | 是否等于 $q_1$ |
|------|----------|--------|------------------|----------------|
| SNARK / Ristretto 标量 | $q_1$ | $\mathbb{Z}_{q_1}$ | `libspartan::Scalar`、`embed_*` | 定义域 |
| E₂ 点坐标 $x,y,a$ | 在 $\mathbb{F}_{n_2}$ | $\mathbb{F}_{n_2}$ | `curveBaseField`；`from_bytes_mod_order` 进 R1CS | **$n_2=q_1$** ✓ |
| E₂ 明文 $m$、随机数 $r$、私钥 $x$ | 在 $\mathbb{Z}_{q_2}$ | $\mathbb{Z}_{q_2}$ | `curveOrder`；`encrypt()` 标量乘 $G$ | **$q_2 \neq q_1$**（设计如此） |
| E₁ Montgomery 点坐标域 | $n_1$ | $\mathbb{F}_{n_1}$，$n_1=2^{255}-19$ | Spartan 内部；与 E₂ Weierstrass 模型不同 | 与 $n_2$ 不同 |

**易错点（曾导致文档/审查误判）：**

- 代码名 `curveOrder` ↔ 论文 **$q_2$**，**不是** 论文嵌入条件里的 **$n_2$**。
- 代码名 `curveBaseField` ↔ 论文 **$n_2$**（嵌入后 **= $q_1$**）。

**小整数范围：** 定点明文、部分权重满足 $m \ll q_2$ 且 $m \ll q_1$ 时，$\mathbb{Z}_{q_2}$ 与 $\mathbb{Z}_{q_1}$ 上的整数取值一致，但 **标量仍按 $q_2$ 做 ElGamal**，**坐标仍按 $\mathbb{F}_{q_1}$ 进 SNARK**——这是两层不同对象，不是「没嵌入」。

### 10.5 本仓库如何实现嵌入（后续编码应对齐的位置）

| 层次 | 实现 | 文件 |
|------|------|------|
| E₂ 参数 | `curveE2Info()` 与论文 ECB 参数一致 | `cnn_networks/Client.py` 等 |
| 坐标进 SNARK | 系数 `a` → 公开输入 `a_pd`；witness 中 `px,py` 用 `Scalar::from_bytes_mod_order` | `point_mult.rs`、`point_addition.rs` |
| 协议层复述 E₂ 常数 | `CurveE2Params::vpin_default()` | `cp-snark-full/src/curve.rs` |

**不属于曲线嵌入、但易一并误解的 cp-snark-full 增补：**

- 自定义 Pedersen/`digest` 承诺、RLC、$\gamma$ 等与 **式 (5) 消 mod $n_2$** 无关，见 `src/cp-snark-full/内部逻辑与论文忠实性审查报告.md` §二（承诺 `from_bytes_wide` vs witness `Scalar::from(u128)` 为 **另一 CLAIM**）。

### 10.6 与 AHE **同态计算量**的关系（为何说 AHE ≪ SNARK）

曲线嵌入 **不减少** 服务器在推理阶段执行的 Python 椭圆曲线运算次数；它减少的是 **证明阶段** 为「同态结果正确」而生成的 R1CS 规模。

| 侧 | 阶段 | 单次点加/点乘的代价（数量级） | 本仓库 network A |
|----|------|------------------------------|------------------|
| **E₂ AHE** | 同态推理（运行时） | 1 次真实 EC 点加 / 标量乘点 | EC 运算约 **2322** 次 |
| **E₁ SNARK** | 证明生成（离线/验证） | 点加 gadget **10** 约束；点乘 gadget **3464** 约束 | R1CS 合计约 **638k** 约束 |

**比例约 275 : 1**（见 §4.3 实测）：同态推理的 EC 成本相对 SNARK 证明可忽略；性能优化应优先看 **R1CS 条数**（gadget 设计、是否再引入 mod $n_2$ 电路、L2 MAC 等），而不是 AHE 的 `ecdsa` 调用次数。

**若错误去掉嵌入（假想）：** 在 SNARK 里用式 (5) 全量证明 mod $n_2$，点乘约束可飙到论文给出的 **$\sim 7.7\times 10^4$** 量级/次，整体证明将不可用——这是论文采用嵌入的 **工程理由**，而非可选优化。

### 10.7 小结（给后续编码的一句话）

> **Setup 选 E₂ 使 $n_2=q_1$，让 AHE 密文坐标的同态求值可以直接在 $\mathbb{Z}_{q_1}$ 上被 SNARK 证明，从而避免「证明 mod $n_2$」的巨型电路；AHE 标量仍在 $\mathbb{Z}_{q_2}$（`curveOrder`），与嵌入条件无关。**

---


## 十一、后续基准测试计划（待确认后实现）

> **暂不编写代码**；以下脚本已在 task2 / 本文档中预留，待人工确认后执行。

建议新增 `src/cp-snark-full/benches/cost_report.rs`（或 Python 驱动），输出：

1. **C, V, nnz**（从 `point_addition` / `point_mult` 直接读取）
2. **prove / verify 时间**（release 构建，≥3 次均值）
3. **proof 字节数**
4. **L1/L2 模拟**：仅统计增量约束公式，不实现完整电路

预期输出格式：

```text
network=A  |PtAdd|=2144  |PtMul|=178  C=638032  V=649125
prove_ms=...  verify_ms=...  proof_bytes=...
L1_delta_C=484  L2_compressed_delta_C=90064  L2_naive_delta_C=4190400
```

---

## 十二、改进优先级建议

> **编号说明：** 下表 **P0–P5** 为 **全项目路线图**（含 R1CS 增强 L1/L2/L3）。  
> `src/cp-snark-full/内部逻辑与论文忠实性审查报告.md` §七 使用同名 **P0–P3** 但范围更窄（仅协议层/工程项），**勿混读**——对照见 **§12.1**。

| 优先级 | 动作 | 计算量代价 | 语义收益 |
|--------|------|------------|----------|
| P0 | 统一 cp-snark-full 承诺与 witness 权重编码 | 无 | Pedersen 与 R1CS 权重一致（**非**曲线嵌入） |
| P1 | L1：完整 \|W\| 承诺 + 等式绑定 | **<0.1%** | cm 与 witness 对齐 |
| P2 | cm_x 绑定真实输入 \|x\| | **<0.1%** | 输入语义 |
| P3 | L2：FC 式 (10) 压缩 MAC 电路 | **~+15%** | 线性层可验证 |
| P4 | 式 (9) 卷积 γ + 验证方挑战 | **+5–15%** | soundness 对齐论文 |
| P5 | L3 端到端 + 前端/后端集成 | **×2–15** | 完整 vPIN |

### 12.1 与《内部逻辑与论文忠实性审查报告》的对照

| 审查报告问题（章节） | 本 doc §4.2 缺口 | 本 doc §十二 改进 | 审查报告 §七 | 关系说明 |
|----------------------|------------------|-------------------|--------------|----------|
| **§二 Scalar 双路径**（`from_bytes_wide` vs `from(u128)`） | （4） | **P0** | **P0** | **一一对应**；先做编码/字节测试，再谈 L1 绑定 |
| **§三.1** 非 CPS.Comm、`point_hex` 未打开 | （5）部分 | **P1**（L1 链外 Pedersen + §7.2 等式） | **P1** Pedersen 打开 | 本 doc P1 含「完整 \|W\|」+ 电路等式；审查 P1 强调 **点承诺可验证** |
| **§三.2** cm_W 仅 178 权重 | （1） | **P1** | — | 仅在本 doc 路线图体现 |
| **§三.3** cm_x 仅系数 a | （2） | **P2** | — | 仅在本 doc 路线图体现 |
| **§三.4** 验证方读本地 `weight.json` | （5） | **P5**（端到端独立验证） | **P1** 验证方独立 | 审查列为近期工程项；本 doc 归入 L3 |
| **§三.5** `e2_digest` 用 `curveOrder` | — | — | — | **未纳入**任一路线图；文档/辅助 digest，优先级低 |
| **§四.1** `gamma_add`/`gamma_mult` 未用 | （6）部分 | **P4**（式 (9) 真 γ） | **P2** 删除或接入 | 本 doc P4 = 论文 soundness；审查 P2 = 去掉假字段 |
| **§四.2** `rlc_binding_hex` 在 SNARK 外 | （6） | — | — | **未单独列改进**；若做 P4/P5 应重写或删除 RLC |
| **§五.1** cm 与 `vars_para` 无 R1CS 等式 | （3） | **P1**（§7.2 L1） | **P3** R1CS 绑定 | **强相关**：审查 P3 ≈ 本 doc P1 的电路部分 |
| **§五.2** `main.rs` 变量名误导 | — | — | **P2** | 仅审查报告；工程清理 |
| **§五.4** `run_protocol.py` 误标 n₂ | — | — | **P2** | 仅审查报告；文档准确性 |
| **§五.3** 计时不一致 | — | — | — | 仅审查报告；观测性 |
| **§五.5** L2/L4 跳过点乘 | — | — | — | **非问题**；与原仓库一致 |
| **§四.3** transcript 标签不同 | — | — | — | 预期行为；集成时统一入口即可 |

**建议实施顺序（合并两文档）：**

1. **P0（两文档一致）** — 编码路径 + 单元测试（审查 §二 = 本 doc §4.2（4））。  
2. **审查 P2 工程项** — 修正 `run_protocol.py` 符号打印、`gamma_*` 占位；可与 P0 同 PR。  
3. **审查 P1 + 本 doc P1** — Pedersen/`digest` 验证 + L1 等式（审查 §三.1、§五.1）。  
4. **本 doc P2 → P3 → P4 → P5** — 输入承诺、MAC 电路、论文 γ、端到端（审查报告未展开计算量）。

**已解决、勿重复立项：** 曲线嵌入（$n_2=q_1$）见 §4.1 第 5 条、§十；**不是** P0 所指问题。

**全项目排期（含 task2/3、平台 R0–R7）：** 见 [`docs/综合未来工作路线图.md`](综合未来工作路线图.md)。

---

## 十三、文档修订记录

| 日期 | 内容 |
|------|------|
| 2026-06-04 | 首版：自检结论 + 符号化计算量预估 + 实测基准（network A） |
| 2026-06-04 | §十二 §12.1 与审查报告对照；链至 `综合未来工作路线图.md` |

---

*本文档基于 `src/cp-snark-full` 源码、`vPIN论文与代码对照说明.md` 与 network A 实测数据；增强方案倍率为 R1CS 规模推导的预估值，精确 benchmark 待 §十一 代码实现后更新。*
