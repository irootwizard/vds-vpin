# 新模型 AHE 客户端-服务端交互流程设计

> **版本**：2026-06-30  
> **适用模型**：`new_lenet_mnist`（LeNet5/MNIST）、`new_lenet`（LeNet5/CIFAR-10）、`new_resnet`（ResNet18/CIFAR-10）  
> **参考**：`docs/ahe/ahe-e2e-实现说明.md`、`docs/network-a/network-a-批次截断算法设计.md`、`model_training/network_lenet/truncation_config.py`

---

## 0. 加密方案说明

本项目 AHE 使用**椭圆曲线指数 ElGamal（ECC 指数ElGamal）**，而非 Paillier。

| 属性 | ECC 指数ElGamal（本项目） |
|------|--------------------------|
| 密文结构 | $(c_1, c_2) = (rG,\; mG + rH)$，两个 EC 点 |
| 同态加 | 分量点加：$(c_1+c_1',\; c_2+c_2')$ → 明文 $m_1+m_2$ |
| 标量乘 | $k\odot(c_1,c_2) = (kc_1, kc_2)$ → 明文 $km$ |
| 解密 | 代数步 $\beta = c_2 - x c_1 = mG$，再 BSGS 求 $m$（需 $|m| < 10^{13}$） |
| 不支持 | 密文×密文（对应明文乘法）→ 非线性运算必须回客户端 |

密码学细节见 `docs/cryptography/指数ElGamal同态加密-数学推导与实现指南.md`。

---

## 0′. 与 network_a 的关键差异（必读）

| 项目 | network_a | 三个新模型 |
|------|-----------|-----------|
| 卷积核 | **固定小整数**（0,1,2），不乘 2^16 | **训练所得浮点**，量化到 f=16 |
| 卷积后尺度 | f=16（整数核不增加 scale） | **f=32**（weight f=16 × input f=16） |
| after_conv 客户端动作 | `relu`（from_bits=16，无需 shift） | **`relu_then_shift`**（from_bits=32→16） |
| Pool | 4×4 sum pool，服务端做 | 2×2 avg pool（LeNet）/ 4×4 avg（ResNet） |
| BatchNorm | 无 | ResNet 有，需**离线 BN Folding** |
| 残差连接 | 无 | ResNet 有，**服务端做密文加法** |

> **核心约束**：本项目使用**椭圆曲线指数 ElGamal（ECC 指数ElGamal）** 加性同态加密，支持密文+密文点加（明文加法）、明文标量 k 乘密文点（明文标量乘）。**不支持**密文×密文运算（对应明文乘法），因此 **ReLU 必须由客户端完成**，任何非线性运算均无法在服务端用密文近似替代。BatchNorm 在推理期为线性变换（可 fold），AvgPool 是线性（可服务端或客户端做）。
>
> **ECC 特有约束**：解密需两步——先代数消元得 $\beta = c_2 - x \cdot c_1 = mG$，再 BSGS 求离散对数恢复 $m$。BSGS 要求 $|m| < m_{bs}^2 \approx 10^{13}$（`BSGS_LIMIT`）；超出此范围解密失败。Paillier 无此限制，本方案所有解密点（包括末端 argmax 的输出）均需满足此约束。

---

## 1. 全局常数与符号

```text
F         = 16     定点输入小数位数
inv_bits  = 10     pool 定点倒数位数
k         = 2      LeNet pool 窗口大小（2×2）
f_pool    = F + log2(k²) + inv_bits = 16 + 2 + 10 = 28   （2×2 pool 后尺度）
f_fc      = F + F = 32                                     （FC/卷积后尺度，权重 f=16）
f_pool4   = F + log2(4²) + inv_bits = 16 + 4 + 10 = 30   （ResNet 4×4 pool 后尺度）

BSGS_LIMIT  ≈ (3.2×10⁶)² ≈ 10¹³   解密安全上限
INT32_LIMIT = 2³¹ − 1               重加密前幅度上限
```

---

## 2. 关键优化：Pool 移到客户端（减少 2 次交互）

**适用模型**：new_lenet_mnist、new_lenet（不适用 ResNet，ResNet 无中间 pool）

**原理**：

标准做法（2 次交互/conv+pool 对）：
```
Server: conv → 发送密文(f=32) → Client: relu_then_shift(32→16) → 重加密
→ Server: pool → 发送密文(f=28) → Client: shift(28→16) → 重加密
```

优化做法（1 次交互/conv+pool 对，pool 在客户端明文域执行）：
```
Server: conv → 发送密文(f=32) → Client: decrypt → relu → pool_plaintext → shift(28→16) → 重加密
```

