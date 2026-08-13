# 小参数 CNN 与大语言模型证明路线：数学论证与复杂度优化

> 目标：把小参数 CNN 与大语言模型的证明方案分开设计。  
> 结论：Network A 这类小参数 CNN 应采用 CP-SNARK / B′ 路线，做完整模型承诺与计算轨迹绑定；大语言模型不应照搬 Network A 的全量 CP-SNARK 电路，而应采用分层承诺、稀疏打开、选择性验证、递归/分段证明等路线优化证明时间复杂度。

**大语言模型完整研究稿**（本总览的 LLM 分支）：

- [大语言模型博弈论可验证推理-数学设计.md](./大语言模型博弈论可验证推理-数学设计.md) — 威胁模型、博弈均衡、协议草案
- [llm-verifiable-inference-cost-model.md](./llm-verifiable-inference-cost-model.md) — Llama 成本与 $G$
- [llm-ahe-verifiable-compute-analysis.md](./llm-ahe-verifiable-compute-analysis.md) — AHE/FHE 可行性
- [llm-sparse-merkle-opening-analysis.md](./llm-sparse-merkle-opening-analysis.md) — 稀疏 opening
- [llm-verification-scheme-matrix.md](./llm-verification-scheme-matrix.md) — 全方案矩阵
- [llm-verifiable-inference-literature-survey.md](./llm-verifiable-inference-literature-survey.md) — **领域文献调研（含本地 PDF）**

---

## 1. 两类对象必须分开

### 1.1 小参数 CNN

Network A 的模型规模：

$$
N_W = 1219
$$

证明轨迹规模：

$$
J_{\mathrm{PtMul}}=178,\qquad J_{\mathrm{PtAdd}}=2144
$$

该规模下，完整模型参数进入 CP-SNARK witness 是可接受的。模型绑定关系可以明确写为：

$$
\mathsf{cm}_W = \mathsf{CPS.Comm}(\mathbf W^*)
$$

并在关系中证明：

