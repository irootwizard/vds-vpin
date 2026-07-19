# Rust AHE 同态推理性能瓶颈诊断

> 日期：2026-07-11（更新：2026-07-15）
> 范围：vpin-client Rust workspace + Python 服务端，EC (secp256r1/primeorder) 后端
> 状态：诊断 + 验证完成，根因已确认

---

## :star: 核心根因：服务端同态推理未充分使用 Rust

### 当前架构（慢的原因）

```
LeNet (6 分钟):
  Rust ahe-cli ─WS─→ Python FastAPI (:8000)
                      └─ AheLenetEngine (纯 Python ecdsa!)
                           └─ my_conv2d: Point * scalar → 每次 ~100µs (纯 Python)
                           └─ fc_layer:   Point + Point  → 无 w-NAF 加速
  ⇒ 全部服务端 EC 运算在纯 Python 完成！

ResNet (1 小时):
  Rust ahe-cli ─WS─→ Python FastAPI (:8000)
                      └─ ResNetWorkerSession
                           └─ ahe-resnet-worker (Rust release ✅)
                                ↑ JSON stdin/stdout IPC PER PHASE (18次) ↑
  ⇒ 卷积在 Rust 计算，但 JSON 序列化/反序列化密文开销巨大
```

### 应该的架构

```
LeNet / ResNet:
  Rust ahe-cli ─WS─→ Rust axum (:8001)  ← 已存在！(vpin-backend/apps/ahe-server/)
                      └─ ahe-engine crate (纯 Rust, 无 IPC, 无 Python)
```

### 关键证据

**LeNet 服务端 — 纯 Python EC：**
`vpin-backend/vpin_backend/inference/homomorphic_network_a.py:92-98`：
```python
term = window[ii, jj] * filter_weights[ii, jj]  # ecdsa Point.__mul__ → GIL 绑定
sum_value = sum_value + term                      # ecdsa Point.__add__ → 纯 Python
```
- Python `ecdsa` 库无 w-NAF 加速（Rust 有，`ahe-crypto-e2-ec/src/mul.rs`）
- 无并行（GIL），Rust 用 rayon
- 每次标量乘 ~50-500µs vs Rust ~3µs

**ResNet 服务端 — JSON IPC 开销：**
`vpin-backend/vpin_backend/inference/ahe_worker.py:178`：
```python
# stdin → JSON → Rust → stdout → JSON → Python — 18 轮！
resp = self._send_cmd({"cmd": "step", "c1_xy": c1_xy, ...})
```
- ResNet release worker 存在 (1.3MB, Jul 2)
- 但 18 轮 × 每轮数千个 (x,y) 十进制坐标 → JSON 序列化

**Rust 服务端已存在但未使用：**
`vpin-backend/apps/ahe-server/` — 完整的纯 Rust axum WebSocket 服务端，包含 `ahe-engine` crate 直调（无 IPC），但当前 `ahe-cli` 默认连接 Python `:8000`！

---

## 实测基线

| 模型 | 耗时 | 交互轮次 | 后端 |
|------|------|---------|------|
| **ResNet18** CIFAR-10 | ~1 小时 (3600s) | 18 轮 (17 ReLU + final) | EC |
| **LeNet** CIFAR-10 | ~6 分钟 (360s) | 5 轮 | EC |

---

## 系统架构概览

```
vpin-client (Rust workspace)
├── ahe-crypto-e2-ec/     ← EC 曲线算术 (secp256r1), 点加/标量乘/BSGS
├── ahe-codec/             ← 编解码, 定点转换, 激活函数
├── ahe-codec-ec/          ← EC↔arkworks 桥接
├── ahe-homomorphic/       ← 同态网络算子 (conv/pool/fc/shortcut)
├── ahe-engine/            ← 状态机 (轮次调度)
├── ahe-client/            ← WebSocket 客户端会话
└── apps/ahe-cli/          ← CLI 入口

数据流:
  Client: 加密输入 → [WS] → Server: 同态 conv → [WS] → Client: BSGS解密→ReLU→重加密 → ...
```

---

## 瓶颈诊断

### 🔴 瓶颈 #1（致命）：BSGS giant step 每轮迭代做仿射坐标转换

