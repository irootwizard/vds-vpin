# Paillier 同态加密：数学推导与实现指南

> 本文档按「思路 → 定义 → 算法 → 证明 → 实现」组织，供后续代码实现查阅。  
> 方案采用标准 Paillier（1999）及最常用的简化变体 $g = n+1$。  
> **公式约定**：行内用 `$...$`，独立公式用 `$$...$$`（与仓库内 `vPIN论文与代码对照说明.md` 一致）。

---

## 目录

1. [整体思路](#1-整体思路)
2. [符号与预备知识](#2-符号与预备知识)
3. [密钥生成](#3-密钥生成)
4. [加密](#4-加密)
5. [解密](#5-解密)
6. [解密正确性证明](#6-解密正确性证明)
7. [加法同态与标量同态](#7-加法同态与标量同态)
8. [简化变体 g = n+1](#8-简化变体-g--n1)
9. [安全性要点](#9-安全性要点)
10. [代码实现清单](#10-代码实现清单)
11. [附录：证明依赖关系图](#11-附录证明依赖关系图)

---

## 1. 整体思路

### 1.1 要解决什么问题

在**不暴露明文**的前提下，让第三方能对密文做运算，且解密结果等于明文上的某种运算。

Paillier 提供的是 **加法同态**：

| 明文运算 | 密文运算 |
|---------|---------|
| $m_1 + m_2$ | 两密文**相乘**（mod $n^2$） |
| $k \cdot m$（$k$ 公开） | 密文**做 $k$ 次乘法**（mod $n^2$） |

**不**提供两密文相乘对应明文相乘（那需要 FHE 或其他方案）。

### 1.2 核心构造（一句话）

选 $n = pq$，在群 $\mathbb{Z}_{n^2}^{\times}$ 中把明文 $m$ 编码为：

$$
c \equiv g^m \cdot r^n \pmod{n^2}
$$

- $g^m$：携带消息 $m$
- $r^n$：随机掩码（$r$ 每次加密随机选取）
- 解密用私钥指数 $\lambda$ 消掉 $r^n$，再用函数 $L(\cdot)$ 读出 $m$

### 1.3 实现主流程

```
KeyGen → (pk, sk)
Enc(pk, m) → c
Dec(sk, c) → m
Add(c1, c2) = c1 * c2 mod n²        // 同态加
Scalar(c, k) = c^k mod n²           // 同态数乘
```

---

## 2. 符号与预备知识

### 2.1 基本符号

| 符号 | 含义 |
|------|------|
| $p, q$ | 两个大素数 |
| $n$ | $n = pq$，公钥的一部分 |
| $\lambda$ | $\lambda = \mathrm{lcm}(p-1, q-1)$，Carmichael 函数 |
| $\varphi(n)$ | $(p-1)(q-1)$，欧拉函数 |
| $\mathbb{Z}_n$ | 明文空间 $\{0, 1, \ldots, n-1\}$ |
| $\mathbb{Z}_n^{\times}$ | 与 $n$ 互素的整数 mod $n$（乘法单位群） |
| $\mathbb{Z}_{n^2}^{\times}$ | 与 $n^2$ 互素的整数 mod $n^2$（密文所在群） |
| $L(x)$ | $\dfrac{x - 1}{n}$（整数除法，结果在 $\mathbb{Z}_n$ 中） |

### 2.2 $L$ 函数

**定义**：对 $x \in \mathbb{Z}$，若 $n \mid (x-1)$，则

$$
L_n(x) = \frac{x - 1}{n} \in \mathbb{Z}
$$

在 Paillier 中，合法输入的 $L$ 值自动 mod $n$ 使用。

**为何需要 $L$**：$c^\lambda$ 形如 $1 + (\text{与 } m \text{ 相关}) \cdot n \pmod{n^2}$，$L$ 把「乘在 $n$ 前面的系数」提取出来。

### 2.3 $n$ 次剩余

**定义**：$x \in \mathbb{Z}_{n^2}^{\times}$ 是 **$n$ 次剩余**，若存在 $y$ 使得

$$x \equiv y^{n} \pmod{n^{2}}$$

**性质**：

- 全体 $n$ 次剩余构成 $\mathbb{Z}_{n^2}^{\times}$ 的正规子群，记为 $R_n$
- $|R_n| = \varphi(n) = (p-1)(q-1)$
- 对 $\gcd(r, n) = 1$，有 $r^n \in R_n$

### 2.4 中国剩余定理（CRT）

若 $\gcd(p, q) = 1$，则同余 mod $n^2$ 等价于分别同余 mod $p^2$ 和 mod $q^2$。

后续引理 1 的证明依赖 CRT。

---

## 3. 密钥生成

### 3.1 算法 KeyGen($1^\kappa$)

**输入**：安全参数 $\kappa$（如 2048）

**步骤**：

1. 生成两个 $\kappa/2$ 位随机素数 $p, q$
2. 计算 $n = pq$
3. 计算 $\lambda = \mathrm{lcm}(p-1, q-1)$
4. 选择 $g \in \mathbb{Z}_{n^2}^{\times}$（推荐 $g = n + 1$，见第 8 节）
5. 计算

$$
\mu = \bigl(L(g^{\lambda})\bigr)^{-1} \bmod n
$$

6. **公钥** $\mathsf{pk} = (n, g)$
7. **私钥** $\mathsf{sk} = (\lambda, \mu)$ 或仅存 $(p, q)$ 按需计算

### 3.2 参数合法性条件

实现时必须保证：

| 条件 | 原因 |
|------|------|
| $p, q$ 为素数且 $p \neq q$ | $n$ 结构正确 |
| $\gcd(n, \lambda) = 1$（实践中通常成立） | $\mu = L(g^\lambda)^{-1}$ 存在 |
| $g \in \mathbb{Z}_{n^2}^{\times}$ | 加密在合法群上 |
| $g$ 的阶是 $n$ 的倍数 | $L(g^{m\lambda})$ 与 $m$ 线性相关 |

**推荐**：$g = n + 1$ 自动满足上述条件（Paillier 原始论文定理 14）。

### 3.3 实现输出结构建议

```python
PublicKey  = { n: int, g: int }
PrivateKey = { p: int, q: int, n: int, lam: int, mu: int }
# 或 PrivateKey 只存 p, q，lam/mu 懒计算
```

---

## 4. 加密

### 4.1 算法 Enc($\mathsf{pk}, m$)

**输入**：

- 公钥 $(n, g)$
- 明文 $m \in \mathbb{Z}_n$，即 $0 \le m < n$

**步骤**：

1. 选随机数 $r \leftarrow \mathbb{Z}_n^{\times}$（均匀随机，$\gcd(r, n) = 1$）
2. 计算
   

$$
c = g^m \cdot r^n \mod n^2
$$

3. 输出密文 $c \in \mathbb{Z}_{n^2}^{\times}$

### 4.2 各步骤含义

| 步骤 | 含义 |
|------|------|
| 检查 $m \in [0, n)$ | 超出范围需编码或报错 |
| 随机 $r$ | 语义安全：同一 $m$ 对应指数级不同密文 |
| $g^m$ | 消息编码 |
| $r^n$ | 一次性随机掩码 |
| mod $n^2$ | 密文长度约 $2 \log_2 n$ 比特 |

### 4.3 加密伪代码

```python
def encrypt(m, pk):
    assert 0 <= m < pk.n
    r = random_coprime(pk.n)          # r ∈ Z_n^*
    c = (powmod(pk.g, m, pk.n2) * powmod(r, pk.n, pk.n2)) % pk.n2
    return c
```

其中 `pk.n2 = n * n`。

---

## 5. 解密

### 5.1 算法 Dec($\mathsf{sk}, c$)

**输入**：

- 私钥 $(\lambda, \mu)$ 及 $n$
- 密文 $c \in \mathbb{Z}_{n^2}^{\times}$

**步骤**：

1. 计算 $x = c^\lambda \mod n^2$
2. 计算 $m = L(x) \cdot \mu \mod n$，即
   

$$
m = \frac{x - 1}{n} \cdot \mu \mod n
$$

3. 输出 $m \in \mathbb{Z}_n$

### 5.2 解密直觉（三步）

```
c = g^m · r^n
       ↓  两边取 λ 次幂
c^λ = g^(mλ) · r^(nλ) = g^(mλ) · 1     ← r^(nλ) 被消掉（引理 1）
       ↓  应用 L(·)
L(c^λ) = m · L(g^λ)                     ← L 的同态性（引理 2）
       ↓  乘 μ = L(g^λ)^(-1)
m = L(c^λ) · μ mod n
```

### 5.3 解密伪代码

```python
def L(x, n):
    return (x - 1) // n                 # 必须整除，否则参数错误

def decrypt(c, sk):
    x = powmod(c, sk.lam, sk.n2)
    m = (L(x, sk.n) * sk.mu) % sk.n
    return m
```

---

## 6. 解密正确性证明

本节给出完整证明链。建议按「引理 → 定理」顺序阅读。

### 6.1 引理 1：随机因子消去

**引理 1**：设 $\gcd(r, n) = 1$，$\lambda = \mathrm{lcm}(p-1, q-1)$。则

$$
r^{n\lambda} \equiv 1 \pmod{n^2}
$$

**证明**：

只需分别证明 mod $p^2$ 和 mod $q^2$ 成立，再由 CRT 合并。

**（1）mod $p^2$**

欧拉定理：若 $\gcd(r, p) = 1$，则 $r^{\varphi(p^2)} \equiv 1 \pmod{p^2}$，其中 $\varphi(p^2) = p(p-1)$。
因 $\lambda$ 是 $p-1$ 的倍数，设 $\lambda = k(p-1)$。则

$$
n\lambda = pq \cdot k(p-1) = q \cdot k \cdot p(p-1) = qk \cdot \varphi(p^2)
$$

故 $r^{n\lambda} \equiv (r^{\varphi(p^2)})^{qk} \equiv 1 \pmod{p^2}$。

**（2）mod $q^2$**

同理，$\varphi(q^2) = q(q-1)$，$\lambda$ 是 $q-1$ 的倍数，

$$
n\lambda = p \cdot k' \cdot q(q-1) = pk' \cdot \varphi(q^2)
$$

故 $r^{n\lambda} \equiv 1 \pmod{q^2}$。

**（3）合并**

$\gcd(p^2, q^2) = 1$，由 CRT：$r^{n\lambda} \equiv 1 \pmod{n^2}$。 ∎

---

### 6.2 引理 2：$L$ 的线性提取

**引理 2**：设 $g$ 为 Paillier 合法生成元，$m \in \mathbb{Z}_n$。则

$$
L\!\left(g^{m\lambda}\right) \equiv m \cdot L\!\left(g^{\lambda}\right) \pmod{n}
$$

**证明（分两种写法）**

#### 写法 A：直接使用 $g = n + 1$（实现最常用）

设 $g = 1 + n$。二项式展开 mod $n^2$：

$$
(1 + n)^t = 1 + tn + \binom{t}{2}n^2 + \cdots \equiv 1 + tn \pmod{n^2}
$$

取 $t = m\lambda$：

$$
g^{m\lambda} = (1+n)^{m\lambda} \equiv 1 + m\lambda n \pmod{n^2}
$$

故

$$
L(g^{m\lambda}) = \frac{(1 + m\lambda n) - 1}{n} = m\lambda \pmod{n}
$$

同理 $L(g^\lambda) = \lambda \pmod{n}$。

若 $\gcd(\lambda, n) = 1$，则 $L(g^{m\lambda}) \equiv m \cdot L(g^\lambda) \pmod{n}$。 ∎

#### 写法 B：一般 $g$ 的子群论证

设 $G_n = \{ x \in \mathbb{Z}_{n^2}^{\times} : x^n \equiv 1 \pmod{n^2} \}$，$|G_n| = n$。
合法 Paillier 的 $g$ 满足 $g^\lambda \in G_n$，且 $L$ 限制在由 $g^\lambda$ 生成的循环子群上是到 $(\mathbb{Z}_n, +)$ 的同构。
对 $g^{m\lambda} = (g^\lambda)^m$：

$$
L(g^{m\lambda}) = L\bigl((g^\lambda)^m\bigr) = m \cdot L(g^\lambda) \pmod{n}
$$

其中用到了 $L(uv) = L(u) + L(v)$（当 $u, v \in G_n$ 时）。 ∎

---

### 6.3 引理 3：$\mu$ 的定义正确

**引理 3**：设 $\mu = L(g^\lambda)^{-1} \mod n$。则

$$
L(g^\lambda) \cdot \mu \equiv 1 \pmod{n}
$$

且对任意 $m \in \mathbb{Z}_n$：

$$
m \cdot L(g^\lambda) \cdot \mu \equiv m \pmod{n}
$$

**证明**：由 $\mu$ 的定义直接得出。 ∎

---

### 6.4 定理：解密正确性

**定理（主定理）**：对任意 $m \in \mathbb{Z}_n$，$r \in \mathbb{Z}_n^{\times}$，令 $c = \operatorname{Enc}(m) = g^m r^n \mod n^2$。则

$$
\operatorname{Dec}(c) = m
$$

**证明**：

**第一步**：计算 $c^\lambda$。

$$
c^\lambda = (g^m r^n)^\lambda = g^{m\lambda} \cdot r^{n\lambda} \pmod{n^2}
$$

由引理 1，$r^{n\lambda} \equiv 1$，故

$$
c^\lambda \equiv g^{m\lambda} \pmod{n^2}
$$

**第二步**：应用 $L$。

$$L(c^{\lambda}) = L(g^{m\lambda}) \equiv m \cdot L(g^{\lambda}) \pmod{n}$$

*（引理 2）*

**第三步**：乘 $\mu$。

$$L(c^{\lambda}) \cdot \mu \equiv m \cdot L(g^{\lambda}) \cdot \mu \equiv m \pmod{n}$$

*（引理 3）*

故 $\operatorname{Dec}(c) = m$。∎

---

## 7. 加法同态与标量同态

### 7.1 定理：加法同态

**定理**：设 $c_1 = \operatorname{Enc}(m_1)$，$c_2 = \operatorname{Enc}(m_2)$（独立随机数）。则

$$
c_1 \cdot c_2 \mod n^2 = \operatorname{Enc}(m_1 + m_2)
$$

且

$$
\operatorname{Dec}(c_1 \cdot c_2) = m_1 + m_2 \pmod{n}
$$

**证明**：

$$
c_1 c_2 = g^{m_1} r_1^n \cdot g^{m_2} r_2^n = g^{m_1 + m_2} \cdot (r_1 r_2)^n \pmod{n^2}
$$

令 $r' = r_1 r_2$。因 $r_1, r_2 \in \mathbb{Z}_n^{\times}$，有 $\gcd(r', n) = 1$，故 $r' \in \mathbb{Z}_n^{\times}$。

因此 $c_1 c_2$ 恰为明文 $m_1 + m_2$ 在随机数 $r'$ 下的合法密文。

由主定理（解密正确性）：

$$
\operatorname{Dec}(c_1 c_2) = m_1 + m_2 \pmod{n} \quad \checkmark
$$

**注意**：明文加法是 mod $n$ 的。若业务上 $m_1 + m_2 \ge n$，解密结果是 $m_1 + m_2 - n$。

---

### 7.2 定理：标量同态

**定理**：设 $c = \operatorname{Enc}(m)$，$k \in \mathbb{Z}$ 为**公开**整数。则

$$
c^k \mod n^2 = \operatorname{Enc}(k \cdot m)
$$

**证明**：

$$
c^k = (g^m r^n)^k = g^{km} \cdot (r^k)^n \pmod{n^2}
$$

$r^k$ 仍与 $n$ 互素，故这是 $km \mod n$ 的合法加密。由主定理：

$$
\operatorname{Dec}(c^k) = km \pmod{n} \quad \checkmark
$$

**限制**：$k$ 不能加密；若 $k$ 也需保密，需 OT/MPC 等额外协议。

---

### 7.3 复合运算

多个明文求和：

$$
\operatorname{Dec}\left(\prod_{i=1}^{t} c_i\right) = \sum_{i=1}^{t} m_i \pmod{n}
$$

加权求和（权重 $k_i$ 公开）：

$$
\operatorname{Dec}\left(\prod_{i=1}^{t} c_i^{k_i}\right) = \sum_{i=1}^{t} k_i m_i \pmod{n}
$$

---

## 8. 简化变体 g = n + 1

### 8.1 为何使用

- 无需搜索合法 $g$
- $g^m \mod n^2$ 可快速计算为 $1 + mn$
- 实现简单，工业界默认选择

### 8.2 加密公式简化

$$
\operatorname{Enc}(m) = (1 + mn) \cdot r^n \mod n^2
$$

**推导**：

$$
g^m = (1+n)^m = \sum_{i=0}^{m}\binom{m}{i}n^i \equiv 1 + mn \pmod{n^2}
$$

### 8.3 解密中 $\mu$ 的简化

当 $g = n+1$ 时：

$$g^{\lambda} = (1+n)^{\lambda} \equiv 1 + \lambda n \pmod{n^{2}}$$

$$L(g^{\lambda}) = \lambda \pmod{n}$$

$$\mu = \lambda^{-1} \bmod n$$

**实现**：KeyGen 时可直接 `mu = modinv(lam, n)`，但仍建议按定义验证 $L(g^\lambda) \cdot \mu \equiv 1 \pmod{n}$。

### 8.4 加密实现（推荐写法）

```python
def encrypt_fast(m, pk):
    n, n2 = pk.n, pk.n * pk.n
    r = random_coprime(n)
    # (1 + m*n) * r^n mod n²
    c = ((1 + m * n) * powmod(r, n, n2)) % n2
    return c
```

---

## 9. 安全性要点

### 9.1 假设：判定性复合 Residuosity（DCR）

**DCR 问题**：给定 $n = pq$ 和 $x \in \mathbb{Z}_{n^2}^{\times}$，区分 $x$ 是 **$n$ 次剩余** 还是 **随机元**。

**定理（Paillier, 1999）**：在 DCR 假设下，Paillier 方案达到 **IND-CPA**（选择明文攻击下不可区分）。

实现含义：密文 $c = g^m r^n$ 不泄露 $m$ 的任何信息（在多项式时间内）。

### 9.2 实现安全 checklist

| 项 | 要求 |
|----|------|
| 素数生成 | 用密码学安全 PRNG；验证 Miller-Rabin / 确定性测试 |
| $r$ 的随机性 | 每次加密必须重新采样，不可固定 |
| $r$ 的范围 | $r \in \mathbb{Z}_n^{\times}$，即 $\gcd(r,n)=1$ |
| 明文范围 | $m \in [0, n)$，溢出需编码策略 |
| 侧信道 | 模幂、模逆用常数时间实现（生产环境） |
| 完整性 | Paillier 不提供认证，需配合 MAC/签名 |
| 私钥保护 | $p, q, \lambda, \mu$ 不可泄露 |

### 9.3 常见攻击（实现时需避免）

| 攻击 | 原因 | 对策 |
|------|------|------|
| 固定 $r$ | 同一 $m$ 同一密文 | 每次随机 $r$ |
| $m \ge n$ | 明文不在 $\mathbb{Z}_n$ | 断言或编码 |
| 多次同态加溢出 | $\sum m_i \ge n$ | 选更大 $n$ 或分段 |
| 恶意 $g$ | 参数注入 | 固定 $g = n+1$ 并验证 |

---

## 10. 代码实现清单

### 10.1 依赖的大数运算

| 函数 | 用途 |
|------|------|
| `powmod(a, e, m)` | 模幂：$a^e \mod m$ |
| `modinv(a, m)` | 模逆：$a^{-1} \mod m$ |
| `gcd(a, b)` | 判断互素 |
| `is_prime(x)` | 素性测试 |
| `random_coprime(n)` | 生成 $r \in \mathbb{Z}_n^{\times}$ |
| `L(x, n)` | $(x-1)/n$，需断言整除 |

Python 可用 `pow(a, e, m)`；大参数建议 `gmpy2` 或 `python-gmp`。

### 10.2 推荐参数

| 参数 | 推荐值 |
|------|--------|
| $\lvert p \rvert$、$\lvert q \rvert$（素数本身 bit 长） | 各 1024 bit（$n$ 为 2048 bit） |
| 明文空间 | $\mathbb{Z}_n$，约 2048 bit 整数 |
| 密文空间 | $\mathbb{Z}_{n^2}^{\times}$，约 4096 bit |
| $g$ | $n + 1$ |

### 10.3 完整 API 设计

```python
class PaillierPublicKey:
    n: int
    g: int
    n2: int          # n²，缓存避免重复计算

class PaillierPrivateKey:
    p: int
    q: int
    n: int
    lam: int         # lcm(p-1, q-1)
    mu: int
    n2: int

def keygen(bit_length=2048) -> (PaillierPublicKey, PaillierPrivateKey): ...
def encrypt(m: int, pk: PaillierPublicKey) -> int: ...
def decrypt(c: int, sk: PaillierPrivateKey) -> int: ...
def add(c1: int, c2: int, n2: int) -> int: ...
def scalar_mult(c: int, k: int, n2: int) -> int: ...
```

### 10.4 KeyGen 实现步骤

```python
def keygen(bit_length=2048):
    half = bit_length // 2
    p = random_prime(half)
    q = random_prime(half)
    while p == q:
        q = random_prime(half)

    n = p * q
    n2 = n * n
    lam = lcm(p - 1, q - 1)
    g = n + 1

    # μ = L(g^λ)^{-1} mod n
    g_lam = pow(g, lam, n2)
    mu = modinv(L(g_lam, n), n)

    pk = PublicKey(n=n, g=g, n2=n2)
    sk = PrivateKey(p=p, q=q, n=n, lam=lam, mu=mu, n2=n2)
    return pk, sk
```

### 10.5 Enc / Dec 实现

```python
def encrypt(m, pk):
    if not (0 <= m < pk.n):
        raise ValueError("plaintext out of range")
    r = random_coprime(pk.n)
    c = ((1 + m * pk.n) * pow(r, pk.n, pk.n2)) % pk.n2
    return c

def decrypt(c, sk):
    x = pow(c, sk.lam, sk.n2)
    m = (L(x, sk.n) * sk.mu) % sk.n
    return m

def add(c1, c2, n2):
    return (c1 * c2) % n2

def scalar_mult(c, k, n2):
    return pow(c, k, n2)
```

### 10.6 明文编码（有符号数与定点数）

Paillier 原生是 $\mathbb{Z}_n$ 上的**无符号**加法。

**有符号整数**（$m \in [-n/2, n/2)$）：

```python
def encode_signed(x, n):
    if x < 0:
        return n + x          # 例如 n - |x|
    return x

def decode_signed(m, n):
    if m > n // 2:
        return m - n
    return m
```

**定点数**（保留 $f$ 位小数，放大 $2^f$ 倍）：

```python
SCALE = 1 << 16   # f = 16

def encode_fixed(x_float):
    return int(round(x_float * SCALE))

def decode_fixed(m_encoded):
    return m_encoded / SCALE
```

同态加后若需控制精度，要在协议层做截断（Paillier 本身不提供）。

### 10.7 单元测试用例

实现后至少验证：

1. **往返**：$\operatorname{Dec}(\operatorname{Enc}(m)) = m$，对 $m \in \{0, 1, n-1, n//2\}$
2. **同态加**：$\operatorname{Dec}(\operatorname{Enc}(m_1) \cdot \operatorname{Enc}(m_2)) = m_1 + m_2 \pmod{n}$
3. **标量**：$\operatorname{Dec}(\operatorname{Enc}(m)^k) = km \pmod{n}$
4. **随机性**：同一 $m$ 两次加密 $c_1 \neq c_2$
5. **边界**：$m_1 + m_2 = n$ 时结果为 0

玩具参数测试（**不可用于生产**）：

```
p = 61, q = 53, n = 3233
λ = lcm(60, 52) = 780
g = 3234
```

---

## 11. 附录：证明依赖关系图

```
                    KeyGen(n, g, λ, μ)
                           │
                           ▼
              Enc: c = g^m · r^n mod n²
                           │
         ┌─────────────────┼─────────────────┐
         ▼                 ▼                 ▼
    引理 1              引理 2            引理 3
 r^(nλ) ≡ 1      L(g^(mλ)) = m·L(g^λ)   μ = L(g^λ)^(-1)
         └────────┬────────┘                 │
                  ▼                           │
           定理：Dec(Enc(m)) = m  ◄───────────┘
                  │
      ┌───────────┴───────────┐
      ▼                       ▼
 同态加：c₁c₂              标量：c^k
 Dec = m₁+m₂               Dec = km
```

---

## 12. 与 vPIN 项目的关系（参考）

本仓库 vPIN 使用的是 **指数 ElGamal（椭圆曲线）**，不是 Paillier：

| 对比项 | Paillier | vPIN ElGamal |
|--------|----------|--------------|
| 同态 | 密文乘法 → 明文加法 | 密文点加 → 明文加法 |
| 解密 | 代数 $L(c^\lambda)$ | 代数步 + 离散对数（BSGS 表） |
| 非线性层 | 无法原生支持 | 交互 + ZK 证明 |

**ElGamal 完整推导与证明**见同目录 [`指数ElGamal同态加密-数学推导与实现指南.md`](指数ElGamal同态加密-数学推导与实现指南.md)。

若将来在联邦统计、投票等**只需加法**的场景，Paillier 更合适；若需与椭圆曲线 R1CS 证明结合，应继续用 ElGamal 路线。

---

## 参考文献

1. P. Paillier, *Public-Key Cryptosystems Based on Composite Degree Residuosity Classes*, EUROCRYPT 1999.
2. 常用实现参考：Python `phe` 库、GMP 大数运算文档。

---

*文档版本：v1.1 | 用途：Paillier 代码实现前的数学参考 | 已修正公式预览语法*
