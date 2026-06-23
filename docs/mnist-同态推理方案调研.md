# MNIST 同态 / 密态推理方案调研（近年文献与实现）

> **范围**：在 **MNIST** 上完成**单张或批量图像分类**的隐私保护推理方案；以**全同态加密（FHE）**及**加法同态 + 证明（vPIN 类）**为主，**MPC / 混合协议**单独标注。  
> **时间口径**：表中「单图延迟」优先取论文 **wall-clock latency（总耗时 / 批大小）**；若仅报告 **amortized time**（SIMD 批处理摊销）会单独注明。  
> **参数量**：多数论文只给网络结构；表中「可训练参数」为按结构推算或论文明示，**固定卷积核不计入**时会注明。  
> **算力口径**：各方案**硬件不同，秒数不可直接横比**；完整 CPU/GPU/内存见 **§2**（汇总表 **§2.0**），本仓库 AHE 实测见 **§2.13**。

---

## 1. 总览对比表

| 年份 | 方案 | 密码体制 | 网络结构（MNIST） | 可训练参数量（约） | 同态运算量 / 备注 | 单图推理时间 | 实验平台（§2） | 准确率 | 论文 | 代码 / 仓库 |
|------|------|----------|-------------------|-------------------|-------------------|--------------|--------------|--------|------|-------------|
| 2016 | **CryptoNets** | YASHE′（levelled FHE） | 5×5 conv×2 + square + pool + FC→100 + square + FC→10（推理简化为 5 层） | ~8.5×10⁴（简化后 100×845 线性层为主） | ~2.9×10⁵ 同态乘法 | **570 s**（SEAL 复现）；原文 **250 s** / batch=4096 摊销 **~61 ms** | §2.1 | 99.0% | [ICML 2016](https://proceedings.mlr.press/v48/gilad-bachrach16.html) · [arXiv:1412.6181](https://arxiv.org/abs/1412.6181) | [Microsoft/CryptoNets](https://github.com/microsoft/CryptoNets) |
| 2018 | **Faster CryptoNets (FCryptoNets)** | BFV（SEAL） | 与 CryptoNets 同类浅层 CNN | 同 CryptoNets 量级 | 减少深度 / 优化 packing | **39.1 s**（单图，batch=1） | §2.2 | 98.71% | [WAHC 2018](https://www.usenix.org/conference/woot18/presentation/chou) · [ePrint 2018/1084](https://eprint.iacr.org/2018/1084) | 论文配套实现（见 USENIX 页） |
| 2018 | **E2DM** | BFV + 打包（非纯 FHE 端到端） | CryptoNets 类 | 同左 | 64 图一批 | **0.45 s** 摊销（28.59 s / 64 图） | §2.3 | 98.01% | [CCS 2018](https://doi.org/10.1145/3243734.3243852) | [s0n0b1/E2DM](https://github.com/s0n0b1/E2DM) |
| 2019 | **LoLa** | BFV（SEAL 2.3） | 与 CryptoNets **相同拓扑** | 同 CryptoNets | 新 ciphertext packing，降 HOP | **2.2 s** | §2.4 | 98.95% | [ICML 2019](https://proceedings.mlr.press/v97/brutzkus19a.html) · [arXiv:1812.10659](https://arxiv.org/abs/1812.10659) | 无官方仓库；可参考 [SEAL](https://github.com/microsoft/SEAL) |
| 2019 | LoLa-Small / LoLa-Dense | BFV | 浅层变体 / 稠密输入变体 | 更少 / 同拓扑 | — | **0.29 s** / **7.2 s** | §2.4 | 96.92% / 98.95% | 同上 supplementary | — |
| 2019 | CryptoNets 2.3（LoLa 复现基线） | BFV | 同 CryptoNets | 同左 | SEAL 多线程 | **24.8 s** | §2.4 | 98.95% | LoLa 论文 Table 2 | — |
| 2021 | **HCNN + A\*FV** | BFV + GPU（A\*FV） | 5×5 conv×5 → square → 5×5 conv×50 → square → FC×10 | **~1.44×10⁴** | CRT 多通道；N=2¹⁴ | **5.16 s** 总时延；**0.63 ms** 摊销（SIMD） | §2.5 | 99.0% | [arXiv:2102.06813](https://arxiv.org/abs/2102.06813) | [dawn-crypto-lab/HCNN](https://github.com/dawn-crypto-lab/HCNN) |
| 2021 | **Efficient CNN Building Blocks**（PPAI 类） | CKKS（HElib/C++） | 28×5×5 conv + FC（权重可加密） | 大于 CryptoNets | K=16384 SIMD 批 | **561 s** wall；**34 ms** 摊销；单图 **8.8 s** / **2.5 s** | §2.6 | ~99% | [arXiv:2102.00319](https://arxiv.org/abs/2102.00319) | 见论文作者页 |
| 2021 | **CRYPTONETS-HS** | BFV + Halevi–Shoup | CryptoNets 拓扑 | 同 CryptoNets | HOP 较 LoLa 再降 ~2× | 秒级（见原文 Table） | SEAL，与 LoLa 同档 CPU 云主机 | ~98.95% | [arXiv:2110.08321](https://arxiv.org/abs/2110.08321) | — |
| 2022 | **FFConv-TinyNet** | BFV（SEAL） | TinyNet 浅层 CNN | 小于 CryptoNets | 优化首层 conv | **0.37 s** | §2.4（同 LoLa 参考机） | 与 LoLa-TinyNet 可比 | [arXiv:2102.03494](https://arxiv.org/abs/2102.03494) | — |
| 2023 | **TT-TFHE** | TFHE（Concrete） | TTnet 浅层 CNN | 论文定制 | lookup table 自举 | **4.4 s**（4 CPU 核） | §2.7 | 98.1% | [arXiv:2302.01584](https://arxiv.org/abs/2302.01584) | [zama-ai/concrete](https://github.com/zama-ai/concrete) |
| 2023 | **GPU FHEW/TFHE** | FHEW/TFHE（OpenFHE） | MLP 784→30→10 | ~2.4×10⁴ | GPU 自举 | **0.04 s**（1×RTX4090） | §2.8 | 96–97% | [TCHES 2023](https://tches.iacr.org/index.php/TCHES/article/view/11931) | OpenFHE 扩展 |
| 2023 | **SHE（BP 网络）** | 定制 FHE | 784→30→10 MLP | **~2.4×10⁴** | 极浅 MLP | **0.14 s** | §2.9 | <1% 精度损失 | [ePrint 2023/647](https://eprint.iacr.org/2023/647) | — |
| 2020 | **TenSEAL** | CKKS / BFV | **库**（算子微基准） | 取决于用户模型 | 微基准 ms 级（见 §4） | **库级** | §2.10 | — | [arXiv:2003.06714](https://arxiv.org/abs/2003.06714) | [OpenMined/TenSEAL](https://github.com/OpenMined/TenSEAL) |
| 2025 | **FHEON** | CKKS（OpenFHE RNS） | **LeNet-5** | **~6.17×10⁴** | 可配置 CNN 栈 | **13 s**；内存 **4.2 GB** | §2.11 | 98.5% | [arXiv:2510.03996](https://arxiv.org/abs/2510.03996) | [stamcenter/fheon](https://github.com/stamcenter/fheon) |
| 2024+ | **HEIR + OpenFHE** | CKKS | MLP on MNIST（示例） | 视 mlir 模型 | 编译器路线 | **~30 s** / **~6 min** | 社区 issue（单机，RingDim 可变） | — | [google/heir#1232](https://github.com/google/heir/issues/1232) | [google/heir](https://github.com/google/heir) |
| 2024 | **vPIN 论文** | EC-AHE + CP-SNARK | Network 1–5 / LeNet | LeNet **~61,706** | 7508 pt-mult + 16864 pt-add（LeNet） | **proving 266–1002 s**（CNN 1–5）；LeNet **10699 s** | §2.12 | 与明文接近 | [arXiv:2411.07468](https://arxiv.org/abs/2411.07468) | [vt-asaplab/vPIN](https://github.com/vt-asaplab/vPIN) |
| 2024 | **vPIN 本仓库 AHE** | EC 加法同态（WS） | **Network A** | **1,210** | ~1.86×10⁴ pt-mult + ~1.83×10⁴ pt-add | **~91 s**（`crypto_infer_ms`） | §2.13（本机实测） | parity ✓ | 同上 | 本仓库 |

### 混合 / 非纯 FHE（对照）

| 方案 | 类型 | MNIST 延迟（约） | 论文 | 仓库 |
|------|------|------------------|------|------|
| Gazelle | HE + GC | 毫秒级（通信轮次多） | [USENIX 2018](https://www.usenix.org/conference/usenixsecurity18/presentation/juvekar) | [mhsijaz/Gazelle](https://github.com/mhsijaz/Gazelle) |
| MiniONN | HE + GC | 秒级 | [CCS 2017](https://doi.org/10.1145/3133956.3134056) | — |
| XONN | GC 为主 | 秒级 | [NDSS 2019](https://www.ndss-symposium.org/ndss-paper/xonn-xnor-based-oblivious-deep-neural-network-inference/) | [s0n0b1/XONN](https://github.com/s0n0b1/XONN) |

---

## 2. 实验环境与算力规格（论文原文 + 本机确认）

> 下表字段：**平台类型**、**CPU**、**GPU**、**内存**、**OS/库**、**并行度**、**算力档位（粗估）**。  
> 「算力档位」仅用于**同密码体制内的粗排序**，跨 FHE/TFHE/EC 不可比。

### 2.0 环境汇总一览（便于横向对照平台）

| 方案 | CPU / 算力 | GPU | 内存 | 密码库 | 并行 / batch | MNIST 单图时间 |
|------|------------|-----|------|--------|--------------|----------------|
| CryptoNets 原文 | Xeon E5-1620 **4T@3.5GHz** | 无 | 16 GB | YASHE′ | batch **4096** | **250 s**（摊销 **~61 ms**） |
| CryptoNets SEAL 复现 | E5-1620 3.5 GHz | 无 | 16 GB | SEAL BFV | — | **570 s** |
| FCryptoNets | i7-5930K **12T@3.5GHz** | 无 | 48 GB | SEAL | batch=1 | **39.1 s** |
| E2DM | MacBook i9 **4C@2.3GHz** | 无 | — | SEAL | 64 图/批 | **0.45 s** 摊销 |
| LoLa / FFConv | Azure B8ms **8 vCPU** | 无 | 32 GB | SEAL 2.3 | 多线程 | **2.2 s** / **0.37 s** |
| HCNN A\*FV | Xeon Platinum **26C@2.1GHz** | **V100 16GB** | 187 GB | A\*FV+SEAL | SIMD N=2¹⁴ | **5.16 s**（摊销 **0.63 ms**） |
| PPAI Building Blocks | POWER9 **112 逻辑核** | 无 | **511 GB** | HElib CKKS | K=16384 | **561 s** / 摊销 **34 ms** |
| TT-TFHE | i7-8650U **4C@1.9GHz**（限 4 核） | 无（训练用 3090） | 16 GB | Concrete TFHE | 4 CPU 核 | **4.4 s** |
| GPU FHEW/TFHE | Threadripper **3970X 32C** | **RTX 4090** | 128 GB | OpenFHE | GPU 自举 | **0.04 s** |
| SHE | Milan 7313P **16C@3.0GHz** | 无 | — | 定制 FHE | — | **0.14 s** |
| TenSEAL 微基准 | EC2 c4.2xlarge **8 vCPU@2.9GHz** | 无 | 15 GiB | SEAL CKKS | — | 算子 ms 级 |
| FHEON LeNet | Ryzen 5900X **12C** | 无 | 64 GB | OpenFHE | 单线程 CPU | **13 s** |
| vPIN 论文 | 客户端 M1 Pro；服务端 **8360Y 48C@2.4GHz** | 无 | 16 / **256 GB** | libspartan | 多线程证明 | proving **266–1002 s** |
| **vPIN 本仓库 AHE** | **i5-13500H 12C/16T@2.6GHz** | RTX 5060 Ti（**未用**） | **15.7 GB** | Python EC | 单图 WS | **~91 s** |

### 2.1 CryptoNets（2016，原文）

| 项 | 规格 |
|----|------|
| 平台 | 单机 PC |
| CPU | Intel Xeon E5-1620，**1 物理核/4 线程 @ 3.5 GHz**（论文写 single CPU） |
| 内存 | **16 GB** |
| OS | Windows 10 |
| 库 | 微软内部 YASHE′ 实现（非 SEAL） |
| 并行 | SIMD batch **4096** 图/批 |
| 算力档位 | 入门级服务器 CPU（2012 代），**无 GPU** |

### 2.2 Faster CryptoNets（2018）

| 项 | 规格 |
|----|------|
| CPU | Intel Core i7-5930K @ **3.5 GHz**（6 核 12 线程 Haswell-E） |
| 内存 | **48 GB** |
| 库 | Microsoft SEAL（BFV） |
| 并行 | batch=1（无 packing 摊销） |
| 算力档位 | 高端桌面/workstation CPU，**无 GPU** |

### 2.3 E2DM（2018）

| 项 | 规格 |
|----|------|
| 平台 | MacBook Pro 笔记本 |
| CPU | Intel Core i9，**4 核 @ 2.3 GHz** |
| 库 | SEAL（BFV） |
| 算力档位 | 移动工作站，**无 GPU** |

### 2.4 LoLa / CryptoNets 2.3 / FFConv（2019–2022 共用参考机）

| 项 | 规格 |
|----|------|
| 平台 | Azure **Standard B8ms** 云 VM |
| vCPU | **8**（Burstable，Intel 至强可扩展族） |
| 内存 | **32 GB** |
| 库 | SEAL **2.3**（LoLa、FFConv 论文均写明） |
| 并行 | LoLa 多线程；FFConv 同机 |
| 算力档位 | 中等云 CPU，**无 GPU**；LoLa 论文 Table 2 的 **2.2 s / 24.8 s / 0.37 s** 均在此机 |

### 2.5 HCNN + A\*FV（2021）

| 项 | 规格 |
|----|------|
| CPU | Intel **Xeon Platinum**，**26 核** @ **2.10 GHz**，**187.5 GB** DDR4（Table 8） |
| GPU（单卡实验） | NVIDIA **V100**，CC **7.0**，**16 GB** HBM2，5120 CUDA 核 @ 1.38 GHz |
| GPU 集群 | **1×V100 + 3×P100**（16 GB×3）；CIFAR 可多机 CRT |
| 库 | SEAL（CPU 基线）+ **A\*FV**（GPU BFV） |
| MNIST 显存 | 论文：**16 GB 足够**装下 MNIST 全层密文 |
| 算力档位 | 数据中心 CPU + **Volta 级 GPU**；**5.16 s** 为 **V100 单卡** A\*FV |

**HCNN 论文 Table 11 其它对比机（非本方案主机）**：CryptoNets 用 E5-1620 3.5 GHz / 16 GB；E2DM 用 MacBook i9 4 核 2.3 GHz；FCryptoNets 用 i7-5930K 3.5 GHz / 48 GB。

### 2.6 Efficient CNN Building Blocks / PPAI（2021，CKKS）

| 项 | 规格 |
|----|------|
| 平台 | IBM Cloud **ppc64le POWER9** 虚拟机 |
| CPU | **112 逻辑 CPU**（14 socket × 1 core × **8 线程**/核） |
| 内存 | **511 GB** |
| OS | Fedora 32 |
| 库 | **HElib 1.0.1**（C++），CKKS，m=2¹⁶，K=**16384** slots |
| 算力档位 | 大型内存优化型 **POWER9**，**非 x86**；与 SEAL/BFV 论文 **不可直接比 wall-clock** |

### 2.7 TT-TFHE（2023）

| 项 | 规格 |
|----|------|
| CPU | Intel Core **i7-8650U** @ **1.90 GHz**（4 物理核 / 8 线程，低功耗移动 U 系列） |
| 内存 | **16 GB** |
| GPU | 4×RTX 3090（**仅训练**，FHE 推理不用 GPU） |
| FHE 推理 | **Concrete v2.10**，限制 **4 CPU 核**，关闭 Turbo Boost |
| 算力档位 | 低端笔记本 CPU 四核；**4.4 s** 为 **4 核 FHE** |

### 2.8 GPU FHEW/TFHE 自举加速（TCHES 2023，MNIST MLP）

| 项 | 规格 |
|----|------|
| CPU | AMD Ryzen Threadripper **3970X**（**32 核 / 64 线程**） |
| 内存 | **128 GB** |
| GPU | NVIDIA **RTX 4090**（MNIST **0.04 s** 为 **1–2×4090**；对比 [LLZ+24] **0.14 s**） |
| 库 | OpenFHE **1.0.4** |
| 安全 | **128-bit**；隐藏层 30 神经元 MLP |
| 算力档位 | 高端桌面 + **Ada Lovelace 旗舰 GPU** |

### 2.9 SHE（ePrint 2023/647）

| 项 | 规格 |
|----|------|
| CPU | AMD **Milan 7313P** @ **3.0 GHz**，**16 核** |
| 模型 | 784→30→10 BP 网络 |
| 算力档位 | 服务器级 Zen3，**无 GPU** |

### 2.10 TenSEAL（2020，算子微基准）

| 项 | 规格 |
|----|------|
| 平台 | AWS **EC2 c4.2xlarge** |
| vCPU | **8** @ **2.9 GHz**（Intel Xeon E5-2666 v3） |
| 内存 | **15 GiB** |
| OS | Ubuntu 20.04，Python 3.8 |
| 算力档位 | 2014 代云 CPU，**无 GPU** |

### 2.11 FHEON（2025）

| 项 | 规格 |
|----|------|
| MNIST LeNet 主实验 | AMD **Ryzen 9 5900X**（**12 核**），**64 GB** RAM，**消费级 CPU** |
| 大规模对照实验 | AMD **EPYC 7763**（**64 核**）+ NVIDIA **A100-SXM4-80GB**，**200 GB** RAM |
| 库 | **OpenFHE**（CKKS RNS） |
| MNIST | **13 s**，**4.2 GB** 峰值内存 |
| 算力档位 | 中高端桌面（MNIST）vs 数据中心（CIFAR/ResNet） |

### 2.12 vPIN 论文实验平台（ACSAC 2024）

| 角色 | 规格 |
|------|------|
| **客户端** | MacBook Pro 2021，Apple **M1 Pro @ 3.2 GHz**，**16 GB** |
| **服务端（证明）** | Intel **Xeon Platinum 8360Y** @ **2.40 GHz**，**48 核**，**256 GB** |
| 证明库 | **libspartan**，**多线程** proving/verify |
| MNIST LeNet | **proving 10699 s**，verify **15.9 s**，proof **2339 KB**；**7508** pt-mult + **16864** pt-add |
| Network 1–5 | proving **266–1002 s**（含 AHE + SNARK，非纯同态） |
| 算力档位 | 客户端 ARM 笔记本 + 服务器 **Ice Lake 48 核** |

### 2.13 本仓库 vPIN AHE 实测环境（2026-06-23 本机确认）

| 项 | 规格 |
|----|------|
| 机型 | 笔记本（Windows **10.0.26200**） |
| CPU | **13th Gen Intel Core i5-13500H**：**12 物理核 / 16 逻辑线程**，基频 **2.6 GHz**（P+E 混合） |
| 内存 | **15.7 GB** 可用 |
| GPU | **NVIDIA GeForce RTX 5060 Ti**（**AHE 热路径未使用 GPU**）；核显 Iris Xe |
| 软件栈 | Python **3.x**（`.venv`），`vpin-backend` WS + `vpin_client ahe-infer` |
| 负载 | 单图官方 MNIST，`cnn-mnist-trained`（Network A） |
| 结果 | `crypto_infer_ms` **≈91 s**（优化后）；`preprocess_ms` **≈2 ms** |
| 算力档位 | 2023 代移动 **i5 + 独显**，但 AHE 为 **纯 Python EC 单线程/少并行**，未绑 GPU |

**与论文服务器对比（粗估）**：本机 CPU 单核睿频与 Xeon 8360Y 同代，但 **AHE 实现为 Python 参考路径、无 48 核 Spartan 并行**；**91 s 仅同态 WS 会话**，不含论文 **266–1002 s** 证明时间。

### 2.14 算力归一化参考（仅供同体制粗排）

| 档位 | 代表硬件 | 典型 MNIST 单图（同体制） |
|------|----------|---------------------------|
| 无 GPU 云 CPU 8 核 | Azure B8ms | LoLa **2.2 s**（BFV） |
| 数据中心 CPU 26 核 | Xeon Platinum + SEAL | HCNN CPU 路径 **数十～数百 s** 级 |
| 单卡 Volta V100 | A\*FV | HCNN **5.16 s** |
| 单卡 RTX 4090 | FHEW/TFHE 自举 | MLP **0.04 s** |
| 12 核桌面 Zen3 | Ryzen 5900X + OpenFHE | LeNet **13 s**（CKKS） |
| 48 核 + Spartan | Xeon 8360Y | vPIN **proving** 分钟～小时级 |
| 笔记本 Python EC | i5-13500H（本机） | vPIN AHE **~91 s** |

---

## 3. 代表性方案展开

### 3.1 CryptoNets（2016）— 基线

- **结构（推理）**：28×28 输入 → 5×5 conv stride 2（5 maps）→ square → pool → 合并线性层 100×845 → square → 10 类输出。  
- **同态乘法**：约 **290,000** 次（论文摘要）。  
- **时间**：原文 Microsoft 实现约 **250 s**；HCNN 论文用 SEAL 复现 **570 s**（80-bit）。层间耗时示例：首层 conv **81 s**，首 square **81 s**，pool **127 s**，次 square **10 s**，输出层 **1.6 s**。  
- **吞吐**：约 **589,000 predictions/hour**（与 ~6 s/图摊销一致）。  
- **仓库**：[microsoft/CryptoNets](https://github.com/microsoft/CryptoNets)（YASHE′ 方案；与 SEAL/BFV 复现不可直接比秒数）。

### 3.2 LoLa（2019）— 同拓扑大幅降延迟

- **核心**：在 BFV 上对中间张量做 **ciphertext packing**（convolutional / interleaved 表示），使 CryptoNets 同级网络从 **205 s → 2.2 s**（相对原始 CryptoNets **~93×**）。  
- **变体**：LoLa-Small **0.29 s**（精度 96.92%）；LoLa-Dense **7.2 s**。  
- **参数量**：与 CryptoNets 相同拓扑，见 §2.1。

### 3.3 HCNN / A\*FV（2021）— 当前 FHE 经典强基线

- **MNIST 结构**（训练与测试同构）：

  | 层 | 描述 | 输出尺寸 |
  |----|------|----------|
  | Conv | 5 个 5×5，stride (2,2) | 12×12×5 |
  | Square | 逐元素平方 | 12×12×5 |
  | Conv | 50 个 5×5，stride (2,2) | 4×4×50 |
  | Square | 逐元素平方 | 4×4×50 |
  | FC | 800 → 10 | 10 |

- **参数量估算**：5×5×5 + 50×5×5×5 + 800×10 + bias ≈ **1.44×10⁴**。  
- **时间**（Table 11）：总延迟 **5.16 s**（λ≈82），摊销 **0.63 ms**；相对 CryptoNets **110×** 加速。  
- **仓库**：[dawn-crypto-lab/HCNN](https://github.com/dawn-crypto-lab/HCNN)。

### 3.4 FHEON（2025）— 可配置 CKKS 框架

- **MNIST 模型**：标准 **LeNet-5**（约 **61,706** 可训练参数）。  
- **单图**：**13 s**，**4.2 GB** 内存，准确率 **98.5%**（明文 98.8%）。  
- **仓库**：[stamcenter/fheon](https://github.com/stamcenter/fheon)。

### 3.5 vPIN / 本仓库 Network A — 非 FHE 的加法同态轨

- **定位**：论文主路径为 **EC 上加法同态线性层 + 客户端验证 SNARK**，**不是** BFV/CKKS 全同态。  
- **Network A 结构**：固定 Sobel 型 3×3 conv（不训练）→ ReLU（客户端）→ 4×4 sum-pool → shift → FC **64→16** → ReLU+shift → FC **16→10**。  
- **可训练参数**：64×16+16 + 16×10+10 = **1,210**。  
- **本仓库实测**（Python `homomorphic_network_a.py`，优化后）：`crypto_infer_ms` **≈91 s**（单张官方 MNIST）；瓶颈为 EC 标量乘循环、BSGS、WS 序列化。  
- **论文报告**：端到端 **proving 266–1002 s**（Network A–E，含 CP-SNARK），**未单独给出纯 AHE 秒级**。  
- **相关文档**：[ahe-e2e-实现说明.md](./ahe-e2e-实现说明.md)、[network-a-official-mnist-ahe-分析.md](./network-a-official-mnist-ahe-分析.md)。

---

## 4. TenSEAL：库级性能（非完整 MNIST 端到端）

TenSEAL 论文给出 **CKKSVector** 在 EC2 c4.2xlarge 上的算子延迟（多项式模 **8192**，系数模 **200 bit**），例如：

| 算子 | 形状 [8192] |
|------|-------------|
| square | ~8.5 ms |
| multiply | ~8.8 ms |
| dot | ~56 ms |
| conv2d_im2col | 见附录 A.5 |

完整 MNIST CNN 端到端时间需自行用 [OpenMined/TenSEAL](https://github.com/OpenMined/TenSEAL) 拼装；社区常见 LeNet 级 demo 在 **秒～分钟级**（视 ring dimension 与安全参数而定）。

---

## 5. 对比阅读注意事项

1. **密码体制不可横比**：YASHE′、BFV、CKKS、TFHE、EC 加法同态的「一次乘法」成本差几个数量级。  
2. **摊销 vs 单图**：CryptoNets / HCNN 利用 **SIMD slot packing**（N=2¹⁴ 等），**amortized time** 可比单图低 **10³–10⁵** 倍。  
3. **权重是否加密**：PPAI 类工作区分权重明文（**2.5 s**）与密文（**8.8 s**）。  
4. **网络深度与参数量**：浅层（LoLa-Small、SHE-M LP）可达 **亚秒**；LeNet-5（~62k 参数）在 CKKS 上多为 **10 s 量级**；CryptoNets 级（~10⁵ 参数）未优化常 **>200 s**。  
5. **本仓库 vPIN**：目标为 **可验证** 密态推理，AHE 仅覆盖线性层；与纯 FHE 方案目标不同，秒数不宜与 CKKS LeNet 直接比「谁更快」，而应分 **纯同态** 与 **同态+证明** 两类。

---

## 6. 推荐阅读顺序

1. 入门：**CryptoNets** → **LoLa**（理解 packing 为何带来 10×～100× 加速）。  
2. FHE 工程基线：**HCNN**、**Faster CryptoNets**。  
3. 现代 CKKS 框架：**TenSEAL**、**FHEON**、**OpenFHE** / **HEIR**。  
4. 可验证推理：**vPIN 论文** + 本仓库 `docs/ahe-e2e-实现说明.md`。

---

## 7. 参考文献（BibTeX 友好链接）

| 简称 | 链接 |
|------|------|
| CryptoNets | https://arxiv.org/abs/1412.6181 |
| LoLa | https://arxiv.org/abs/1812.10659 |
| Faster CryptoNets | https://eprint.iacr.org/2018/1084 |
| E2DM | https://doi.org/10.1145/3243734.3243852 |
| HCNN | https://arxiv.org/abs/2102.06813 |
| PPAI Building Blocks | https://arxiv.org/abs/2102.00319 |
| CRYPTONETS-HS | https://arxiv.org/abs/2110.08321 |
| FFConv | https://arxiv.org/abs/2102.03494 |
| TenSEAL | https://arxiv.org/abs/2003.06714 |
| FHEON | https://arxiv.org/abs/2510.03996 |
| TT-TFHE | https://arxiv.org/abs/2302.01584 |
| vPIN | https://arxiv.org/abs/2411.07468 |
| Gazelle | https://www.usenix.org/conference/usenixsecurity18/presentation/juvekar |

---

*文档版本：2026-06-23（§2 实验环境与本机算力已核对）；论文数据来自原文 Table/§Evaluation，本仓库 AHE 行来自 `ahe-infer --timing` + `Win32_Processor` 本机查询。*