**为什么合法**：
- Pool 是确定性线性操作（client 知道窗口大小和步长）
- Client 已经在解密，不增加额外明文曝露
- Server 不执行 pool（从协议中移除）→ 节省一轮 WS 通信

**LeNet 节省**：从 6 次减少到 **4 次重加密**。

---

## 3. new_lenet_mnist（LeNet5 / MNIST / 1×32×32）

### 3.1 模型架构

```
input: 1×32×32 (f=16)
c1: Conv2d(1→6, 5×5)    → ReLU → AvgPool(2,2)  → 6×14×14
c2: Conv2d(6→16, 5×5)   → ReLU → AvgPool(2,2)  → 16×5×5
c3: Conv2d(16→120, 5×5) → ReLU                  → 120   (5×5核恰好覆盖全图，等价于 FC(400,120))
f4: Linear(120→84)      → ReLU                  → 84
f5: Linear(84→10)                                → 10  argmax
```

### 3.2 数据预处理（客户端）

| 步骤 | 操作 |
|------|------|
| 原始 | uint8 28×28 灰度 |
| 归一化 | /255 → pad 32×32 → per-image min-max → ×2^16 → int32 |
| 加密 | Enc(input) at f=16 |

### 3.3 权重准备（服务端，离线）

```
conv1_weight: (6,1,5,5) float → ×2^16 → int   # real_to_fixed_point(w, bits=16)
conv1_bias:   (6,)      float → ×2^32 → int   # bias 在 f=32 尺度（与 conv 输出对齐）
conv2/c3/fc 同理
```

> bias 为什么用 f=32：conv 输出 f=32，bias 需与输出尺度对齐才能做密文+明文加法。

### 3.4 交互时序（优化版，4 轮重加密）

```text
Client                                       Server
  |  SessionStart / ModelSelect              |
  |<──────────── ModelSelectAck ────────────|  (truncation_plan)
  |  PublicKey                               |
  |  Enc(input) initial (f=16, 1×32×32)     |
  |─────────────────────────────────────────>|
  |                                          | conv1(1→6,5×5) → 6×28×28 (f=32)
  |<─── TruncateRequest(π1, relu+pool+shift) |  ← 含 6×28×28 密文
  | Dec → relu → pool2×2 → shift(28→16)     |
  | Re-enc(6×14×14, f=16)                   |
  |─────────────────────────────────────────>|  [π1 done]
  |                                          | conv2(6→16,5×5) → 16×10×10 (f=32)
  |<─── TruncateRequest(π2, relu+pool+shift) |
  | Dec → relu → pool2×2 → shift(28→16)     |
  | Re-enc(16×5×5, f=16)                    |
  |─────────────────────────────────────────>|  [π2 done]
  |                                          | c3(16→120,5×5) → 120 (f=32)  [等价FC]
  |<─── TruncateRequest(π3, relu_then_shift) |
  | Dec → relu → shift(32→16)               |
  | Re-enc(120, f=16)                       |
  |─────────────────────────────────────────>|  [π3 done]
  |                                          | f4(120→84) → 84 (f=32)
  |<─── TruncateRequest(π4, relu_then_shift) |
  | Dec → relu → shift(32→16)               |
  | Re-enc(84, f=16)                        |
  |─────────────────────────────────────────>|  [π4 done]
  |                                          | f5(84→10) → 10 (f=32)
  |<─── InferenceResult (密文 f=32, 10维)   |
  | Dec → argmax → ŷ                        |  [无重加密]
  |<──────────── InferenceComplete ─────────|
```

### 3.5 截断相位表（Π）

> **注：π1/π2 中间尺度说明**  
> Pool 在客户端明文域对 f=32 的解密值执行。2×2 avg pool = 对 4 个整数求和后右移 2 位（÷4），结果仍在 f=32；再右移 16 位（shift 32→16）得到 f=16。因此总移位量 = 18 bit，表中"pool+shift"合并为从 f=32 到 f=16 的 18 bit 右移，**不经过 f=28 中间态**（f=28 是同态服务端执行 pool 时对 f=16 输入的尺度，此处 pool 在客户端明文域进行故不适用）。

| π_k | 位置 | 客户端动作 | 解密时 f | 重加密时 f | 张量规模 | 约束 |
|-----|------|-----------|---------|----------|---------|------|
| π1 | after_conv1 + pool1 | relu → pool(2×2) → shift(18 bit) | 32 | 16 | 6×14×14 | BSGS: dec前\|m\|<10¹³；INT32: re-enc前\|m\|<2³¹ |
| π2 | after_conv2 + pool2 | relu → pool(2×2) → shift(18 bit) | 32 | 16 | 16×5×5 | 同上 |
| π3 | after_c3 | relu → shift(32→16, 16 bit) | 32 | 16 | 120 | 同上 |
| π4 | after_f4 | relu → shift(32→16, 16 bit) | 32 | 16 | 84 | 同上 |
| — | after_f5 | argmax（无重加密） | 32 | — | 10 | **BSGS: dec前\|m\|<10¹³**（无 INT32 要求） |

