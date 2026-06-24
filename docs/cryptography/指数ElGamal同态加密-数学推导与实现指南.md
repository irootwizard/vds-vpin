# 指数 ElGamal 同态加密：数学推导与实现指南

> 本文档按「思路 → 定义 → 算法 → 证明 → 实现」组织，与 vPIN 仓库中 **椭圆曲线指数 ElGamal（Exponential ElGamal）** 实现一致。  
> **公式约定**：行内用 `$...$`，独立公式用 `$$...$$`。  
> **表格注意**：单元格内勿写 `$|m|$` 这类含竖线 `|` 的公式（会被当成列分隔符）；绝对值请用 `$\lvert m \rvert$`。  
> 对照代码：`src/cnn_networks/Client.py`、`src/LeNet/Client.py`、`src/Pre_computed_table/baby-step-giant-step.py`。

---

## 目录

1. [整体思路](#1-整体思路)
2. [符号与预备知识](#2-符号与预备知识)
3. [密钥生成](#3-密钥生成)
4. [加密](#4-加密)
5. [解密](#5-解密)
6. [解密正确性证明](#6-解密正确性证明)
7. [加法同态与标量同态](#7-加法同态与标量同态)
8. [明文空间、离散对数与 BSGS](#8-明文空间离散对数与-bsgs)
9. [安全性要点](#9-安全性要点)
10. [与经典 ElGamal 的对比](#10-与经典-elgamal-的对比)
11. [vPIN 代码实现清单](#11-vpin-代码实现清单)
12. [附录：证明依赖关系图](#12-附录证明依赖关系图)

---

## 1. 整体思路

### 1.1 要解决什么问题

在**不暴露明文**的前提下，让服务器对密文做**线性运算**（加、与公开小整数相乘），客户端持有私钥完成非线性层（ReLU、截断）。

指数 ElGamal 在椭圆曲线群上提供 **加法同态**（对明文整数在 $\mathbb{Z}_q$ 中模加）：

| 明文运算 | 密文运算（椭圆曲线点） |
|---------|------------------------|
| $m_1 + m_2$ | $(c_1^{(1)}, c_2^{(1)}) \oplus (c_1^{(2)}, c_2^{(2)})$：分量分别做点加 |
| $k \cdot m$（$k$ 公开） | $(k \cdot c_1,\; k \cdot c_2)$：标量乘点 |

**不**提供两密文相乘对应明文相乘（需 FHE 等）。

### 1.2 核心构造（一句话）

在素数阶子群 $\langle G \rangle \subset E(\mathbb{F}_{n_2})$ 上，明文 $m \in \mathbb{Z}_{q_2}$ 编码为指数：

$$
c_1 = rG,\quad c_2 = mG + rH,\quad H = xG
$$

- $r$：每次加密随机（语义安全）
- $x$：私钥，**全阶**随机（约 252 bit，本仓库 `curveOrder` = 论文 $q_2$）
- $m$：**小整数**（定点编码，约 $\lesssim 2^{35}$ bit），解密第二步用 BSGS 求离散对数

### 1.3 实现主流程（vPIN）

```
KeyGen → (G, H, x),  H = xG
Enc(pk, m) → (c1, c2)
Dec(sk, c1, c2):
    β ← c2 - x·c1 = mG          // 代数步，O(1) 次点运算
    m ← ECDLP_G(β)              // BSGS + 预计算表
HomAdd: (c1,c2) ⊕ (c1',c2')     // 点加
HomScalar(k, (c1,c2)) = (k·c1, k·c2)
```

---

## 2. 符号与预备知识

### 2.1 椭圆曲线群

设 $E/\mathbb{F}_p$ 为 Weierstrass 曲线，$G \in E(\mathbb{F}_p)$ 为基点，**阶**为素数 $q$：

$$
q = \#\langle G \rangle
$$

记群运算为 **加法** $\oplus$（代码里 `+`），标量乘 $k \cdot P = \underbrace{P + \cdots + P}_{k\text{ 次}}$（代码里 `k * P`）。

| 符号 | 论文 | vPIN 代码 | 含义 |
|------|------|-----------|------|
| $n_1$ | E₁ 基域 | （Spartan 点坐标域） | $2^{255}-19$ |
| $q_1$ | E₁ 阶 / SNARK 标量域 | Ristretto `Scalar` | $2^{252}+277423\ldots989$ |
| $n_2$ | E₂ **基域** | **`curveBaseField`** | **= $q_1$**（曲线嵌入） |
| $q_2$ | E₂ **群阶** | **`curveOrder`** | $2^{252}-124614\ldots947$ |
| $G$ | 生成元 | `curveGenerator` | |
| $H$ | 公钥 $xG$ | `h` | |
| $x$ | 私钥 | `randomValueX` | $\in \mathbb{Z}_{q_2}$ |

**易混点：** 代码变量名 `curveBaseField` 常被口头叫作「基域 $p$」，其数值等于论文 **$n_2$** 与 **$q_1$**，**不等于** `curveOrder`（论文 **$q_2$**）。AHE 明文/标量 $m,r,x$ 在 $\mathbb{Z}_{q_2}$（`curveOrder`）；点坐标 $(x,y)$ 在 $\mathbb{F}_{n_2}=\mathbb{F}_{q_1}$（`curveBaseField`）。

### 2.2 明文与密文空间

- **明文**：$m \in \mathbb{Z}_{q_2}$（代码 `curveOrder`）。实现中 $m$ 为定点整数，且协议要求 $\lvert m \rvert$ 远小于 $q_2$（约 $\lesssim 2^{35}$）。
- **密文**：有序对 $(c_1, c_2) \in \langle G \rangle \times \langle G \rangle$，两个椭圆曲线点。

### 2.3 离散对数问题（ECDLP）

**定义（ECDLP）**：给定 $G$ 与 $P = mG$，在 $m \in \{0,\ldots,q-1\}$ 中求 $m$。

- **困难版本**：$m$ 均匀取自全 $\mathbb{Z}_q$（$q \sim 2^{252}$）→ 认为多项式时间不可解。
- **vPIN 使用的简单版本**：$m$ 已知落在区间 $[0, M]$，$M \ll q$（如 $M \sim 2^{35}$）→ 可用 **Baby-step Giant-step（BSGS）** 在 $O(\sqrt{M})$ 时间与空间内求解。

### 2.4 与「私钥空间 / 明文空间」的关系

| 对象 | 典型大小 | 解密方式 |
|------|----------|----------|
| 私钥 $x$ | $\approx q$，~252 bit | 不通过 BSGS 恢复；依赖全群 ECDLP 困难 |
| 明文 $m$ | $\ll q$，~35 bit（协议控制） | 代数步得 $mG$ 后 **BSGS** |

**预计算表**只加速 **小 $m$** 的 ECDLP，**不能**替代大 $x$ 的搜索（见第 8、9 节）。

### 2.5 与 CP-SNARK 的曲线嵌入（论文 Setup）

论文（§IV-B、附录 Setup）选取 E₂ 使 **基域 $n_2 = E_1$ 的群阶 $q_1$**，ECB 生成参数写入 `curveE2Info()`。本仓库 **已实现**：

- `curveBaseField` = $q_1$ = $2^{252}+27742317777372353535851937790883648493$
- `curveOrder` = $q_2$ = $2^{252}-124614587218531604318505012771651942947$
- R1CS：`point_mult.rs` 中 `a_pd` / `px` / `py` 经 `from_bytes_mod_order` 进入 $\mathbb{Z}_{q_1}$

详见 `vPIN论文与代码对照说明.md` §二引用块。

---

## 3. 密钥生成

### 3.1 算法 KeyGen

**公开参数**：曲线 $E$、$G$、$q$（所有参与方已知）。

**步骤**：

1. 随机选取 $x \leftarrow \{1, 2, \ldots, q-2\}$（代码：`random.randrange(1, curveOrder-1)`）
2. 计算 $H = x \cdot G$
3. **公钥** $\mathsf{pk} = (G, H)$
4. **私钥** $\mathsf{sk} = x$

### 3.2 私钥长度

$q$ 为 252 bit 量级时，$x$ 的取值空间约为 $2^{252}$，**不是** 35 bit。35 bit 约束针对 **明文 $m$**，与 $x$ 无关。

### 3.3 实现伪代码

```python
def keyGen():
    G = curveGenerator
    q = curveOrder
    x = random.randrange(1, q - 1)
    H = x * G
    return pk=(G, H), sk=x
```

---

## 4. 加密

### 4.1 算法 Enc($\mathsf{pk}, m$)

**输入**：

- 公钥 $(G, H)$
- 明文 $m \in \mathbb{Z}_q$（实现中 `int` 定点值）

**步骤**：

1. 随机 $r \leftarrow \{1, \ldots, q-2\}$
2. $c_1 = r \cdot G$
3. $c_2 = m \cdot G + r \cdot H$

**输出**：密文 $C = (c_1, c_2)$。

### 4.2 与代码对应

```python
# src/cnn_networks/Client.py :: encrypt
c1 = randomValueR * curveGenerator      # rG
c2 = message * curveGenerator + randomValueR * h   # mG + rH
```

### 4.3 加密直觉

把 $c_2$ 展开：

$$
c_2 = mG + r(xG) = (m + rx)G \quad\text{（在群中形式上可这样记，实际实现是 } mG + rH\text{）}
$$

随机 $r$ 使 $(c_1, c_2)$ 对同一 $m$ 分布均匀于大量密文对（语义安全，见第 9 节）。

---

## 5. 解密

解密分 **两步**：先利用私钥消随机性，再解离散对数。

### 5.1 步骤一：代数消元（得 $mG$）

已知 $c_1 = rG$，$c_2 = mG + rH$，$H = xG$：

$$
\beta = c_2 - x \cdot c_1 = mG + rH - x(rG) = mG + r(xG) - xrG = mG
$$

**代码**（`decrypt_c1_c2`）：

```python
s = randomValueX * encrypted_trained_c1[i][j]
output = encrypted_trained_c2[i][j] + ((-1) * s)   # β = c2 - x·c1
```

同时计算 $-c_1, -c_2$ 的对应组合，以处理 $m$ 可能为负（二补 / 符号歧义）的情形，再交给 BSGS。

### 5.2 步骤二：ECDLP（求 $m$）

求唯一 $m \in \mathbb{Z}_q$（在协议限定的小范围内）使得：

$$
\beta = m \cdot G
$$

**实现**：Baby-step Giant-step + 预计算表 `table.pickle`（`giant_step`）。

### 5.3 完整解密算法 Dec($\mathsf{sk}, c_1, c_2$)

1. $\beta \leftarrow c_2 - x c_1$
2. $m \leftarrow \mathrm{BSGS}(G, \beta, M_{\max})$，其中 $M_{\max}$ 为协议明文上界
3. 输出 $m$

若 $m$ 超出 BSGS 预计算范围，第 2 步失败或返回错误值。

---

## 6. 解密正确性证明

### 6.1 引理 1（代数步）

**引理 1**：对任意 $m, r \in \mathbb{Z}_q$，$x \in \mathbb{Z}_q$，令 $c_1 = rG$，$c_2 = mG + rH$，$H = xG$。则

$$
c_2 - x \cdot c_1 = mG
$$

**证明**：

$$
\begin{aligned}
c_2 - x c_1 &= (mG + rH) - x(rG) \\
&= mG + r(xG) - xrG \\
&= mG + rxG - rxG \\
&= mG
\end{aligned}
$$

（群运算满足分配律：$rH = r(xG) = (rx)G = x(rG)$。） ∎

### 6.2 引理 2（ECDLP 步）

**引理 2**：若 $\beta = mG$，且 $m \in \{0,1,\ldots,M\}$，BSGS 在参数 $m_{\mathrm{bs}} \ge \lceil\sqrt{M}\rceil$ 下可恢复 $m$。

**证明（概要）**：

BSGS 预计算 $T = \{ jG : 0 \le j < m_{\mathrm{bs}} \}$。写 $m = i \cdot m_{\mathrm{bs}} + j$，对 $i = 0,\ldots,m_{\mathrm{bs}}-1$ 检查 $\beta - i \cdot m_{\mathrm{bs}} \cdot G$ 是否落在 $T$ 中。  
当 $m \le M$ 且 $m_{\mathrm{bs}} \ge \lceil\sqrt{M}\rceil$ 时，必存在这样的 $(i,j)$。 ∎

本仓库取 $m_{\mathrm{bs}} = 3{,}200{,}000$，可覆盖 $|m| \lesssim m_{\mathrm{bs}}^2 \sim 10^{13}$ 量级。

### 6.3 定理（解密正确性）

**定理**：若 $m \in \mathbb{Z}_q$ 落在 BSGS 可解范围内，且 Enc、Dec 按第 4、5 节定义，则

$$
\mathrm{Dec}(\mathrm{Enc}(m)) = m
$$

**证明**：

1. 设 $\mathrm{Enc}(m) = (c_1, c_2)$，随机数为 $r$。
2. 由引理 1，$\beta = c_2 - x c_1 = mG$。
3. 由引理 2，$\mathrm{BSGS}(G, \beta) = m$。
4. 故 $\mathrm{Dec}(c_1, c_2) = m$。 ∎

---

## 7. 加法同态与标量同态

### 7.1 密文加法（同态加）

定义密文加法为分量点加：

$$
(c_1, c_2) \oplus (c_1', c_2') = (c_1 + c_1',\; c_2 + c_2')
$$

（代码中椭圆曲线点 `+`。）

**定理（加法同态）**：设 $C_i = \mathrm{Enc}(m_i)$，$i=1,2$，则

$$
\mathrm{Dec}(C_1 \oplus C_2) = m_1 + m_2 \pmod{q}
$$

**证明**：

设 $C_i = (r_i G,\; m_i G + r_i H)$。则

$$
\begin{aligned}
C_1 \oplus C_2 &= (r_1 G + r_2 G,\; m_1 G + r_1 H + m_2 G + r_2 H) \\
&= ((r_1+r_2)G,\; (m_1+m_2)G + (r_1+r_2)H)
\end{aligned}
$$

这正是随机数 $r_1+r_2$、明文 $m_1+m_2$ 的有效密文。代数步：

$$
(c_2 + c_2') - x(c_1 + c_1') = (m_1+m_2)G
$$

ECDLP 步恢复 $m_1+m_2 \pmod q$。 ∎

### 7.2 标量乘法（同态数乘）

对公开整数 $k \in \mathbb{Z}$，定义：

$$
k \odot (c_1, c_2) = (k \cdot c_1,\; k \cdot c_2)
$$

**定理（标量同态）**：

$$
\mathrm{Dec}(k \odot \mathrm{Enc}(m)) = k \cdot m \pmod{q}
$$

**证明**：

$k \cdot (rG) = (kr)G$，$k \cdot (mG + rH) = kmG + krH$，即 $\mathrm{Enc}(km)$ 的随机数为 $kr$。  
代数步得 $\beta = kmG$，BSGS 得 $km \pmod q$。 ∎

### 7.3 卷积 / 全连接中的用法（vPIN）

- **密文 + 密文**：池化窗口内多点相加。
- **整数权重 $\times$ 密文点**：`filter_weights[ii,jj] * ciphertext_point`。
- **不支持**：密文 $\times$ 密文（非线性乘法）。

服务器在 `myConv2d(..., type=1)`、`FCLayer(..., flag=1)` 中执行上述运算；非线性 ReLU 由客户端解密后完成。

---

## 8. 明文空间、离散对数与 BSGS

### 8.1 为何必须限制 $\lvert m \rvert$

| 限制来源 | 说明 |
|----------|------|
| **ECDLP 可解性** | BSGS 时间与空间 $O(\sqrt{M})$，$M$ 为 $\lvert m \rvert$ 上界 |
| **预计算表** | `baby_step` 存 $jG$，$j = 0,\ldots,m_{\mathrm{bs}}-1$，$m_{\mathrm{bs}}=3{,}200{,}000$ |
| **论文量级** | 单层卷积约 35 bit；不截断可超 80 bit → 超出离散对数可解范围 |
| **int32 重加密** | `shifting` 后 `.astype(np.int32)`，要求 $\lvert m \rvert < 2^{31}$ |

### 8.1.1 `shifting` / 截断在同态加深时保持什么

同态层数增加时，卷积/FC 会使定点整数 **幅度** $A_l$ 与 **小数位** $f_l$ 同时变大。`shifting(bits)` 在客户端解密后执行：

$$
m_{\mathrm{new}} \approx \mathrm{round}\!\left(\frac{m_{\mathrm{old}}}{2^{\,\text{bits}-16}}\right),\quad f_{\mathrm{new}} = 16
$$

因而每次截断旨在同时保持：

| 保持量 | 含义 |
|--------|------|
| $\lvert m \rvert \le T_{\mathrm{safe}}$ | BSGS 与 `int32` 仍能表示（可解密、可重加密） |
| 有效小数位 $f=16$ | 与权重定点尺度一致，避免 $f$ 无限累积 |
| 近似实值精度 | 右移丢弃低位，用舍入误差换位宽（推理精度与位宽折中） |

**不**保持：同态运算的精确代数相等（截断是有损的）；也 **不** 把实值强行限制在 $[0,1]$（仅输入归一化阶段接近该区间）。

### 8.2 BSGS 算法（与代码一致）

**预计算（Baby step）**——离线一次：

$$
\text{table}[(jG)_x, (jG)_y] = j,\quad j = 0,\ldots,m_{\mathrm{bs}}-1
$$

**在线（Giant step）**——对每个 $\beta$：

1. $\gamma \leftarrow \beta$，$\text{inv} \leftarrow -m_{\mathrm{bs}} \cdot G$
2. 对 $i = 0,\ldots,m_{\mathrm{bs}}-1$：
   - 若 $\gamma \in \text{table}$，返回 $m = i \cdot m_{\mathrm{bs}} + \text{table}[\gamma]$
   - $\gamma \leftarrow \gamma + \text{inv}$

代码见 `giant_step()`；注释中 $n=2^{35}$ 表示**设计明文上界**，实际搜索能力由 $m_{\mathrm{bs}}$ 决定。

### 8.3 静态位宽预算（离线，仓库未自动实现）

逐层估计整数上界 $A_l$，若 $A_l > T_{\mathrm{safe}} = \alpha \cdot \min(m_{\mathrm{bs}}^2, 2^{31}-1)$，则在该层后做 `shifting` 截断。  
公式见 `vPIN论文与代码对照说明.md` 第二节「静态位宽预算」。

### 8.4 无预计算表能否解密

- **可以**：启动时在内存中执行与 `baby_step` 相同的建表，再 `giant_step`。
- **不能**：用同一 $m_{\mathrm{bs}}$ 的表去解 **全 252 bit 的私钥 $x$**（$xG=H$）。

---

## 9. 安全性要点

### 9.1 私钥保密（ECDLP）

给定 $(G, H=xG)$，在经典/通用模型下，求 $x$ 等价于 **ECDLP**，$x$ 从 $\mathbb{Z}_q^*$ 均匀抽样时约为 252 bit 熵。  
**小 $m$ 的 BSGS 表不削弱大 $x$ 的安全性**——表只覆盖 $[0, m_{\mathrm{bs}}^2)$ 量级的指数，与 $x$ 的采样空间无关。

### 9.2 语义安全（IND-CPA 直觉）

指数 ElGamal 在 **DDH（Decisional Diffie-Hellman）** 假设下 IND-CPA 安全（标准教科书结果）：

密文 $(rG,\; mG+rH)$ 在 $H=xG$ 未知 $x$ 时，与随机点对计算不可区分。

**注意**：实现须每次加密使用**新鲜随机** $r$；$r$ 重用会泄露 $m$ 相关信息。

### 9.3 同态运算下的泄露

- 服务器见密文与**公开**权重整数，不见 $x$。
- 多次同态加/标量乘后，**明文位宽增长**是功能问题，不是 IND-CPA 定义内自动处理的问题；需协议层截断。
- 客户端解密中间层会暂时看到部分明文；vPIN 用交互 + 可验证计算约束服务器行为（完整 CP-SNARK 验证见论文，本仓库部分未端到端实现）。

### 9.4 安全与可解密性的分工（回答常见疑问）

| 机制 | 保证什么 |
|------|----------|
| $x \sim$ 全 $\mathbb{Z}_q$ | 无私钥则无法计算 $\beta = c_2 - x c_1$ |
| $\lvert m \rvert \ll q$ 且 BSGS | 有私钥时可从 $\beta = mG$ 恢复小整数 $m$ |
| `shifting` / 截断 | 同态加深时把 $\lvert m \rvert$、$f$ 压回可解密范围（见 [8.1.1](#811-shifting--截断在同态加深时保持什么)） |

**不是**「所有同态加密都靠控 $m$ 与控 $x$」；这是 **ECDLP 型指数编码** 的路径。Paillier 等用代数解密，无第二步 ECDLP（见 `docs/Paillier同态加密-数学推导与实现指南.md`）。

---

## 10. 与经典 ElGamal 的对比

| 项目 | 经典 ElGamal（乘法群/曲线） | 指数 ElGamal（vPIN） |
|------|---------------------------|----------------------|
| 明文嵌入 | $M = m \cdot G$ 或 $m \in \mathbb{F}_p^*$ | $c_2 = mG + rH$ |
| 同态 | 乘法：$c_1 c_2$ → $m_1 m_2$ | **加法**：点加 → $m_1+m_2$ |
| 解密 | 解离散对数得 $m$ | 先代数得 $mG$，再 ECDLP |
| 典型用途 | 加密信道 | 隐私推理、加法电路 |

---

## 11. vPIN 代码实现清单

### 11.1 文件映射

| 功能 | 文件 | 函数 |
|------|------|------|
| 曲线参数 | `cnn_networks/Client.py` | `curveE2Info()` |
| 密钥生成 | 同上 | `keyGen()` |
| 加密 | 同上 | `encrypt()`, `encryptFixedPointValue()` |
| 代数解密 | 同上 | `decrypt_c1_c2()` |
| BSGS | 同上 | `giant_step()` |
| 预计算表 | `Pre_computed_table/baby-step-giant-step.py` | `baby_step()`, `table.pickle` |
| 同态卷积/FC | `cnn_networks/Server.py` | `myConv2d(type=1)`, `FCLayer(flag=1)` |
| 非线性+截断 | `cnn_networks/Client.py` | `relu()`, `shifting(bits)` |

### 11.2 曲线常数（摘录）

```
curveBaseField (= 论文 n2 = q1) = 2^252 + 27742317777372353535851937790883648493
curveOrder   (= 论文 q2)      = 2^252 - 124614587218531604318505012771651942947
BSGS m_bs = 3_200_000
设计明文上界注释 n = 2^35
```

### 11.3 定点与截断

```python
# 加密前
m = round(x_real * 2**16)   # f = 16

# 截断（激活/池化后）
m_new = round(m_old / 2**(bits - 16))   # shifting(bits) → 回到 f=16
```

### 11.4 单元测试建议

1. **往返**：$\mathrm{Dec}(\mathrm{Enc}(m)) = m$，$m \in \{0, 1, 10^6, 2^{20}\}$（在 BSGS 范围内）
2. **同态加**：$\mathrm{Dec}(C_1 \oplus C_2) = m_1 + m_2 \pmod q$
3. **标量**：$\mathrm{Dec}(k \odot C) = km \pmod q$
4. **随机性**：同一 $m$ 两次加密，$(c_1,c_2) \neq (c_1',c_2')$
5. **代数步**：验证 $c_2 - x c_1 = mG$ 无需 BSGS（用已知小 $m$ 构造）

### 11.5 与 Paillier 文档的关系

| 对比项 | Paillier | 本仓库指数 ElGamal |
|--------|----------|-------------------|
| 文档 | `docs/Paillier同态加密-数学推导与实现指南.md` | 本文档 |
| 同态 | 密文乘 → 明文加 | 密文点加 → 明文加 |
| 解密 | $L(c^\lambda)$ 闭式 | ECDLP + BSGS |
| 明文界 | mod $n$ | 小整数 + 截断 |

---

## 12. 附录：证明依赖关系图

```
                    KeyGen: H = xG,  x ∈ Z_q
                           │
                           ▼
              Enc: (c1, c2) = (rG, mG + rH)
                           │
         ┌─────────────────┴─────────────────┐
         ▼                                   ▼
    引理 1: c2 - x·c1 = mG              随机 r → IND-CPA
         │                                   (DDH)
         ▼
    引理 2: BSGS(β) = m  (|m| ≤ M)
         │
         ▼
    定理: Dec(Enc(m)) = m
         │
    ┌────┴────┐
    ▼         ▼
 同态加      标量乘 k·(·)
 m1+m2       k·m
 (点加)      (标量乘点)
```

---

## 参考文献

1. T. ElGamal, *A Public Key Cryptosystem and a Signature Scheme Based on Discrete Logarithms*, IEEE TIT, 1985.  
2. 指数 / 加法同态 ElGamal 变体：见密码学教材中 “Exponential ElGamal”“Additive homomorphic encryption” 章节。  
3. D. Boneh, *The Decision Diffie-Hellman Problem* — DDH 与 ElGamal 语义安全。  
4. vPIN 论文（仓库 README 中的 arXiv 链接）— 神经网络推理中的 AHE 与截断协议。  
5. 本仓库：`vPIN论文与代码对照说明.md`，`docs/Paillier同态加密-数学推导与实现指南.md`。

---

*文档版本：v1.0 | 用途：vPIN 指数 ElGamal 数学参考与实现对照 | 对应实现：cnn_networks / LeNet Client-Server*
