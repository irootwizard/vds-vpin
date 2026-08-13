# 大语言模型可验证推理：完整抽象设计

> **定位**：独立描述 LLM 可验证推理的数学目标、协议抽象、博弈均衡与具体算法，**不涉及**任何既有系统迁移。  
> **本地文献 PDF**：[`literature/papers/`](./literature/papers/) · [`literature/README.md`](./literature/README.md)

---

## 目录

1. [问题与目标](#1-问题与目标)
2. [为什么不能全量证明](#2-为什么不能全量证明)
3. [威胁模型](#3-威胁模型)
4. [协议抽象](#4-协议抽象)
5. [抽样检测与博弈均衡](#5-抽样检测与博弈均衡)
6. [成本与参数](#6-成本与参数)
7. [局部验证原语](#7-局部验证原语)
8. [具体算法](#8-具体算法)
9. [稀疏与 MoE](#9-稀疏与-moe)
10. [方案选型](#10-方案选型)
11. [落地阶段与边界](#11-落地阶段与边界)
12. [文献索引](#12-文献索引)

---

## 1. 问题与目标

**问题**：不可信推理服务器声称用模型 $M$、策略 $\pi$ 对输入 $x$ 产生输出 $y$。客户端如何以可接受成本相信该声称？

| 子问题 | 典型作弊 |
|--------|----------|
| 是否用了声称的模型？ | 70B 标称、7B 实跑 |
| 是否按声称精度执行？ | FP16 标称、INT4 实跑 |
| 输出是否绑定真实 decode 路径？ | 先写答案再伪造 logits |
| 计费 token 是否诚实？ | 多报内部 token |

**设计目标**（大模型场景）：

$$
\boxed{
O(N_W)\ \text{一次性模型注册}
\;+\;
O(k \cdot \mathrm{polylog}\, N_W)\ \text{每次审计}
}
$$

**安全目标**不是 $\Pr[\mathrm{cheat}]=0$，而是：

$$
\boxed{
\mathbb E[U_{\mathrm{cheat}}] < \mathbb E[U_{\mathrm{honest}}]
\quad\Leftrightarrow\quad
p(P+L)+C_A > G
}
$$

即：理性服务器选择诚实计算是均衡策略。

---

## 2. 为什么不能全量证明

设模型参数量 $N_W \in [10^8, 10^{11}]$，decoder-only Transformer 每层计算量：

$$
C_\ell = \Theta(Ld^2 + L^2d)
$$

其中 $L$ 为序列长，$d$ 为 hidden size。全量 R1CS / zk 化：

$$
C_{\mathrm{full}} = \Theta(n_\ell \cdot (Ld^2 + L^2d))
$$

对在线 70B API **不可生产**。因此采用三层保证光谱：

| 等级 | 机制 | 安全类型 | 适用 |
|------|------|----------|------|
| 强 | 全量 / 递归 zkML | 密码学 hard soundness | 小模型、离线高价值 |
| 中 | 承诺 + 随机审计 + 局部证明 | 概率 soundness | **LLM 在线服务** |
| 弱 | 输出分布 / hidden 指纹 | 风控信号 | 辅助，非证明 |

---

## 3. 威胁模型

| 编号 | 作弊 | 收益 |
|------|------|------|
| A1 | 小模型替代大模型 | 节省 GPU |
| A2 | 跳层 / 降精度 | 节省算力 |
| A3 | 激进量化 | 节省显存与带宽 |
| A4 | 缓存 / 模板答案 | 几乎零推理 |
| A5 | 篡改 logits / decode path | 控制输出 |
| A6 | 伪造 trace commitment | 逃避审计 |

方案不追求一次排除全部作弊，而是使每种作弊的**期望收益为负**。

---

## 4. 协议抽象

### 4.1 核心对象

| 对象 | 含义 |
|------|------|
| $\mathbf W^*$ | 模型权重 |
| $\mathsf{cm}_W$ | 模型承诺：$\mathsf{Commit}(\mathbf W^*)$ |
| $\tau$ | 模型指纹：$H(\mathrm{arch}, \mathrm{tokenizer}, \mathrm{quant}, \mathsf{cm}_W, \mathrm{decode\_policy})$ |
| $\mathsf{cm}_{\mathrm{trace}}$ | 推理轨迹承诺：中间激活、logits、decode 路径 |
| $\mathcal U$ | 审计单元集合，$N = |\mathcal U|$ |
| $\mathcal S \subset \mathcal U$ | 挑战抽中的 $k$ 个单元 |

### 4.2 五阶段流程

```text
Setup      → 注册 (model_id, manifest, cm_W, stake_policy)
Inference  → 推理并输出 (answer, cm_trace, receipt)
Challenge  → VRF 抽样 S（必须在 cm_trace 公布之后）
Open       → 服务器打开权重 + trace 局部
Verify     → 验证者 LocalCheck(S)
Settle     → 通过则 pay(R)；失败则 slash(P)
```

**时序约束（防适配）**：

$$
\text{cm\_trace 固定} \;\Rightarrow\; \text{VRF 挑战} \;\Rightarrow\; \text{打开} \;\Rightarrow\; \text{验证} \;\Rightarrow\; \text{结算}
$$

若挑战在 trace 之前，服务器可只诚实计算被抽中层。

### 4.3 审计单元类型

```text
LINEAR_GEMM    // y = Wx
ATTN_OUTPUT    // Attention 输出
NORM           // LayerNorm / RMSNorm
ACTIVATION     // GELU / SiLU
DECODE_STEP    // logits + 采样随机数 xi + token
MOE_ROUTE      // 路由 + 选中专家
LORA_DELTA     // 低秩增量
```

---

## 5. 抽样检测与博弈均衡

### 5.1 检测概率

作弊影响 $t$ 个单元，总空间 $N$，抽查 $k$ 个：

$$
p_{\mathrm{hit}} = 1 - \frac{\binom{N-t}{k}}{\binom{N}{k}}
\approx \frac{kt}{N} \quad (t \ll N)
$$

$q$ 次独立审计：$p_q = 1 - (1-p_{\mathrm{hit}})^q$。

### 5.2 效用与均衡

| 符号 | 含义 |
|------|------|
| $R$ | 诚实完成推理的收入 |
| $C_H, C_C$ | 诚实 / 作弊成本 |
| $G = C_H - C_C$ | 作弊节省 |
| $p$ | 被检测概率（含审计频率 $\rho$：$p_{\mathrm{eff}} = \rho \cdot p_{\mathrm{hit}}$） |
| $P$ | 罚没 / 押金损失 |
| $L$ | 声誉折损 |
| $C_A$ | 应对审计的伪造成本 |

$$
U_H = R - C_H, \qquad
U_C = R - C_C - C_A - p(P+L)
$$

诚实均衡条件：

$$
\boxed{p(P+L) + C_A > G}
\qquad\Rightarrow\qquad
P > \frac{G}{p} - L \quad (C_A \approx 0)
$$

多轮会话（$q$ 次，每次节省 $G$）：

$$
P_{\min}^{(q)} = \frac{qG}{1-(1-p)^q} \approx qG \quad (q \text{ 大})
$$

### 5.3 多方扩展

- **推理市场**：需最低 stake 门槛，否则逆向选择淘汰诚实服务器。
- **多 verifier**：$p_{\mathrm{multi}} = 1 - (1-\rho p_{\mathrm{hit}})^m$；需防 verifier 与服务器串谋。
- **懒验证者**：验证成功也须奖励 $R_V$，使 $R_V - C_V > 0$。

---

## 6. 成本与参数

### 6.1 基本公式

| 量 | 公式 |
|----|------|
| 训练 FLOPs | $C_{\mathrm{train}} \approx 6ND$ |
| 每 token 推理 | $C_{\mathrm{fwd/token}} \approx 2N$ |
| 每层 | $C_\ell \approx 4Ld^2 + 2Ld^2 + 2L^2 d \cdot n_h/n_{kv}$ |

### 6.2 替换收益 $G$（典型）

| 策略 | $G/C_H$ |
|------|---------|
| 70B → 7B | $\approx 0.90$ |
| 70B → 13B | $\approx 0.81$ |
| FP16 → INT4 | $\approx 0.5$–$0.75$ |
| 跳过 $k/n_\ell$ 层 | $\approx k/n_\ell$ |

### 6.3 伪造成本 $C_A$

| 路径 | $C_A$ |
|------|-------|
| 诚实 trace + 正常 opening | $O(k\log N_W + kd^2)$ |
| 事后编造 trace | $\Omega(C_H)$ |

### 6.4 参数选取

目标检测率 $p^\star$，近似：

$$
k \gtrsim \frac{N}{t}\ln\frac{1}{1-p^\star}
$$

押金（含审计频率 $\rho$）：

$$
P > \frac{G}{\rho \cdot p_{\mathrm{hit}}}
$$

**数值例**：70B→7B，$G=0.9C_H$，$\rho=0.01$，$k=5$，$t=10^5$，$N=10^6$ → $p_{\mathrm{hit}}\approx 0.41$，$p_{\mathrm{eff}}\approx 0.0041$ → $P \gtrsim 220 \cdot C_H$（或提高 $\rho$/$k$）。

### 6.5 审计开销预算（领域实测量级）

| 方案 | Prover 额外 | Verifier |
|------|-------------|----------|
| TensorCommitments | $\approx 1\%$ | $\approx 0.1\%$ |
| VeriLLM | $\approx 1\%$ | 轻量链上 |
| IMMACULATE | $<1\%$ 吞吐 | VC 子集 |

---

## 7. 局部验证原语

### 7.1 线性层 Freivalds

对 $y = Wx$，采样随机向量 $r$：

$$
r^\top y \stackrel{?}{\approx} r^\top W x
$$

精确域漏检 $\le |\mathbb F|^{-1}$；浮点用容差 $\epsilon$ 与多次独立 $r$。复杂度 $O(d)$。

### 7.2 Attention（抽样）

完整 softmax 证明昂贵。默认：
- 对 $QK^\top$ 随机行/列 Freivalds；
- 对 softmax 输出做行级一致性 + $\sum w \approx 1$；
- KV cache 纳入 trace 承诺。

### 7.3 Decode 路径

必须绑定：

$$
token_t = \mathsf{Decode}(\mathrm{logits}_t, \mathrm{policy}, \xi_t)
$$

无 $\xi_t$ 绑定 → 服务器可先定 token 再伪造 logits（威胁 A5）。

### 7.4 非线性（Norm / Activation）

抽样点局部重算 + 容差检查，$O(k)$。

---

## 8. 具体算法

### 8.1 总览

```text
Alg-1  ModelRegister          模型注册与 cm_W
Alg-2  InferAndCommitTrace    推理 + cm_trace
Alg-3  VRFChallenge           不可预测抽样
Alg-4  OpenAndProve           打开权重与 trace
Alg-5  LocalVerify            局部验证（5a–5d）
Alg-6  SettleOrSlash          结算 / 罚没
Alg-7  ComputeStakeParams     押金与 k 计算
Alg-8  MoERouteVerify         MoE 路由验证
```

### 8.2 Alg-1：ModelRegister

```python
def ModelRegister(manifest, weights, stake_policy):
    tau = H(arch, tokenizer, quant, tensor_layout, decode_policy)
    for tensor in manifest.tensors:
        for chunk in chunk_tensor(tensor, chunk_size=4096):
            leaf = H(name, dtype, shape, idx, canonical_bytes(chunk))
        tensor_root = MerkleRoot(leaves)
    cm_W = H(tau, serialize(tensor_roots))
    audit_manifest = build_audit_units(manifest)
    stake_min = ComputeStakeParams(stake_policy, N=len(audit_manifest))
    return model_id, cm_W, stake_min, audit_manifest
```

复杂度：$O(N_W)$ hash（一次性）。

### 8.3 Alg-2：InferAndCommitTrace

```python
def InferAndCommitTrace(model_id, prompt, session_id, decode_policy):
    trace_leaves = []
    for layer in layers:
        # attention, norm, mlp — 每层 commit 审计单元
        trace_leaves += commit_units(...)
    for step in decode_steps:
        logits = lm_head(hidden[-1])
        xi = sample_rng(decode_policy, session_id, step)
        token = decode(logits, decode_policy, xi)
        trace_leaves += [H(DECODE_STEP, step, topk_digest(logits), xi, token)]
    cm_trace = MerkleRoot(trace_leaves)
    receipt = H(model_id, session_id, cm_trace, H(answer), H(prompt), ...)
    return answer, cm_trace, receipt
```

Prover 额外开销目标 $<2\%$ 推理时间。

### 8.4 Alg-3：VRFChallenge

```python
def VRFChallenge(cm_W, cm_trace, receipt, session_id, beacon, k):
    seed = VRF(H(cm_W, cm_trace, receipt, session_id, beacon))
    S = sample_without_replacement(audit_units, k, seed)
    return challenge_record(S, seed, deadline)
```

### 8.5 Alg-4：OpenAndProve

对每个 $u \in \mathcal S$：
- Merkle 打开 trace 叶子；
- Merkle 打开所需权重 chunk；
- 提供 $(W_{\mathrm{local}}, x_{\mathrm{local}}, y_{\mathrm{claimed}})$。

通信量：每单元 $O(h_w + h_t)$，$h_w = \lceil \log N_W \rceil$。

### 8.6 Alg-5：LocalVerify

```python
def LocalVerify(challenge, openings):
    for op in openings:
        assert MerkleVerify(cm_W, op.weight_paths)
        assert MerkleVerify(cm_trace, op.trace_path)
        match op.unit.type:
            case LINEAR_GEMM:   FreivaldsGEMM(W, x, y)
            case ATTN_OUTPUT:   PartialAttnVerify(op)
            case DECODE_STEP:   DecodePathVerify(op)
            case MOE_ROUTE:     MoERouteVerify(op)
            case _:             LocalReplay(op, epsilon)
    return PASS
```

**FreivaldsGEMM**：3 次独立 $r$，容差 $\epsilon$。  
**DecodePathVerify**：重算 `token = decode(logits, policy, xi)` 并核对 `logits_digest`。

### 8.7 Alg-6：SettleOrSlash

```python
if verify == PASS:
    pay(server, R); pay(verifier, R_V)
else:
    slash(server, min(stake, P)); pay(verifier, alpha * P)
    reputation[server] -= delta
```

### 8.7 Alg-7：ComputeStakeParams

```python
def ComputeStakeParams(G, p_target, rho, N, t_worst):
    k = min k s.t. 1 - C(N-t, k)/C(N, k) >= p_target
    p_eff = rho * p_hit(k)
    P_min = max(0, (G - C_A) / p_eff - L)
    return {k, p_hit, p_eff, P_min}
```

### 8.8 Alg-8：MoERouteVerify

重算 `top-k` 专家集合 $\mathcal I$，打开各专家 Merkle path，验证：

$$
y = \sum_{e \in \mathcal I} g'_e \cdot E_e(x)
$$

### 8.9 REST 消息流

```text
POST /registry/models     → { manifest, cm_W, stake_min }
POST /infer               → { answer, cm_trace, receipt }
POST /audit/challenge     → { challenge_record, vrf_proof }   // prob ρ
POST /audit/open          → { openings }
POST /audit/verify        → { pass | fail }
POST /settle              → { payment_receipt }
```

### 8.10 实现优先级

| 阶段 | 范围 | 产物 |
|------|------|------|
| MVP-L1 | Alg-1/2，仅 DECODE_STEP | 解码路径可验证 |
| MVP-L2 | + Alg-3/4/5a/6 | 线性层 Freivalds 审计 |
| MVP-L3 | + Attention/Decode 完整 + Alg-7 | 抽样 + 押金计算器 |
| Prod | + MoE/LoRA + 链上 VRF | 生产路径 |

---

## 9. 稀疏与 MoE

### 9.1 核心条件

Merkle 打开仅当 $k_w \ll N_W$ 且 $k_w \cdot h \ll N_W$ 可行（$h = \lceil \log_2 N_W \rceil$）。

Dense 70B 每 token 全量 opening **不可行**；仅抽样 / 稀疏结构适用。

### 9.2 结构对比

| 结构 | 打开量 $k_w$ | 路由证 |
|------|-------------|--------|
| Dense | $N_W$ | 否 |
| MoE top-$k$ | $k \cdot N_E$ per layer | **是** |
| LoRA rank-$r$ | $O(rd)$ | 否 |
| 稀疏 Attention | $O(L k_{\mathrm{attn}})$ | 是 |

MoE 需同时证：

$$
\mathrm{Router}(x) = \mathcal I \;\land\; y = \sum_{e \in \mathcal I} g'_e E_e(x)
$$

推荐 **per-expert Merkle root** + 全局 manifest root。

### 9.3 UsedIndices

trace receipt 显式记录每层实际使用的权重块 / 专家 / 激活坐标，使审计空间 $N$ 等于活跃单元而非全 $N_W$。

---

## 10. 方案选型

### 10.1 对比矩阵（摘要）

| 方案 | Prove | Verify | Soundness | 70B 在线 |
|------|-------|--------|-----------|----------|
| 全量 zkML | $10^3$–$10^6\times$ | ms–s | 密码学 | ✗ |
| 递归 / GKR 子图 | 子图相关 | 聚合 ms | 密码学 | △ 离线 |
| Merkle/Terkle + 抽样 | $<2\%$ | $O(kh)$ | 概率 | ✓ |
| TensorCommitments | $\approx 1\%$ | $\approx 0.1\%$ | 概率 | ✓ |
| Freivalds 局部 | $O(d)$ | $O(d)$ | 概率 | ✓ 局部 |
| TEE attestation | $<5\%$ | ms | 硬件信任 | ✓ |
| VeriLLM 式 | $\approx 1\%$ | 轻链上 | 1-诚实 verifier | ✓ |
| 纯押金博弈 | 极低 | 极低 | 理性 | ✓ 无密码保证 |

### 10.2 场景推荐

| 场景 | 推荐 | 避免 |
|------|------|------|
| 在线 API 推理市场 | TC/VeriLLM + 押金 | 全量 zkML |
| 黑盒商业 API | IMMACULATE (LDD+VC) | 声称零错误 |
| MoE 服务 | per-expert Merkle + 路由审计 | 全模型 opening |
| 离线高价值合同 | 递归 SNARK 分层 | 单次博弈审计 |
| 输入隐私 | TEE 或 FHE 混合 + trace 审计 | 纯明文 Merkle |

### 10.3 输入隐私与计算诚实（正交）

$$
\text{输入隐私（AHE/FHE/TEE）} \nRightarrow \text{计算量诚实}
$$

密文推理下服务器仍可能用小模型、跳层、伪造 trace；须独立做 trace commitment + 审计。

---

## 11. 落地阶段与边界

### 11.1 阶段路线

```text
L0  威胁模型 + manifest + stake 规则
L1  trace commitment + decode receipt
L2  VRF 抽样 + Merkle opening + 局部重算
L3  stake / slash / verifier 激励
L4  高价值算子 sumcheck / 小 zk 片段
L5  离线任务递归 / 分层证明
```

### 11.2 产品声明禁区

1. 博弈论安全 $\neq$ 密码学 soundness → 对外写 **理性安全 / 概率审计**。
2. 输出文本检测、hidden 指纹 → 风控，非 opening 替代。
3. Dense 70B 全权重每 token Merkle opening → **不可行**。
4. AHE/FHE → 输入隐私，**不自动**保证算力诚实。

### 11.3 实现 checklist

- [ ] VRF 输入含 `cm_trace`；挑战晚于 trace 公布
- [ ] Decode 绑定 `xi` 与 `logits_digest`
- [ ] 浮点 canonical 字节序一致
- [ ] 权重 opening 与 trace opening 交叉验证
- [ ] 失败必须 slash，非仅 warn

---

## 12. 文献索引

| 类别 | 代表 | 要点 |
|------|------|------|
| 缩放律 | Chinchilla 2022 | $C_{\mathrm{train}} \approx 6ND$ |
| 推理缩放 | Beyond Chinchilla 2024 | 生命周期含推理 token |
| 张量承诺 | TensorCommitments 2026 | Terkle，Llama2 $<1\%$ prover |
| 去中心化推理 | VeriLLM 2025 | Merkle+VRF+slash，$\approx 1\%$ |
| 黑盒审计 | IMMACULATE 2026 | LDD + VC |
| 轻量 trace | Lightweight Proofs 2026 | trace separation，毫秒级 |
| 抽样理论 | Proof of Sampling 2024 | 博弈 + 抽样 |
| zk 分层 | NanoZK 2026, zkLLM 2024 | 离线 / 小模型硬证明 |
| 本地 PDF | [literature/README.md](./literature/README.md) | 12 篇 |

**完整文献摘录**（分六域分析）：[`llm-verifiable-inference-literature-survey.md`](./llm-verifiable-inference-literature-survey.md)

---

## 结论

$$
\boxed{
\text{LLM 可验证推理 = 模型承诺 + trace 承诺 + VRF 抽样 + 局部打开/重算 + 押金罚没}
}
$$

数学目标：

$$
p_{\mathrm{eff}}(P+L) + C_A > G
\quad\Rightarrow\quad
\mathbb E[U_{\mathrm{cheat}}] < \mathbb E[U_{\mathrm{honest}}]
$$

与全量 zk 的关系：**互补而非替代**——在线服务走中强度审计，离线高价值走局部/递归硬证明。