### 3.6 位宽安全检查（完整）

每个解密点需满足 BSGS 约束；每个重加密点需满足 INT32 约束。

| 检查点（π） | BSGS：解密前 \|m\| < 10¹³ | INT32：re-enc前 \|m\| < 2³¹ | 备注 |
|------------|--------------------------|---------------------------|------|
| π1 after_conv1 (f=32) | ✓ 须离线校准验证 | — （dec后做 relu+pool+shift，shift后检查） | — |
| π1 re-enc (f=16, after shift 18 bit) | — | ✓ M_post = M_pre_relu / 2^18 < 2³¹ | — |
| π2 after_conv2 (f=32) | ✓ 须离线校准验证 | — | — |
| π2 re-enc (f=16, after shift 18 bit) | — | ✓ M_post = M_pre_relu / 2^18 < 2³¹ | — |
| π3 after_c3 (f=32) | ✓ 须离线校准验证 | — | — |
| π3 re-enc (f=16, after shift 16 bit) | — | ✓ M_post = M_pre_relu / 2^16 < 2³¹ | — |
| π4 after_f4 (f=32) | ✓ 须离线校准验证 | — | — |
| π4 re-enc (f=16, after shift 16 bit) | — | ✓ M_post = M_pre_relu / 2^16 < 2³¹ | — |
| **after_f5 argmax (f=32)** | ✓ **须离线校准验证**（无重加密，仍需 BSGS） | — | argmax 只比大小，但解密每个值仍需 BSGS |

---

## 4. new_lenet（LeNet5 / CIFAR-10 / 3×32×32）

### 4.1 模型架构

```
input: 3×32×32 (f=16, RGB per-channel min-max)
c1: Conv2d(3→6,  5×5) → ReLU → AvgPool(2,2) → 6×14×14
c2: Conv2d(6→16, 5×5) → ReLU → AvgPool(2,2) → 16×5×5
c3: Conv2d(16→120,5×5)→ ReLU                 → 120   (等价 FC(400,120))
f4: Linear(120→84)    → ReLU                 → 84
f5: Linear(84→10)                             → 10  argmax
```

与 new_lenet_mnist 结构**完全相同**，仅输入通道 1→3、数据集 MNIST→CIFAR-10。

### 4.2 数据预处理（客户端，CIFAR-10）

```
RGB 3×32×32 uint8
→ /255 → per-channel per-image min-max → clip[0.001, 0.9999999]
→ ×2^16 → int32 (3,32,32)
→ Enc  (3 通道分别加密，或展平后加密，视实现而定)
```

### 4.3 交互时序

**与 new_lenet_mnist 完全相同**（见 §3.4），仅初始密文为 3×32×32。

截断相位表同 §3.5。

### 4.4 与 network_lenet（计划中）的区别

| 项 | network_lenet（HDC 计划版） | new_lenet（本文） |
|----|---------------------------|------------------|
| 卷积权重 | 设计为"等效小整数" f=0 → after_conv f=16 | 标准浮点 f=16 → after_conv f=32 |
| π1 动作 | relu（from_bits=16，不需 shift） | relu+pool+shift（from_bits=32） |
| 截断相位数 | 6（π1 relu, π2 shift, ...） | 4（π1 relu+pool+shift, π2 relu+pool+shift, π3, π4） |
| 总交互数 | 6 | **4** |

---

## 5. new_resnet（ResNet18 / CIFAR-10 / 3×32×32）

### 5.1 架构概览

```
input: 3×32×32 (f=16)
conv1: Conv2d(3→64,3×3,s=1,p=1,no bias) → BN → ReLU → 64×32×32
layer1 (stride=1, identity shortcut):
  Block1: conv1(64→64,3×3)→BN→ReLU→conv2(64→64,3×3)→BN → +shortcut → ReLU
  Block2: 同上
layer2 (first block stride=2, downsample shortcut):
  Block1: conv1(64→128,3×3,s=2)→BN→ReLU→conv2(128→128,3×3)→BN → +conv_sc(1×1,s=2)→BN → ReLU
  Block2: conv1(128→128)→BN→ReLU→conv2→BN → +identity → ReLU
layer3 (128→256, first s=2): 2 Blocks（同 layer2 模式）
layer4 (256→512, first s=2): 2 Blocks
avg_pool: AvgPool(4,4) → 512×1×1
linear: Linear(512→10) → argmax
```