**位置:** `vpin-client/crates/ahe-crypto-e2-ec/src/bsgs.rs:119-149`
**估算占比:** 40-60%

```rust
fn giant_step_projective_raw_from_alpha(...) {
    let step = inv_alpha_m.to_affine();  // 一次性，OK
    for i in 0..BSGS_M {  // 最多 3,200,000 次
        let keys = lookup_keys_projective_batch(&[gamma, gamma2]); // ← 致命！
        // ... HashMap 查找 ...
        gamma = add_projective_mixed(&gamma, &step);
        gamma2 = add_projective_mixed(&gamma2, &step);
    }
}
```

`lookup_keys_projective_batch` (`point.rs:226-239`) 每次调用 `BatchNormalize`（**批量模逆**），即对每对 projective 点做 `1/(z1*z2)` 256-bit 模逆运算。

**代价计算：**
- 对于值为 2^32 的 cell（post-ReLU 正值，f=32）：
  `floor(2^32 / 3.2M) ≈ 1,342` 次迭代
  每次迭代含 1 次模逆 ≈ 10-100μs → **每 cell 13-134ms**
- ResNet stem 输出: 16×32×32 = **16,384 cells**
  → 总计 214-2,200s（**3.5-37 分钟** 仅解密一层！）
- 对于 2^37 的大值（pre-ReLU 中间值）：
  `floor(2^37 / 3.2M) ≈ 42,950` 次迭代
  → **每 cell 0.4-4.3s**

**根因：** BSGS 搜索步数 = `floor(|value| / BSGS_M)`。pre-ReLU 中间值可达 2^37，需要数万次迭代。每次迭代都做模逆。

**优化方向：**
1. 迭代中去掉 affine 转换 — 改用纯 projective 坐标查表方案
2. 使用无需 z 逆的坐标归一化（如 X/Z 或 Y/Z 比值作为查表 key）
3. 扩大 BSGS_M（减少搜索步数），以内存为代价
4. 利用 ReLU 后值大概率较小的特性做 early termination

---

### 🔴 瓶颈 #2（重大）：scalar_mul_i64 每条像素分配 BigUint

**位置:** `vpin-client/crates/ahe-crypto-e2-ec/src/point.rs:259-268`
**估算占比:** 10-15%

```rust
pub fn scalar_from_i64(k: i64) -> Scalar {
    let abs = BigUint::from(k.unsigned_abs());  // ← 堆分配！
    let order = crate::params::scalar_order();   // ← 每次重新获取！
    let n = if k < 0 { order - abs } else { abs };
    scalar_from_biguint(&n)
}
```

卷积内循环每条像素调用 `scalar_mul_i64(w_fp)`：
```rust
// network_resnet.rs:101
let term = padded[...].scalar_mul_i64(w_fp); // ← 每条像素都分配 BigUint
```

**代价：** ResNet 单次 conv（16ch×32×32×3×3×16 = 737K 次标量乘），每次 `BigUint::from()` 触发堆分配 + `Scalar::reduce()` Barrett reduction。

**优化方向：**
1. 权重是 f=16 定点数，范围 [-32768, 32767]，可直接用 `Scalar::from(i64)` 处理
2. 加载权重时预计算 `Vec<Scalar>`，卷积时直接使用

---

### 🔴 瓶颈 #3（重大）：E2Point 操作中的 Arc clone 和坐标转换

**位置:** `vpin-client/crates/ahe-crypto-e2-ec/src/point.rs` 和 `vpin-client/crates/ahe-crypto-e2/src/point.rs`
**估算占比:** 8-12%

```rust
// EcE2Point 内部持有 Arc<PointCache>
pub enum EcE2Point {
    Affine {
        x: [u8; 32], y: [u8; 32],
        cache: Arc<PointCache>,  // ← 每次 clone 都 inc refcount
    },
}

// 每个 add 都要做 to_projective() 转换
pub fn add(&self, other: &EcE2Point) -> EcE2Point {
    EcE2Point::from_projective(&add_projective(
        &self.to_projective(),    // ← OnceLock 检查 + 可能重新计算
        &other.to_projective(),
    ))
}
```

ResNet 总计约 500-1000 万次 point add，每次的微小开销被放大。

