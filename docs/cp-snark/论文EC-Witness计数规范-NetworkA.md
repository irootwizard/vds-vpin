# 论文 EC Witness 计数规范（Network A · model_training 标准）

> **权威来源（按优先级）：**  
> 1. **本文 PDF：** [`Documents/2024-Privacy-Preserving Verifiable Neural Network Inference Service.pdf`](../../Documents/2024-Privacy-Preserving%20Verifiable%20Neural%20Network%20Inference%20Service.pdf)（arXiv:2411.07468v2）  
>    - **§IV-B.4** Inference + Proving（式 (6)–(10)、Fig.7）  
>    - **§V** Complexity + **Table I**  
>    - **§VI-B** Network A 参数（3×3 conv、4×4 pool、FC 64→16→10）  
> 2. `topology.NETWORK_A` + `model_training/outputs/20260622_184254`  
>  
> **非权威：** ACSAC Artifact Documentation（仅实验流程）、`Server.py` `rLCR`、`engine.py` 硬编码。

---

## 1. 计数对象是什么

论文证明的是 **CP-SNARK 电路中要证的 EC gadget 次数**（PtMul / PtAdd），不是 AHE 同态推理里每一次 naive MAC。

| 模式 | 含义 | 论文依据 |
|------|------|----------|
| **`paper_proof`** | 式 (9)(10) RLC 压缩后的 **证明轨迹** | §IV-B Proving Conv/Pool/FC；Table I |
| **`ahe_homomorphic`** | 同态推理实际执行的 MAC（无 RLC） | 式 (6)(7)(8)；**不**等于证明 witness 数 |

客户端 verify 的 SNARK 应跟 **`paper_proof`** 对齐。

---

## 2. 论文 Table I 与 ElGamal 双分量（实现因子 $B$）

论文 **Table I / §V** 按**单层、单次** RLC 压缩后的 gadget 计数（式 (9)(10) 之后）：

| 层 | Table I #PtMul | Table I #PtAdd |
|----|----------------|----------------|
| Conv | $k^2$ | $k^2-1$ |
| Avg Pool | $0$ | $(\hat{k}^2-1)\cdot n_{\mathrm{pool\_cells}}$（见 §3.2） |
| FC（每层） | $g$ | $(g-1)+h$ |

指数 ElGamal（Appendix Fig.4）密文为 **$(c_1, c_2)$ 双分量**；同态推理与 witness 导出对 **每个分量各跑一遍** MAC/证明链。

| 量 | 论文 Table I（单分量） | 本仓库 Network A 实现（$B=2$） |
|----|----------------------|--------------------------------|
| PtMul 合计 | $k^2+g_1+g_2 = 9+64+16 = 89$ | $B \times 89 = \mathbf{178}$ |
| PtAdd 合计 | 见 §3 各层相加 | $B \times (\cdots) = \mathbf{2144}$ |

**结论：** `178` / `2144` 是 **Table I × ElGamal 双分量**，不是论文表格里直接写出的数字；编码时须显式参数 `elgamal_branches=2`（Fig.4 的 $c_1,c_2$）。

---

## 3. 符号与网格（§IV + §VI）

| 符号 | 含义 | Network A（32×32 输入） |
|------|------|-------------------------|
| $n, m$ | 客户端样本高/宽 | $n=m=32$（MNIST resize，见论文 §VI） |
| $k$ | 卷积核边长 | $k=3$ |
| $\hat{s}$ | 卷积 stride | $\hat{s}=1$ |
| $\hat{k}$ | 池化窗口边长 | $\hat{k}=4$（论文池化式 (7) 的 $k$） |
| $n', m'$ | 卷积输出格点数 | 含 padding 时 $32\times32$；纯论文式无 pad 时为 $30\times30$ |
| $g, h$ | FC 输入/输出维 | FC1: $g=64,h=16$；FC2: $g=16,h=10$ |
| $\llbracket\cdot\rrbracket_2$ | ElGamal 密文（双分量 $c_1,c_2$） | 实现中 **分支数 $B=2$** |

**实现注：** model_training / `topology.NETWORK_A` 卷积 **padding=1**，故

$$
n'_{\mathrm{eff}} = \frac{n + 2p - k}{\hat{s}} + 1 = 32 \quad (p=1,\ k=3,\ \hat{s}=1)
$$

池化输出边长（stride = $\hat{k}$）：