**ReLU 总数**：1（conv1后）+ 8块×2 = **17 个 ReLU**  
**= 最少 17 次重加密**（不可优化，模型已按此架构训练）

### 5.2 BN Folding（离线预处理，无交互）

推理期 BatchNorm 是线性变换，折入前一层卷积权重：

```
W_folded[c] = W[c] × (γ[c] / σ[c])
b_folded[c] = β[c] − γ[c] × μ[c] / σ[c]
```

其中 γ, β, μ, σ 来自训练后的 BN 层参数。折入后每个 Conv+BN 变为普通有偏卷积，服务端做纯线性运算。

### 5.3 残差连接的密文加法

**Identity shortcut（无下采样）**：
```
shortcut_enc 在 f=16，main path 在 f=32（conv2 后）
→ Server: shortcut_enc × 2^16（EC 点标量乘，同态免费）→ 对齐到 f=32
→ Server: main_enc + shortcut_scaled_enc = result_enc (f=32)
→ Client: relu_then_shift(32→16)
```

**Downsampling shortcut（含 1×1 conv+BN，已 fold）**：
```
input_enc at f=16
→ Server: 并行计算 main_path_conv1 和 shortcut_conv(1×1)，均为 f=32
→ 主路径 conv1 结果 → Client: relu_then_shift(32→16) → 重加密
→ 主路径 conv2 结果 (f=32) + shortcut_enc (f=32) = result_enc (f=32)
→ Client: relu_then_shift(32→16)
```

### 5.4 末端优化：Pool + Linear 合并（节省 1 次交互）

标准做法（2 步）：
```
Server: avg_pool(4×4) → 512 (f=30) → 发送 → Client: shift(30→16) → 重加密
→ Server: linear(512→10) → 10 (f=32) → Client: argmax
```

优化（1 步，pool 和 linear 均在服务端完成）：
```
Server: avg_pool(4×4) → linear(512→10)（两步均线性，服务端连续计算）
→ 发送密文 10 维 (f=30+16=46) → Client: argmax（无重加密）
```

节省 1 次重加密和 1 次 WS 往返。

> ⚠️ **ECC BSGS 约束**：f=46 下整数绝对值可能很大（pool 512 维 × FC 权重累积）。实现时须在离线校准阶段验证 $|m_{\text{final}}| < 10^{13}$；若超出，改为 pool 后先 shift(30→16)再做 FC，代价是恢复 2 步（+1 轮交互）。

### 5.5 交互时序（完整 17 轮重加密 + 1 argmax）

```text
Client                                          Server
  | SessionStart / ModelSelect                  |
  |<─────────────── ModelSelectAck ────────────|
  | PublicKey + Enc(input) 3×32×32 (f=16)      |
  |────────────────────────────────────────────>|
  |                                             | [BN Folded conv1] 64×32×32 (f=32)
  |<── TR(π_init, relu_then_shift)             |
  | Dec→relu→shift(32→16) Re-enc 64×32×32      |
  |────────────────────────────────────────────>|

  // Layer1 Block1:
  |                                             | conv1_b11 → 64×32×32 (f=32)
  |<── TR(π_l1b1c1, relu_then_shift)           |
  | Dec→relu→shift(32→16) Re-enc              |
  |────────────────────────────────────────────>|
  |                                             | conv2_b11 (f=32) + shortcut×2^16 → f=32
  |<── TR(π_l1b1c2, relu_then_shift)           |
  | Dec→relu→shift(32→16) Re-enc              |
  |────────────────────────────────────────────>|

  // Layer1 Block2: (同 Block1 模式)
  ... 2 次交互 ...

  // Layer2 Block1 (stride=2, downsample shortcut):
  |                                             | conv1_b21(s=2) → 128×16×16 (f=32)
  |                                             |   同时: shortcut_conv(1×1,s=2)→BN_fold → f=32 (hold)
  |<── TR(π_l2b1c1, relu_then_shift)           |
  | Dec→relu→shift(32→16) Re-enc 128×16×16    |
  |────────────────────────────────────────────>|
  |                                             | conv2_b21 (f=32) + shortcut_held (f=32) → f=32
  |<── TR(π_l2b1c2, relu_then_shift)           |
  | Dec→relu→shift(32→16) Re-enc              |
  |────────────────────────────────────────────>|

  // Layer2 Block2 / Layer3 / Layer4: (每 block 2 次，共 6 blocks × 2 = 12 次)
  ... 12 次交互 ...

  // 末端 (Pool + Linear 合并):
  |                                             | avg_pool(4×4) → linear(512→10)
  |                                             |   output 10 (f=46)
  |<─────────── InferenceResult (f=46) ────────|
  | Dec → argmax → ŷ  [无重加密]              |
  |<────────── InferenceComplete ──────────────|
```