$$
a_j = \mathrm{Source}_j(\mathbf W^*, \gamma')
$$

再证明 EC 轨迹：

$$
Q_j = a_j P_j
$$

因此小 CNN 的数学闭包是：

$$
\boxed{
\mathsf{CPS.Ver}
\Rightarrow
\exists \mathbf W^*:
\mathsf{cm}_W=\mathsf{CPS.Comm}(\mathbf W^*)
\land
a_j=\mathrm{Source}_j(\mathbf W^*,\gamma')
\land
R_{\mathrm{EC}}=1
}
$$

### 1.2 大语言模型

大语言模型参数规模通常为：

$$
N_W \in [10^8,10^{11}]
$$

即使只考虑百万级简化模型：

$$
N_W \gtrsim 10^6
$$

若照搬小 CNN，把全部权重、全部层计算和全部激活都写进单个 R1CS，则证明规模接近：

$$
C_{\mathrm{full}}
=
\Theta(\text{forward FLOPs})
$$

对 Transformer，单层主要成本近似为：

$$
C_{\mathrm{layer}}
=
\Theta(Ld^2 + L^2d)
$$

其中：

- $L$：序列长度；
- $d$：hidden size；
- $Ld^2$：QKV/MLP 等矩阵乘；
- $L^2d$：attention。

若层数为 $n_{\ell}$：

$$
C_{\mathrm{LLM}}
=
\Theta(n_{\ell}(Ld^2+L^2d))
$$

这远超 Network A 的 $6.38\times10^5$ 级约束。

因此大模型不能简单采用“全量 CP-SNARK + 全量 R1CS 推理”。

---

## 2. 小参数 CNN：CP-SNARK 路线的数学闭包

### 2.1 承诺对象

对完整模型：

$$
\mathbf W^*
=
(\mathrm{conv},\mathrm{fc1},\mathrm{bias1},\mathrm{fc2},\mathrm{bias2})
$$

做 CP-SNARK 原生承诺：

$$
\mathsf{cm}_W
\leftarrow
\mathsf{CPS.Comm}(\mathbf W^*)
$$

证明中的 witness 包含：

$$
w=(\mathbf W^*, aux)
$$

其中 $aux$ 包含 EC 轨迹、PtMul/PtAdd 中间变量、层关系辅助变量。

### 2.2 模型到 PtMul 轨迹的绑定

对每个 PtMul：

$$
Q_j=a_jP_j
$$

必须证明：

$$
a_j=\mathrm{Source}_j(\mathbf W^*,\gamma')
$$

其中：

#### Conv

$$
a_{j_{\mathrm{conv}}(\beta,s)}=\mathbf W^*_s
$$

#### FC1

$$
a_{j_{\mathrm{fc1}}(\beta,p)}
=
\sum_{i=0}^{15}(\gamma')^i
\mathbf W^*_{9+p\cdot16+i}
$$

#### FC2

$$
a_{j_{\mathrm{fc2}}(\beta,p)}
=
\sum_{i=0}^{9}(\gamma')^i
\mathbf W^*_{1049+p\cdot10+i}
$$

这些都是线性约束，额外 R1CS 约束数约为：

$$
\Delta C_{\mathrm{bind}}
=
18+128+32
=
178
$$

相对当前：

$$
C_0=638032
$$

比例为：

$$
\frac{178}{638032}
\approx
0.028\%
$$

所以小 CNN 中，**模型到 PtMul 乘数的绑定不是证明时间瓶颈**。

### 2.3 小 CNN 的主要瓶颈

小 CNN 的瓶颈仍是 EC gadget：

$$
C_{\mathrm{EC}}
=
J_{\mathrm{PtMul}}\cdot C_{\mathrm{PtMul}}
+
J_{\mathrm{PtAdd}}\cdot C_{\mathrm{PtAdd}}
$$

当前：

$$
C_{\mathrm{PtMul}}=3464,\qquad
C_{\mathrm{PtAdd}}=10
$$

因此：

$$
C_{\mathrm{EC}}
=
178\cdot3464+2144\cdot10
=
638032
$$

这说明优化方向应优先围绕：

1. 减少 PtMul 数量；
2. 压缩 PtMul gadget；
3. 并行/批处理 Spartan proof；
4. 避免把 AHE 朴素轨迹 $18560$ PtMul 放进 SNARK。

### 2.4 小 CNN 的推荐证明路线

小 CNN 应采用：

```text
CPS.Comm(W*)
  + L1: W* -> a_j
  + EC SNARK: Q_j = a_j P_j
  + M1/M5: Eq(9)(7)(10)
```

数学上最干净的目标是：

$$
\boxed{
\mathsf{CPS.Ver}(\pi,\mathsf{cm}_W,\mathsf{cm}_{aux},x)=1
}
$$

验证结论：

$$
\exists \mathbf W^*, aux:
\mathsf{cm}_W=\mathsf{CPS.Comm}(\mathbf W^*)
\land
\phi(\mathbf W^*,aux,x)=1
$$

---

## 3. 大语言模型：为什么不能照搬小 CNN

### 3.1 全量证明复杂度不可接受

如果对大模型全量矩阵乘做普通 R1CS：

$$
y = Wx
$$

其中：

$$
W\in\mathbb F^{m\times n}
$$

naive 乘加约束为：

$$
C_{\mathrm{matmul}}
=
\Theta(mn)
$$

Transformer 中每层有多个大矩阵：

$$
W_Q,W_K,W_V,W_O,W_1,W_2
$$

若 hidden size 为 $d$，MLP expansion 为 $4d$，则每 token 每层矩阵计算量约为：

$$
\Theta(d^2 + d^2 + d^2 + d^2 + 4d^2 + 4d^2)
=
\Theta(12d^2)
$$

对 $L$ 个 token：

$$
\Theta(12Ld^2)
$$

attention 还含：

$$
\Theta(L^2d)
$$

因此：

$$
C_{\mathrm{LLM}}
=
\Theta(n_{\ell}(Ld^2+L^2d))
$$

该规模远大于小 CNN 的 paper proof EC 轨迹。

### 3.2 大模型的承诺也不能全量进电路

若用 Merkle 承诺完整模型：

$$
R_W=\mathrm{MerkleRoot}(\mathbf W^*)
$$

并在电路中打开 $k_w$ 个权重，则：

$$
\Delta C_{\mathrm{Merkle}}
=
k_w\log_2(N_W)C_H
$$

其中 $C_H$ 是哈希 gadget 成本。Poseidon 约：

$$
C_H\approx 200\sim400
$$

如果大模型一次推理实际使用大量矩阵权重，则：

$$
k_w\approx N_W
$$

此时：

$$
\Delta C_{\mathrm{Merkle}}
=
\Theta(N_W\log N_W)
$$

不可接受。

所以大模型不能把“每个被用权重都在电路中打开”作为主路线，除非证明的是稀疏子模型、MoE top-k 路由或局部层。

---

## 4. 大模型应采用的分离设计

### 4.1 模型承诺层

大模型可以用：

$$
R_W=\mathrm{MerkleRoot}(\mathbf W^*)
$$

或张量承诺 / 向量承诺：

$$
\mathsf{cm}_W=\mathsf{VC.Commit}(\mathbf W^*)
$$

该承诺用于 catalog 绑定：

$$
model\_id\mapsto(\mathsf{cm}_W,\tau,\mathrm{manifest})
$$

### 4.2 推理证明层

不做全量证明，而是按业务选择以下路线之一：

#### 路线 A：选择性层证明

只证明部分层或部分 checkpoint：

$$
h_{t+1}=F_{\ell}(h_t,W_{\ell})
$$

验证者只检查抽中的层集合：

$$
\mathcal S\subseteq\{1,\ldots,n_{\ell}\}
$$

证明成本：

$$
C_{\mathrm{selective}}
=
\sum_{\ell\in\mathcal S} C_{\ell}
$$

若 $|\mathcal S|\ll n_{\ell}$，则：

$$
C_{\mathrm{selective}}\ll C_{\mathrm{full}}
$$

这是统计审计，不是完整推理硬证明。

#### 路线 B：分段递归证明

把模型分为块：

$$
F=F_T\circ F_{T-1}\circ\cdots\circ F_1
$$

每块证明：

$$
\pi_t:\quad h_t=F_t(h_{t-1},W_t)
$$

再递归聚合：

$$
\Pi=\mathsf{RecursiveVerify}(\pi_1,\ldots,\pi_T)
$$

单块证明时间降低，最终验证时间可压缩为：

$$
T_{\mathrm{verify}}=O(\log T)
\quad\text{或}\quad
O(1)
$$

但总 prover 工作量仍约等于各块之和：

$$
T_{\mathrm{prove}}=\sum_t T_t + T_{\mathrm{recursion}}
$$

适合并行化与工程分布式证明。

#### 路线 C：承诺中间激活 + 随机检查

对中间激活承诺：

$$
\mathsf{cm}_{h_t}=\mathsf{Com}(h_t)
$$

验证随机层或随机坐标：

$$
h_{t+1}[i]\stackrel{?}{=}
F_t(h_t,W_t)[i]
$$

成本从全量：

$$
\Theta(\dim(h_t)\dim(W_t))
$$

降到抽样规模：

$$
\Theta(k)
$$

但安全性变为概率型：

$$
p_{\mathrm{catch}}
=
1-\frac{\binom{N-t}{k}}{\binom{N}{k}}
$$

其中 $t$ 是错误坐标数，$k$ 是抽样数。

#### 路线 D：专用 zkML / lookup / GKR / sumcheck

对大矩阵乘，使用 sumcheck / GKR 类协议可把证明结构改为多线性扩展检查。

典型矩阵乘：

$$
y_i=\sum_j W_{i,j}x_j
$$

可通过 sumcheck 把全量逐项乘加压缩为对多项式的随机点评估。

证明复杂度通常接近：

$$
T_{\mathrm{prove}}=\tilde O(\mathrm{nnz}(W))
$$

验证复杂度：

$$
T_{\mathrm{verify}}=\mathrm{polylog}(|W|)
$$

但这要求新的证明后端，不应强行塞进当前 EC-gadget Spartan 路线。

---

## 5. 证明时间复杂度优化原则

### 5.1 小 CNN 的优化目标

小 CNN 的证明复杂度：

$$
C_{\mathrm{CNN}}
=
178\cdot3464+2144\cdot10+\Delta C_{\mathrm{bind}}+\Delta C_{\mathrm{M5}}
$$

其中：

$$
\Delta C_{\mathrm{bind}}\approx178
$$

所以：

$$
C_{\mathrm{CNN}}\approx6.38\times10^5+\Delta C_{\mathrm{M5}}
$$

优化重点：

1. 保持 paper proof，不使用 AHE 朴素轨迹；
2. 把模型绑定写成线性约束，不做 Merkle in-circuit；
3. M5 只编码压缩后的式 (9)(7)(10)，不编码所有 MAC；
4. 复用 Spartan PC / CP-SNARK，避免电路内重算承诺。

### 5.2 大模型的优化目标

大模型的证明复杂度不能以 $N_W$ 或 forward FLOPs 全量增长。

目标应是：

$$
T_{\mathrm{prove}}
\approx
O(k_{\mathrm{verified}}\cdot \mathrm{polylog}(N_W))
$$

或：

$$
T_{\mathrm{prove}}
\approx
\tilde O(\mathrm{verified\_subgraph})
$$

其中 $k_{\mathrm{verified}}$ 是被验证的权重、坐标、层或块的规模。

必须避免：

$$
T_{\mathrm{prove}}=\Theta(N_W)
$$

作为每次推理成本。

Setup 阶段可以接受一次性：

$$
T_{\mathrm{setup}}=O(N_W)
$$

例如建 Merkle 树或生成张量承诺。

---

## 6. 推荐最终分工

### 6.1 小参数 CNN

采用：

```text
CP-SNARK / B′
  + CPS.Comm(W*)
  + W* -> a_j 线性绑定
  + EC gadget
  + 式 (9)(7)(10) 压缩层证明
```

性质：

$$
\text{硬绑定，完整验证，适合小模型。}
$$

### 6.2 大语言模型

采用独立路线：

```text
Model commitment / tensor commitment
  + 分层或稀疏 opening
  + 激活承诺
  + 随机审计或递归分段证明
  + 专用 zkML backend
```

性质：

$$
\text{可扩展，概率或分段安全，避免全量 R1CS。}
$$

### 6.3 不推荐混用

不要把小 CNN 的：

```text
178 PtMul + EC gadget + full W* binding
```

直接外推到 LLM。

也不要把大模型的随机抽查安全声称套回小 CNN，因为小 CNN 完全可以做硬绑定。

---

## 7. 一句话定案

$$
\boxed{
\text{小参数 CNN：用 CP-SNARK 做硬绑定；}
\quad
\text{大语言模型：另设分层/承诺/抽样/递归证明路线。}
}
$$

小 CNN 追求：

$$
\mathsf{cm}_W \Rightarrow \mathbf W^* \Rightarrow a_j \Rightarrow EC\ trace
$$

大模型追求：

$$
O(N_W)\ \text{一次性 Setup}
\quad+\quad
O(k\log N_W)\ \text{或子图级 Prove}
$$

而不是每次推理都证明全模型全计算。