$$
n'' = \frac{n'_{\mathrm{eff}} - \hat{k}}{\hat{k}} + 1 = 8,\quad N_{\mathrm{pool}} = n''^2 = 64
$$

---

## 4. 各层 witness 计数（论文 Table I + §IV-B.4）

记 $B$ = ElGamal 分支数（Network A 实现 $B=2$）。

### 4.1 卷积 — 式 (9)

论文：由 $O(n^2 k^2)$ 降为 **$O(k^2)$** 次 PtMul / PtAdd（$\hat{s}$ 为常数）。

| 量 | 单分支 | $B$ 分支合计 |
|----|--------|--------------|
| **PtMul** | $k^2$ | $B \cdot k^2 = 2 \times 9 = 18$ |
| **PtAdd** | $k^2 - 1$ | $B \cdot (k^2 - 1) = 16$ |

**与输入窗数 $n'm'$ 无关**（论文 Figure 3：证明时间随输入尺寸不变）。

对应关系式 (9) 左/右 RLC 后的 EC 链，**不是**逐格 MAC 的 $n'm'k^2$ 次。

### 4.2 平均池化 — 式 (7)

论文：仅 PtAdd 证窗口内求和；公开因子 $1/\hat{k}^2$ **不进 RLC**（与式 (7) 一致）。

| 量 | 公式 | Network A |
|----|------|-----------|
| **PtMul** | $0$ | $0$ |
| **PtAdd** | $B \cdot (\hat{k}^2 - 1) \cdot N_{\mathrm{pool}}$ | $2 \times 15 \times 64 = 1920$ |

论文 §V 渐近式 $(\hat{k}^2-1)(((n-k)/\hat{s})+1)^2/\hat{k}^2$ 在 $n'=n'_{\mathrm{eff}}$、池化 stride=$\hat{k}$ 时等价于上式。

**AHE 同态路径**另有一次 $1/\hat{k}^2$ 标量乘/池化格 → 计入 `ahe_homomorphic`，**不计入** `paper_proof` PtMul。

### 4.3 全连接 — 式 (10)

每层 FC（输入维 $g$，输出维 $h$）：

| 量 | 单分支 | $B$ 分支 |
|----|--------|----------|
| **PtMul** | $g$ | $B \cdot g$ |
| **PtAdd** | $(g-1) + h$ | $B \cdot ((g-1)+h)$ |

Network A 两层：

| 层 | $g$ | $h$ | PtMul | PtAdd |
|----|-----|-----|-------|-------|
| FC1 | 64 | 16 | 128 | 158 |
| FC2 | 16 | 10 | 32 | 50 |

式 (10) 右端含 bias 项 $\sum_j \gamma'^j b[j]$；bias 的 **PtAdd** 计入 $(g-1)+h$ 中的 $h$ 项（论文 §IV-B FC proving 段）。

### 4.4 总计（Network A · `paper_proof` · $B=2$）

$$
\begin{aligned}
J_{\mathrm{PtMul}} &= B(k^2 + g_1 + g_2) = 2(9+64+16) = \mathbf{178} \\
J_{\mathrm{PtAdd}} &= B\bigl[(k^2-1) + (\hat{k}^2-1)N_{\mathrm{pool}} + (g_1-1+h_1) + (g_2-1+h_2)\bigr] \\
&= 2\bigl[8 + 960 + 79 + 25\bigr] = \mathbf{2144}
\end{aligned}
$$

与 legacy `rust_files/A` 实测一致，但数字来源是 **论文 Table I**，不是 `Server.py` 循环。

---

## 5. 全局 PtMul 层区间（Network A · $B=2$）

| 层 | $j$ 区间 | 长度 |
|----|----------|------|
| conv | $[0, 18)$ | 18 |
| pool | $[18, 18)$ | 0 |
| fc1 | $[18, 146)$ | 128 |
| fc2 | $[146, 178)$ | 32 |

---

## 6. 与 `ahe_homomorphic` 的对比

同态推理 naive MAC（式 (6)(7)(8)，**无** RLC）：

| 层 | PtMul | PtAdd |
|----|-------|-------|
| conv | $B \cdot n'_{\mathrm{eff}} m'_{\mathrm{eff}} k^2 = 18432$ | $B \cdot n' m' (k^2-1) = 16384$ |
| pool | $B \cdot N_{\mathrm{pool}} = 128$ | $B \cdot (\hat{k}^2-1) N_{\mathrm{pool}} = 1920$ |
| fc1 | $B \cdot g_1 h_1 = 2048$ | $B \cdot g_1 h_1 = 2048$ |
| fc2 | $B \cdot g_2 h_2 = 320$ | $B \cdot g_2 h_2 = 320$ |
| **合计** | **20928** | **20672** |

其中 conv+pool PtMul = **18560**（与 AHE 计数计划文档一致）。

---

## 7. 论文未闭合、实现须决策的点

| 编号 | 问题 | 状态 |
|------|------|------|
| O1 | 卷积 padding：Fig.3 实验用 pad=1；式 (6) 中 $n'=((n-k)/\hat{s})+1$ **不含** padding → 用 $n'_{\mathrm{eff}}$ | topology 显式 |
| O2 | Table I 为单分量计数；178 = $B\times$ Table I（Fig.4 ElGamal） | 本文 §2 |
| O3 | 式 (10) 显示式未写 bias；Fig.7 lines 29–31 单独 Enc+PtAdd | FC add 含 $h$ |
| O4 | Fig.7 line 33：$\phi_{cnv},\phi_{pl},\phi_{fc}$ 合并证明 + `CPS.Comm(aux)` | M5 按层 π 须对齐 |

---

## 8. 代码落点

| 模块 | 作用 |
|------|------|
| `model_training/network_a/ec_witness_schedule.py` | `derive_paper_proof_schedule()` 实现 §4 公式 |
| `model_training/.../proof_artifacts/ec_witness_schedule.json` | 导出计数 + 层区间 |
| `EcWitnessMode.PAPER_PROOF` | 证明 witness（178 / 2144） |
| `EcWitnessMode.AHE_HOMOMORPHIC` | 同态 naive 计数（对照用） |

**禁止**在 `PAPER_PROOF` 路径引用 `Server.py` / `rLCR` 模拟器。

---

## 9. 参考文献

- Riasi, Guajardo, Hoang, *Privacy-Preserving Verifiable Neural Network Inference Service*, arXiv:2411.07468v2, Nov 2024. 本地 PDF：`Documents/2024-Privacy-Preserving Verifiable Neural Network Inference Service.pdf`