### 5.6 截断相位汇总

每个 relu_then_shift 相位均需满足以下两项约束（下表统一标注）：
- **BSGS**：解密前 |m| < 10¹³（即 conv+BN_fold 累积后的密文绝对值）
- **INT32**：relu+shift(32→16) 后 |m_shifted| = |m_relu| / 2¹⁶ < 2³¹（重加密前）

| 阶段 | 位置 | 动作 | f_dec→f_reenc | 张量规模 | BSGS | INT32 |
|------|------|------|---------------|---------|------|-------|
| π_init | after conv1+BN_fold | relu_then_shift | 32→16 | 64×32×32 | ✓ 须校准 | ✓ |
| π_l1b1_1 | layer1 B1 conv1+BN | relu_then_shift | 32→16 | 64×32×32 | ✓ | ✓ |
| π_l1b1_2 | layer1 B1 conv2+BN+sc（shortcut 已×2¹⁶ 对齐 f=32） | relu_then_shift | 32→16 | 64×32×32 | ✓ | ✓ |
| π_l1b2_1 | layer1 B2 conv1+BN | relu_then_shift | 32→16 | 64×32×32 | ✓ | ✓ |
| π_l1b2_2 | layer1 B2 conv2+BN+sc | relu_then_shift | 32→16 | 64×32×32 | ✓ | ✓ |
| π_l2b1_1 | layer2 B1 conv1+BN（stride=2） | relu_then_shift | 32→16 | 128×16×16 | ✓ | ✓ |
| π_l2b1_2 | layer2 B1 conv2+BN + ds_sc（均 f=32，直接加） | relu_then_shift | 32→16 | 128×16×16 | ✓ | ✓ |
| π_l2b2_1 | layer2 B2 conv1+BN | relu_then_shift | 32→16 | 128×16×16 | ✓ | ✓ |
| π_l2b2_2 | layer2 B2 conv2+BN+sc | relu_then_shift | 32→16 | 128×16×16 | ✓ | ✓ |
| π_l3b1_1/2 | layer3 B1 同上模式 | relu_then_shift | 32→16 | 256×8×8 | ✓ | ✓ |
| π_l3b2_1/2 | layer3 B2 | relu_then_shift | 32→16 | 256×8×8 | ✓ | ✓ |
| π_l4b1_1/2 | layer4 B1 | relu_then_shift | 32→16 | 512×4×4 | ✓ | ✓ |
| π_l4b2_1/2 | layer4 B2 | relu_then_shift | 32→16 | 512×4×4 | ✓ | ✓ |
| **— (argmax)** | pool(4×4)+linear→argmax | argmax，无重加密 | f=46 | 10 | **⚠️ 须校准验证** \|m\|<10¹³ | — |

总计：**17 次重加密 + 1 次 argmax**

> **ds_sc**（downsampling shortcut）：layer2/3/4 第一个 block 的 shortcut 经 1×1 conv+BN_fold，输出也在 f=32，与主路径 conv2 输出直接相加，无需额外标量乘对齐。仅 identity shortcut（layer1）需要 ×2¹⁶ 对齐。

---

## 6. new_resnet_block（Block 线性化实验变体 — ResNet18 / CIFAR-10 / 3×32×32）

### 6.1 目标

`new_resnet_block` 与 `new_resnet` 使用**相同已训练权重**，不重新训练。  
通过将恒等 shortcut block（identity-shortcut BasicBlock）替换为离线拟合的线性矩阵，把原来每 block **2 次**客户端交互降至 **1 次**，从而减少 ResNet18 的总 AHE 交互轮次。

代码位于 `model_training/new_resnet_block/`：

| 文件 | 作用 |
|------|------|
| `model.py` | `ResNet18()`（与 new_resnet 相同，用于校准）；`LinearizedBlock`；`linearize_blocks()` |
| `calibrate.py` | 加载 new_resnet checkpoint，拟合 A 矩阵，保存至 `block_linear_weights/` |
| `train.py` | （可选）如需重新训练 resnet_block 变体，输出到 `resnet18_block_<run_id>/` |
| `dataset.py` | 透传 new_resnet.dataset（相同 CIFAR-10 loader） |

### 6.2 可线性化 Block 与矩阵可行性

ResNet18 中 identity-shortcut block（stride=1，通道不变）的输出可近似为输入的线性变换：

