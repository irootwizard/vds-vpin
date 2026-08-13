# AHE/FHE 大语言模型推理与非线性线性化方案总结

## 1. 研究背景

Transformer 中绝大多数计算量来自矩阵乘（Linear），GPU 推理时约 95%~99% FLOPs 都来自 Attention 和 FFN 中的线性层，而 Softmax、LayerNorm、SwiGLU/GELU 等非线性层 FLOPs 占比很低。

但对于 AHE/FHE 而言，瓶颈完全不同：

- Linear：可直接利用同态加法/乘法高效计算。
- Nonlinear：通常需要多项式近似、Bootstrapping、Client 参与或 TEE，因此成为整个系统最大的性能瓶颈。
- 因此 AHE/FHE 的优化目标不是减少 FLOPs，而是减少非线性计算及其带来的加解密、通信和 Bootstrapping 开销。

---

# 2. 当前研究目标

目标不是简单减少模型参数，而是重新设计 Transformer 的计算图。

原始结构：

Linear → Nonlinear → Linear → Nonlinear → Linear

期望结构：

Linear → Linear → Linear → Nonlinear

或

多个 Block → 一次统一 Nonlinear

主要收益：

- 减少 Linear / Nonlinear 切换次数
- 减少 Client-Server 交互
- 减少 Encrypt/Decrypt 次数
- 减少 Communication Round
- 减少 Bootstrapping
- 提高 AHE/FHE 推理效率

GPU 推理几乎不会因此受益，但 AHE/FHE 收益可能十分明显。

---

# 3. 已有相关工作

## 3.1 MLP Linearization（最相关）

思想：

Linear → SwiGLU → Linear

近似为：

Linear

实验结论：

- Transformer 中很多中间层 MLP 可以直接线性化。
- 首尾层更依赖非线性。
- 中间层非线性重要性明显降低。

意义：

说明 Transformer 的非线性需求不是均匀分布的，可以选择性保留非线性。

与本研究关系：★★★★★

---

## 3.2 ReplaceMe

思想：

多个 Transformer Block

↓

一个 Linear Mapping

特点：

- Training-free
- Block Replacement
- 可减少约 25% Block
- 保留约 90% 性能

意义：

Transformer Block 存在大量冗余。

与本研究关系：★★★★☆

---

## 3.3 FlattenGPT

思想：

Layer Flattening

多个 Block

↓

更浅 Transformer

减少：

- LayerNorm
- Residual
- SwiGLU

出现次数。

意义：

减少层深，提高推理效率。

与本研究关系：★★★★☆

---

## 3.4 PowerSoftmax（IBM）

目的：

重新设计 Softmax，使其适合 FHE。

不是减少 Nonlinear 数量，而是修改 Nonlinear 形式。

采用：

Polynomial-friendly Softmax

特点：

- HE-friendly Transformer
- 面向 CKKS/FHE
- 可训练较大的 Transformer
- 目前仅论文公开，没有完整开源模型。

与本研究关系：★★★☆☆

---

## 3.5 CLAWS

思想：

FFN Activation Sparsity

很多神经元不参与计算。

减少：

FFN 实际计算量。

不是减少：

Activation 次数。

与本研究关系：★★★☆☆

---

## 3.6 Sparse Transformer

代表：

- DejaVu
- LLM in Flash

思想：

每个 Token 仅计算部分 FFN。

属于：

Sparse Computing。

与本研究关系：★★☆☆☆

---

# 4. 与已有工作的区别

已有工作主要关注：

- 非线性函数近似
- 层压缩
- Block 合并
- Sparse Activation

当前设想关注：

**减少 Linear 与 Nonlinear 的切换频率。**

重点优化：

- Ciphertext 生命周期
- Communication Round
- Encrypt/Decrypt 次数
- Bootstrapping 次数

属于系统级优化，而不仅是函数近似。

---

# 5. 推荐研究模型规模

## 50M

优点：

- 容易训练
- 成本最低

缺点：

Transformer 行为尚不稳定。

适合：

算法验证。

---

## 500M（推荐）

优点：

- Transformer 行为已经稳定。
- Attention、FFN、LayerNorm 与 Llama 基本一致。
- 训练成本仍可接受。
- 最适合作为论文实验平台。

推荐模型：

- Pythia-410M
- OPT-350M
- GPT-Neo-350M

---

## 1B

推荐模型：

- Llama 3.2 1B
- TinyLlama 1.1B
- Pythia 1B

适合：

最终实验验证。

---

## 7B

主要用于：

最终对比实验。

不建议作为算法开发平台。

---

# 6. 当前隐私计算研究现状

目前顶会大量研究：

- HE Inference
- MPC Inference
- TEE + AI
- Privacy-preserving ML

但模型规模主要集中：

- CNN
- MLP
- BERT

真正针对：

500M~7B LLM 的 HE 推理工作仍然较少。

说明：

LLM + AHE/FHE 推理仍存在较大研究空间。

---

# 7. 论文投稿方向

系统安全：

- ACM CCS（CCF A）
- USENIX Security（CCF A）
- NDSS（CCF A）
- IEEE S&P（CCF A）

机器学习系统：

- MLSys
- NeurIPS（Systems）

密码学：

- CHES
- Asiacrypt
- Crypto（更偏密码算法创新）

---

# 8. 当前必须验证的问题

1. 哪些 Layer 真正需要 Nonlinear？
2. 中间 Layer 是否可以全部或部分线性化？
3. 减少 Nonlinear 后 Perplexity 损失是多少？
4. 是否需要重新训练或蒸馏恢复性能？
5. AHE/FHE 推理是否真正减少：
   - Communication Round
   - Encrypt/Decrypt
   - Bootstrapping
   - End-to-End Latency

---

# 9. 当前研究路线

Stage 1：选择 500M Transformer（推荐 Pythia-410M）。

Stage 2：统计各 Layer Nonlinear 重要性。

Stage 3：逐层替换：
- SwiGLU → Linear
- Softmax → Approximation
- LayerNorm → Approximation

Stage 4：实验不同 Nonlinear 保留策略：
- 每层保留
- 每两层保留
- 每四层保留
- 仅首尾层保留

Stage 5：分析：
- Accuracy
- Perplexity
- AHE Cost
- Communication
- Ciphertext Size
- Bootstrapping 次数

Stage 6：建立 AHE/FHE 推理系统并与现有方案对比。

---

# 10. 核心创新点

已有工作主要解决：

- 非线性函数近似
- Layer Compression
- Block Compression
- Sparse Activation

当前设想解决：

**重新设计 Transformer 计算图，减少 Linear/Nonlinear 切换频率，从系统层面降低 AHE/FHE 推理中的通信、加解密和 Bootstrapping 开销。**

最终目标不是降低 GPU FLOPs，而是降低 **AHE/FHE 的整体推理成本（End-to-End Latency）**。