**优化方向：**
1. 卷积/FC 等热点函数内部改用纯 `ProjectivePoint` 表示
2. 仅在边界处（输入/输出/加密/解密）转为 wire 格式 `EcE2Point`

---

### 🟡 瓶颈 #4（显著）：pointwise_add_grid 逐元素串行

**位置:** `vpin-client/crates/ahe-homomorphic/src/network_resnet.rs:203-213`
**估算占比:** 5-10%

```rust
fn pointwise_add_grid(a: &CtGrid, b: &CtGrid) -> CtGrid {
    for i in 0..h {
        for j in 0..w {
            out[i][j] = a[i][j].add(&b[i][j]);  // 串行，无 rayon
        }
    }
}
```

此函数在 `resnet_conv_ciphertext` 中每个输入通道调用一次（叠加通道卷积结果），但空间维度全部串行。

**优化方向：** 对 h×w 网格用 `into_par_iter` 并行化

---

### 🟡 瓶颈 #5（架构）：ResNet 18 轮交互

**估算占比:** 架构约束

- 每轮：服务端同态计算 → WS 传输 → 客户端 BSGS 解密 → ReLU/shift → 重加密 → WS 回传
- 18 轮是 ResNet 的 17 个 ReLU 层决定的（不可压缩）
- 当前无流水线：每轮的 WS 传输和等待是纯 idle 时间
- base64 编码的密文张量比 raw bytes 大 33%

**优化方向：**
1. 利用 ReLU 后稀疏性（多数值为 0）做 sparse 传输
2. Binary WebSocket 替代 base64 JSON

---

### 🟡 瓶颈 #6（中等）：HashMap BSGS 表

**位置:** `vpin-client/crates/ahe-crypto-e2-ec/src/bsgs.rs:28-30`
**估算占比:** 5-8%

```rust
pub struct BsgsTable {
    map: HashMap<([u8; 32], [u8; 32]), u32>,  // 3.2M entries, 64-byte key
}
```

- 3.2M 条目 × ~100 bytes/条目 ≈ 320MB
- 每次查找哈希 64 字节 key → 缓存不友好
- 标准 `HashMap` 使用 SipHash（加密级哈希），对 64 字节 key 较慢

**优化方向：**
1. 用 `ahash` 或 `fxhash` 替代默认 SipHash
2. 更紧凑的 key 表示（如 X 坐标低 32 位截断）
3. 排序数组 + 二分查找（缓存友好但 O(log n)）

---

## 瓶颈贡献估算

```
BSGS affine 转换   ████████████████████████████████████████  40-60%
BigUint 分配       ██████████                                10-15%
Arc clone/坐标转换  ████████                                  8-12%
串行 grid add      █████                                     5-10%
HashMap 哈希       ████                                      5-8%
WS/base64 开销     ██                                        2-5%
其他               ███                                       3-5%
```

---

## 验证结果（2026-07-11，已实测确认）

### V1: BSGS giant step 占比确认

```
Phase breakdown (decrypt_pair_profiled, value=10^8):
  wire_ms  (affine conv): 0.000ms
  mul_ms   (sk*c1)      : 0.000ms
  add_ms   (c2-sk*c1)   : 0.014ms
  bsgs_ms  (giant step) : 3.146ms  ← 占总时间 99.5%
  total_ms              : 3.161ms
```

**:star: 结论确认：BSGS 占解密时间 99.5%，瓶颈 #1 诊断正确。**

每轮 giant step 迭代约 **~95-100µs**（在 debug 模式下实测）。

### V1.1: ResNet 中间值范围 vs BSGS 耗时

| 中间值 | 迭代次数 | bsgs_ms | total_ms | 典型场景 |
|--------|---------|---------|----------|---------|
| 0 | 0 | 0.37 | 0.51 | ReLU 后零值（最常见） |
| 2^16 (65K) | 1 | 0.38 | 0.39 | shift 后 f=16 |
| 2^20 (1M) | 1 | 0.38 | 0.39 | 较小中间值 |
| 2^24 (16M) | 6 | 0.93 | 0.94 | 中等中间值 |
| **2^28 (268M)** | **84** | **7.50** | **7.51** | **大中间值（pre-ReLU）** |
| 2^30 (1B) | 312 | 30.0 | 30.0 | 很大中间值 |
| 2^33 (10B) | 3125 | 306 | 306 | 极端值（接近 BSGS 上限） |