$$y \approx A \cdot x$$

其中 $A$ 通过最小二乘法在校准数据上离线拟合。根据空间维度选择两种模式：

**Channel-only 模式**（`A ∈ R^{C×C}`，每空间位置共享，等价于 1×1 conv）：
- 矩阵极小（64²=4096 参数），适用于空间尺寸大的早期层
- 只捕获通道混合；精度取决于 block 是否主要在通道方向混合特征

**Full-spatial 模式**（`A ∈ R^{D×D}`，`D=C×H×W`）：
- 完整空间线性映射，精度更高
- 仅 layer4 B2（512ch, 4×4）可行：D=8192，A≈256 MB（float32）

| 线性化目标 | 替换范围 | 模式 | A 尺寸 | 内存 | 可行性 |
|-----------|---------|------|--------|-----|-------|
| `layer1_both` | layer1[0]+layer1[1] 合并 | channel | 64×64 | <1 MB | ✅ |
| `layer2_b2` | layer2[1] | channel | 128×128 | <1 MB | ✅ |
| `layer3_b2` | layer3[1] | channel | 256×256 | <1 MB | ✅ |
| `layer4_b2` | layer4[1] | full | 8192×8192 | ~256 MB | ✅ |
| layer3[1] full | — | full | 16384² | ~1 GB | ⚠️ 内存紧张 |
| layer1/2 full | — | full | ≥32768² | ≥4 GB | ❌ 不可行 |

**Downsample-shortcut block**（layer2/3/4 第一个 block，stride=2+通道变化）**不做线性化**：shortcut 本身含 1×1 conv，非恒等，线性近似误差大。

### 6.3 校准流程（calibrate.py）

```
Step 1  加载 new_resnet checkpoint.pt → ResNet18 标准模型
Step 2  CIFAR-10 测试集取前 N 张图作为校准集（建议 N=500~2000，无需标签）
Step 3  对每个目标 block/block-pair 注册 forward hook：
          hook_pre  → 捕获 block 输入 X (N, C, H, W)
          hook_post → 捕获 block 输出 Y (N, C, H, W)
Step 4  前向推理校准集，收集 X, Y
Step 5  拟合 A（最小二乘）：
          channel: X_flat = X.transpose(0,2,3,1).reshape(-1,C)   [形状 N·H·W × C]
                   Y_flat = Y.transpose(0,2,3,1).reshape(-1,C)
                   A = lstsq(X_flat, Y_flat).T  ∈ R^{C×C}
          full:    X_flat = X.reshape(N, D),  Y_flat = Y.reshape(N, D)
                   A = lstsq(X_flat, Y_flat).T  ∈ R^{D×D}
Step 6  计算相对误差：err = ‖Y_pred - Y_flat‖_F / ‖Y_flat‖_F
          建议阈值：channel mode < 10%，full mode < 5%；超出则该 block 不线性化
Step 7  保存 block_linear_weights/A_{target}.npy（float32）及 error_{target}.json
Step 8  调用 linearize_blocks(model, targets, weights_dir) 替换 block
Step 9  在 CIFAR-10 测试集上验证端到端精度，与原 new_resnet 对比
```

CLI 示例：
```bash
python -m model_training.new_resnet_block.calibrate \
    --checkpoint model_training/outputs/resnet18_<run_id>/checkpoint.pt \
    --num-calib 500 \
    --targets layer1_both layer2_b2 layer3_b2 layer4_b2
```

### 6.4 AHE 交互流变化

**原 new_resnet（每个 identity block 2 轮）：**
```
Server: conv1 + BN_fold → enc_mid (f=32)
Client: relu_then_shift(32→16) → re-enc            ← 第 1 轮
Server: conv2 + BN_fold + shortcut×2^16 → enc_out (f=32)
Client: relu_then_shift(32→16) → re-enc            ← 第 2 轮
```

**new_resnet_block（线性化后 1 轮）：**
```
Server: A ⊗ enc_x → enc_y (f=32)
        [A 量化至 f=16，矩阵乘法同态完成，无需客户端参与]
Client: shift(32→16) → re-enc                      ← 仅 1 轮（无 relu）
```

> **为何不加 relu**：A 拟合的是整个 block 的输出分布（已包含内部 relu 的效果），加 relu 反而破坏近似。shift 后的值可能有负数（近似误差引入），不影响后续层的 AHE 计算。

### 6.5 各 block 轮次节省汇总

