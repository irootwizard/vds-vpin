---
name: llm-verifiability-game-theory
overview: 系统性论证大语言模型可验证推理的可行性，把训练/推理成本、模型替换收益、AHE 上的计算量证明、稀疏矩阵/Merkle 电路内打开、trace/witness 伪造成本、抽样检测概率和押金罚没均衡统一到一个数学模型中，并与小参数 CNN 的 CP-SNARK 路线分离。
todos:
  - id: collect-literature
    content: 收集并摘录 LLM 可验证推理、抽样证明、TensorCommitments、VeriLLM、IMMACULATE、TAO/NAO、DeepProve、AHE/FHE 推理证明、稀疏矩阵证明、Merkle/VC 电路内打开等资料。
    status: completed
  - id: build-cost-model
    content: 建立 Llama 7B/13B/70B 的训练、prefill、decode、显存带宽和替换收益计算模型。
    status: completed
  - id: derive-game-model
    content: 推导作弊收益、伪造成本、检测概率、押金罚没和多轮审计的均衡条件。
    status: completed
  - id: analyze-ahe-proof
    content: 分析 AHE/FHE 上的大模型计算量证明方案，包括密文线性层、bootstrapping/非线性、同态矩阵乘、证明轨迹与现有 vPIN AHE-ECC 路线的兼容性。
    status: completed
  - id: analyze-sparse-merkle
    content: 分析稀疏矩阵、MoE、稀疏 attention、UsedIndices、Merkle/VC 电路内打开与稀疏 opening 的复杂度和安全边界。
    status: completed
  - id: compare-all-schemes
    content: 建立全方案对比矩阵：CP-SNARK、Merkle in-circuit、Tensor/KZG/IPA commitment、GKR/sumcheck、zkML lookup、TEE、optimistic fraud proof、抽样审计、复制计算。
    status: completed
  - id: design-protocol
    content: 设计 trace commitment、VRF 抽样、局部打开、局部验证、结算罚没和 verifier 激励协议。
    status: completed
  - id: write-docs
    content: 扩展或新增完整数学论证文档，并把总览文档链接到详细研究稿。
    status: completed
isProject: false
---

# 大模型可验证推理博弈论与全方案论证计划

## 研究边界
- 小参数 CNN：沿用 `docs/cp-snark/小参数CNN与大模型证明路线-数学论证.md` 中的 CP-SNARK/B′ 硬绑定路线。
- 大语言模型：单独建立“模型承诺 + trace commitment + 随机审计 + 局部证明 + AHE/FHE 可验证计算 + 博弈论激励”的可行性模型，不预设全量 zkML、AHE 或抽样方案一定最优。
- 目标模型默认选择 Llama 2/3 系列开源模型，至少覆盖 7B、13B、70B 三档，用于替换模型收益和计算量差异估算。
- 领域内方案全部纳入候选：cryptographic hard proof、AHE/FHE 推理证明、TensorCommitments、Merkle/VC 稀疏打开、GKR/sumcheck、lookup-based zkML、TEE、optimistic fraud proof、multi-prover/refereed delegation、随机审计与纯经济激励。

## 核心论证结构
1. 建立训练成本模型：使用 Chinchilla/Transformer FLOPs 公式，推导训练成本 `C_train ≈ 6ND`，并纳入 Llama 2 model card 的 GPU-hour 数据作为现实校准。
2. 建立推理成本模型：使用 decoder-only 近似 `C_infer ≈ 2N` FLOPs/token，并区分 prefill、decode、KV cache、显存带宽瓶颈。
3. 建立替换模型收益模型：比较 70B→13B、70B→7B、13B→7B、FP16→INT8/FP8、跳层/短路/缓存响应等策略的节省 `G=C_H-C_C`。
4. 建立伪造成本模型：分析伪造 `cm_trace`、隐藏状态、logits、decode path、局部 Freivalds 检查、Merkle/Tensor opening 的成本 `C_A`。
5. 建立检测概率模型：对抽样空间 `N`、作弊影响单元 `t`、抽样数 `k` 推导 `p_hit=1-C(N-t,k)/C(N,k)`，并扩展到多轮查询 `1-(1-p)^q`。
6. 建立博弈均衡条件：推导服务器诚实条件 `p(P+L)+C_A>G`，并反推最低押金、审计频率、验证者奖励和长期信誉损失。
7. 分析多方博弈：包括单服务器-单客户端、推理市场、多 verifier、一个诚实 verifier、懒验证者问题、peer-prediction/奖励一致性机制。
8. 分析 AHE/FHE 上的大模型计算量证明：密文线性层可证明性、非线性/softmax/LayerNorm 的瓶颈、bootstrapping 成本、证明轨迹大小、与 vPIN ElGamal-ECC 线性层证明的可迁移性。
9. 分析稀疏矩阵与 Merkle 电路内打开：MoE top-k、稀疏 attention、剪枝矩阵、低秩 adapter、LoRA/adapter 场景下的 `k_w << N_W` 条件，推导 `k_w log N_W` 何时优于全量承诺或 CP-SNARK。
10. 建立全方案复杂度矩阵：每种方案分别列出 setup、prove、verify、proof size、通信、模型隐私、输入隐私、soundness 类型、经济假设。
11. 给出协议设计：模型承诺、trace commitment、VRF challenge、局部打开、局部重算/小证明、AHE 证明接口、结算与罚没。
12. 给出不可行边界：哪些场景必须全量 zkML/TEE，哪些场景只能给概率/经济安全，哪些声明不能写进产品。