### V1.2: 按层解密时间估算

| 层 | 通道×空间 | cells | 2^20 值 | 2^28 值 |
|----|----------|-------|---------|---------|
| stem (3→16, 32×32) | 16×32×32 | 16,384 | 6.5s | **123s** |
| Layer1 (16→16, 32×32) | 16×32×32 | 16,384 | 6.5s | **123s** |
| Layer2 (16→32, 16×16) | 32×16×16 | 8,192 | 3.3s | **61s** |
| Layer3 (32→64, 8×8) | 64×8×8 | 4,096 | 1.6s | **31s** |
| Layer4 (64→64, 4×4) | 64×4×4 | 1,024 | 0.4s | **8s** |

> 注：以上仅估算解密时间，不含服务端 EC 计算、WS 传输、客户端重加密。
> ResNet 共 17 层解密（每层 conv 输出），如果中间值普遍在 2^28+，单是解密就需 **~350s-600s**。

### V2: BigUint 转换开销确认

```
per-call cost:
  direct Scalar::from:  0.280 µs
  via BigUint (current): 4.009 µs
  overhead: 14.3× slower
```

**:star: 结论确认：每次 scalar_mul_i64 的 BigUint 分配开销是直接转换的 14.3×。** ResNet 约有 500-1000 万次标量乘，累积开销不可忽视。

### V3: Debug 模式下 EC 标量乘的耗时

在 debug 模式下，单次 EC 标量乘约 **3ms**（10000 次耗时 30s），这解释了为什么 ResNet 在 debug build 下接近 1 小时。Release 模式下预计可以快 50-100×。

### 综合结论

1. **瓶颈 #1 (BSGS) 已确认**：占解密 99.5%，每 cell 耗时 = `floor(|value| / 3.2M) × 100µs`
2. **瓶颈 #2 (BigUint) 已确认**：每次转换 14.3× 开销
3. **瓶颈 #3 (Arc/坐标) 无法在 debug 模式下区分**：EC 操作本身太重，淹没了开销差异
4. **真因主链**：large pre-ReLU values (2^28+) → thousands of BSGS iters → 100µs/iter → **minutes per layer**

---

## 诊断优先级（按收益/难度排序）

| # | 检查项 | 预期收益 | 难度 | 对应瓶颈 |
|---|--------|---------|------|---------|
| P1 | BSGS 去掉迭代内 affine 转换 | **极高 (2-5×)** | 中 | #1 |
| P2 | 权重 Scalar 预计算 | **高 (~10-15%)** | 低 | #2 |
| P3 | 卷积内循环用纯 ProjectivePoint | **高 (~10%)** | 中 | #3 |
| P4 | pointwise_add_grid rayon 并行 | **中 (5-10%)** | 低 | #4 |
| P5 | BSGS 表改用 ahash | **中 (3-5%)** | 低 | #6 |
| P6 | Binary WebSocket 替代 base64 | **低 (<3%)** | 中 | #5 |

---

## 关键代码路径索引

| 文件 | 函数 | 瓶颈 |
|------|------|------|
| `crates/ahe-crypto-e2-ec/src/bsgs.rs:119` | `giant_step_projective_raw_from_alpha` | #1, #6 |
| `crates/ahe-crypto-e2-ec/src/point.rs:226` | `lookup_keys_projective_batch` | #1 |
| `crates/ahe-crypto-e2-ec/src/point.rs:259` | `scalar_from_i64` | #2 |
| `crates/ahe-crypto-e2-ec/src/point.rs:107` | `EcE2Point::add` | #3 |
| `crates/ahe-homomorphic/src/network_resnet.rs:67` | `resnet_conv2d_channel` | #2, #3 |
| `crates/ahe-homomorphic/src/network_resnet.rs:129` | `resnet_conv_ciphertext` | #4 |
| `crates/ahe-homomorphic/src/network_resnet.rs:203` | `pointwise_add_grid` | #4 |
| `crates/ahe-crypto-e2-ec/src/codec.rs:114` | `decrypt_pair_profiled` | #1 (计时点) |