| Block | 原 new_resnet | new_resnet_block | 节省 | 备注 |
|-------|-------------|-----------------|------|------|
| conv1+BN (π_init) | 1 | 1 | 0 | 不变 |
| layer1 B1 (identity) | 2 | ↘ | — | ↓ |
| layer1 B2 (identity) | 2 | ↘ 1（合并） | **3** | channel mode |
| layer2 B1 (downsample) | 2 | 2 | 0 | 不可线性化 |
| layer2 B2 (identity) | 2 | 1 | **1** | channel mode |
| layer3 B1 (downsample) | 2 | 2 | 0 | 不可线性化 |
| layer3 B2 (identity) | 2 | 1 | **1** | channel mode |
| layer4 B1 (downsample) | 2 | 2 | 0 | 不可线性化 |
| layer4 B2 (identity) | 2 | 1 | **1** | full mode |
| pool+linear argmax | 0+1 | 0+1 | 0 | 不变 |
| **合计** | **17 reenc + 1 argmax** | **11 reenc + 1 argmax** | **6** | 全部线性化成功时 |

> **前提**：4 个目标（layer1 B1+B2 合并，layer2/3/4 B2）均校准误差在阈值内。若某 block 误差超出，保留原 BasicBlock（轮次不减但精度无损）。

### 6.6 截断相位表（线性化后全优化版）

| 阶段 | 位置 | 客户端动作 | f_dec→f_reenc | BSGS | INT32 |
|------|------|-----------|--------------|------|-------|
| π_init | after conv1+BN_fold | relu_then_shift | 32→16 | ✓ 须校准 | ✓ |
| π_l1_linear | after linearized layer1 B1+B2 | **shift only** | 32→16 | ✓ 须校准 | ✓ |
| π_l2b1_1 | layer2 B1 conv1+BN | relu_then_shift | 32→16 | ✓ | ✓ |
| π_l2b1_2 | layer2 B1 conv2+BN+ds_sc | relu_then_shift | 32→16 | ✓ | ✓ |
| π_l2_linear | after linearized layer2 B2 | **shift only** | 32→16 | ✓ 须校准 | ✓ |
| π_l3b1_1 | layer3 B1 conv1+BN | relu_then_shift | 32→16 | ✓ | ✓ |
| π_l3b1_2 | layer3 B1 conv2+BN+ds_sc | relu_then_shift | 32→16 | ✓ | ✓ |
| π_l3_linear | after linearized layer3 B2 | **shift only** | 32→16 | ✓ 须校准 | ✓ |
| π_l4b1_1 | layer4 B1 conv1+BN | relu_then_shift | 32→16 | ✓ | ✓ |
| π_l4b1_2 | layer4 B1 conv2+BN+ds_sc | relu_then_shift | 32→16 | ✓ | ✓ |
| π_l4_linear | after linearized layer4 B2 (full) | **shift only** | 32→16 | ✓ 须校准 | ✓ |
| argmax | pool(4×4)+linear | argmax，无重加密 | f=46 | ⚠️ 须校准验证 | — |

> **BSGS 注意**：线性化 block 的 A 矩阵是离线标量乘（f=16），输入已在 f=16，因此 A⊗enc_x 的中间值在 f=32，与原 conv 层相同。BSGS 校准要求与 new_resnet 一致：须在校准集上验证 |m| < 10¹³。

---

## 7. 交互轮次对比

| 模型 | 朴素设计（轮次） | 优化后（轮次） | 节省 | 主要优化手段 |
|------|----------------|---------------|------|-------------|
| network_a（参考） | 4 | 4 | — | 已是最优 |
| new_lenet_mnist | 6 | **4** | 2 | pool 移到客户端，relu+pool+shift 合并 |
| new_lenet | 6 | **4** | 2 | 同上 |
| new_resnet | 19 | **18** | 1 | pool+linear 合并（末端） |
| **new_resnet_block** | 18 | **11~18** | **0~7** | Block 线性化（需校准验证，见 §6） |

> new_resnet 的 17 次 ReLU 是已训练架构的**交互下限**（不重训情况下）。new_resnet_block 通过线性化 identity block 绕过 relu，理论上可降至 11 轮，实际轮次取决于各 block 的线性化误差是否在阈值内。

---

## 8. 非线性运算可线性化分析

### 8.1 成功线性化（服务端完成，节省通信）

| 运算 | 为什么能服务端做 | 本文处理方式 | 节省轮次 |
|------|----------------|-------------|---------|
| Conv（含偏置） | 密文×明文标量 + 密文加法，完全线性 | 直接同态计算 | 0（必须） |
| BatchNorm（推理期） | 推理期 BN = γ/σ · x + (β − γμ/σ)，纯线性 | **BN Folding** 离线折入 Conv 权重 | 消除所有 BN 层交互 |
| AvgPool | 加权求和，线性 | 移至客户端（明文域），与 relu 合并一次解密 | **LeNet 节省 2 轮** |
| 残差 shortcut 加法 | 密文+密文 = 明文加法，线性 | 服务端密文加法（identity 需先标量乘 2¹⁶ 对齐 f） | 无需额外交互 |
| pool+linear 末端合并 | 两步均线性，服务端连续算 | **ResNet 末端节省 1 轮** | 1 |