## 方案空间
- **全量 zkML / CP-SNARK**：硬 soundness，成本最高；适合小模型、离线高价值推理或分段递归。
- **AHE/FHE + 可验证计算**：保护输入隐私，但大模型非线性、softmax、LayerNorm、bootstrapping 与密文内存成本是瓶颈；需要判断只证线性层、只证局部层还是端到端。
- **Merkle / Vector Commitment 电路内打开**：严格绑定被使用权重；复杂度 `O(k_w log N_W C_H)`，仅当 `k_w << N_W` 或稀疏结构成立时适合大模型。
- **稀疏矩阵 / MoE / LoRA / Adapter 证明**：如果每次路由只用少量专家或 adapter，`UsedIndices` 可显著小于全模型，是 Merkle/VC 方案的主要适用场景。
- **TensorCommitments / KZG / IPA**：更适合张量结构和批量 opening，需要分析 trusted setup、pairing、模型隐私与证明大小。
- **GKR / Sumcheck / Freivalds**：适合大矩阵乘和局部线性检查，可降低 verifier 成本，但 prover 仍接近被证明子图大小。
- **Lookup zkML**：适合 softmax/GELU/LayerNorm 近似或量化非线性，需单独分析精度损失与表大小。
- **TEE + attestation**：工程成本低、性能好，但依赖硬件信任，可与随机 ZK spot-check 组合。
- **Optimistic fraud proof**：默认接受，挑战时二分 trace；低日常成本，但有挑战窗口和 verifier 激励问题。
- **随机审计 / 博弈论**：不能提供密码学零错误 soundness，但可用押金、重复审计、声誉损失使理性作弊期望收益为负。

## 需要更新或新增的文档
- 扩展 `docs/cp-snark/大语言模型博弈论可验证推理-数学设计.md`：从概要升级为完整研究稿。
- 保留 `docs/cp-snark/小参数CNN与大模型证明路线-数学论证.md` 作为总览，链接到完整研究稿。
- 可新增 `docs/cp-snark/llm-verifiable-inference-cost-model.md`，专门放公式、参数表、Llama 2/3 估算和敏感性分析。
- 可新增 `docs/cp-snark/llm-ahe-verifiable-compute-analysis.md`，专门分析 AHE/FHE 上的大模型推理和计算量证明可行性。
- 可新增 `docs/cp-snark/llm-sparse-merkle-opening-analysis.md`，专门分析稀疏矩阵、MoE、LoRA/Adapter 与 Merkle/VC 电路内打开的复杂度。
- 可新增 `docs/cp-snark/llm-verification-scheme-matrix.md`，专门做全方案对比矩阵和适用条件。

## 方法与资料
- 参考 Llama 2 model card：参数规模、训练 tokens、A100 GPU hours。
- 参考 Chinchilla scaling laws：`C_train≈6ND` 与 compute-optimal 数据比例。
- 参考 Transformer FLOPs 资料：`2N` FLOPs/token、prefill/decode、attention 与 MLP 成本。
- 参考 verifiable inference 论文：Proofs of Inference、VeriLLM、TensorCommitments、IMMACULATE、TAO/NAO、DeepProve、CommitLLM。
- 参考 FHE/AHE 推理资料：TFHE/CKKS/BFV、FHE-DiNN、CryptoNets、FHE Transformer 或 encrypted inference 相关工作，评估与 vPIN ElGamal-ECC 线性层证明的关系。
- 参考稀疏大模型资料：MoE、Mixtral、Switch Transformer、稀疏 attention、LoRA/Adapter，估算 `UsedIndices` 和动态路由验证成本。
- 参考承诺与证明后端：Merkle/Poseidon、KZG/IPA vector commitment、tensor commitment、GKR/sumcheck、lookup arguments、recursive SNARK。
- 把资料下载或缓存到本地后，整理成文档引用和公式来源。

## 输出形式
- 一份完整数学论证文档：包含定义、假设、定理/命题、推导、参数案例和结论边界。
- 一份 AHE/FHE 可验证大模型推理专项分析：明确哪些计算能在密文上做、哪些证明能复用、哪些部分不可行。
- 一份稀疏 Merkle/VC opening 专项分析：给出 `k_w`、`N_W`、树深、hash gadget 成本、proof size 和电路约束。
- 一份全方案矩阵：按安全强度、成本、工程复杂度、模型隐私、输入隐私、产品适用性排序。
- 一份协议草案：包含消息时序、承诺对象、抽样算法、验证算法、结算算法。
- 一组示例计算：例如 70B 替换为 7B 时，给定抽样概率与罚没金额，服务器是否有作弊动机。

## 风险与注意事项
- 博弈论安全不是密码学 soundness，必须明确写成“理性安全/概率审计”。
- 随机抽样必须在 trace commitment 之后产生，否则服务器可适配挑战。
- 输出文本/日志概率分布检测不是严格证明，只能作为风控信号。
- 大模型硬证明若采用 zkML，需要单独后端，不应塞进当前 Network A 的 EC gadget Spartan 路线。
- AHE/FHE 可以解决输入隐私，但不自动解决计算量证明；仍需 trace binding、proof 或审计机制。
- 稀疏 Merkle 只有在 `k_w << N_W` 时有复杂度优势；对 dense Transformer 全层权重，逐叶 opening 仍不可行。
- MoE/稀疏路由会引入“路由是否诚实”的额外证明或审计问题，不能只证明被打开专家权重。