### 8.2 为何 ReLU 无法在服务端用线性拟合替代

这是 ECC 指数ElGamal 加性同态的**根本限制**，非精度问题：

服务端对密文 $\text{Enc}(x)$ 只能计算：
- $k \cdot \text{Enc}(x) = \text{Enc}(kx)$（标量乘）
- $\text{Enc}(x) + \text{Enc}(y) = \text{Enc}(x+y)$（密文加）

即服务端只能对 $x$ 施加**固定系数的全域线性变换** $ax + b$。

ReLU 的特性是：
$$\text{ReLU}(x) = \begin{cases} x & x \ge 0 \\ 0 & x < 0 \end{cases}$$

- 任何固定线性函数 $ax+b$ 对正值和负值使用**同一斜率 $a$**，无法在负值处截零。
- "截零"需要知道 $x$ 的**符号**，而符号信息隐藏在密文中，服务端无法获取。
- 更高次多项式近似（如 $\alpha x^2 + \beta x + \gamma$）需要密文×密文运算 $= \text{Enc}(x^2)$，ECC ElGamal **不支持**。

因此，ReLU **必须**发回客户端解密后处理，无论用多少线性项拟合都无法绕过这一约束。

### 8.3 各运算可线性化汇总

| 运算 | 类型 | 服务端可做？ | 方式 |
|------|------|------------|------|
| Conv | 线性 | ✅ | 同态标量乘+加 |
| BatchNorm（推理） | 线性 | ✅ | BN Fold 离线 |
| AvgPool | 线性 | ✅（或移客户端） | 移客户端节省 1 轮/pool |
| 残差加法 | 线性 | ✅ | 密文加法，标量乘对齐 f |
| **ReLU** | **非线性** | ❌ **不可，含线性拟合** | 服务端看不到符号，无法截零 |
| SoftMax | 非线性 | ❌ | 含 exp，最终 argmax 由客户端做 |
| Sigmoid/Tanh | 非线性 | ❌ | 同 ReLU |
| Dropout | 训练期特有 | — | 推理时恒等，不影响 |

**结论**：当前 ECC 指数ElGamal 框架下，所有线性运算（Conv/BN/Pool/shortcut）均已在服务端完成或通过折叠消除，**ReLU 是唯一因密码学约束无法线性化的运算**，也是交互次数的硬下限。ResNet18 的 17 个 ReLU 是已训练架构的不可压缩底线。ECC 解密的 BSGS 约束要求每个解密点（含末端 argmax）满足 $|m| < 10^{13}$，需离线校准验证。

---

## 9. 后续工作（若需进一步减少交互）

| 方案 | 节省 | 代价 |
|------|------|------|
| **重训 new_resnet（无中间 ReLU）** | 每 block 减 1 轮，17→9 轮 | 精度下降，需重训 |
| **用 CKKS 替代 ECC ElGamal** | ReLU 可服务端多项式近似 | 需更换密码库，近似误差，失去 SNARK 兼容性 |
| **知识蒸馏到更小模型** | 减少层数 → 减少 ReLU | 需新训练 |
| **BatchNorm + Shortcut-Only ResNet** | 每 block 1 轮（9 轮总） | 需重训，精度取决于设计 |

最现实的短期方案：**按本文 §3–§5 为当前已训练模型接入 AHE 管线**，ResNet18 以 18 轮为基准，LeNet 以 4 轮为基准。

---

## 10. 实现路线（分步）

```text
Step 1  为 new_lenet_mnist 实现 truncation_config.py（参照 network_lenet 但 from_bits 改为 32）
Step 2  为 new_lenet 复用 Step 1（仅输入通道 1→3，其余相同）
Step 3  新建 export_weights.py（LeNet）：导出 conv1/2/c3/fc1/fc2 权重 npy bundle
Step 4  新建 register_backend.py，写入 registry
Step 5  为 new_resnet 实现 BN folding 工具（offline，产出 folded_weights.json）
Step 6  实现 ResNet shortcut 密文加法的服务端 topology（含明文标量对齐）
Step 7  实现 pool+linear 合并（服务端连续推理不中断）
Step 8  e2e smoke test（类比 scripts/ahe_e2e_smoke.py）
```
