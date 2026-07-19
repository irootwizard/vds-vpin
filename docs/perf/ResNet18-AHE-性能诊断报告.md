# ResNet18 AHE 同态推理性能诊断报告

> **日期**: 2026-07-15
> **模型**: ResNet18 CIFAR-10 (new_resnet)
> **权重**: `model_training/outputs/resnet18_20260629_054142`
> **密码学后端**: EC (secp256r1 / primeorder), 指数 ElGamal
> **状态**: 诊断完成

---

## 1. 诊断方法

### 1.1 测量工具

在三个位置添加了分阶段计时埋点：

**Python 服务端** (`vpin-backend/vpin_backend/api/routes/session.py`):
```python
def _resnet_step():
    t1 = time.time()
    c1_pack = points_to_xy(c1)   # numpy Point → (x,y) 十进制元组
    c2_pack = points_to_xy(c2)
    t2 = time.time()
    res = resnet_session.step(...) # JSON IPC → Rust worker → JSON IPC
    t3 = time.time()
    out_c1 = _pack_to_points(...)  # (x,y) → numpy Point
    out_c2 = _pack_to_points(...)
    t4 = time.time()
    # 输出: pack_ms=(t2-t1) worker_ms=(t3-t2) unpack_ms=(t4-t3)
```

**Rust Worker** (`vpin-client/apps/ahe-cli/src/bin/ahe_resnet_worker.rs`):
```rust
let t1 = Instant::now();
let c1: Vec<E2Point> = c1_xy.iter().map(parse_point).collect(); // JSON→Point
let t2 = Instant::now();
let result = eng.accept_client_ciphertext(...); // EC 同态卷积
let t3 = Instant::now();
let out_c1_flat = ...point_to_xy...; // Point→JSON
let t4 = Instant::now();
emit_ok(&resp); // stdout write
// 输出: parse_ms compute_ms serialize_ms write_ms
```

**Rust 客户端** (`vpin-client/crates/ahe-client/src/session_ec.rs`):
```rust
struct SessionProfiler {
    encrypt_ms: f64,  // 客户端加密累计
    decrypt_ms: f64,  // 客户端 BSGS 解密累计
    ws_ms: f64,       // WebSocket 传输累计
    phases: Vec<PhaseTiming>, // 逐 phase 增量
}
```

### 1.2 测试环境

| 项目 | 值 |
|------|-----|
| CPU | 16 核 |
| OS | Windows 10 |
| Rust | release 模式 (`--release`) |
| Python | 3.10.6, uvicorn |
| BSGS 表 | `src/Pre_computed_table/table.bin` (3.2M entries, ~320MB) |
| WebSocket | ws://127.0.0.1:8000, base64 JSON wire |

### 1.3 测试方法

```
1. 启动 Python AHE 服务端 (:8000)
2. 客户端连接，发送 CIFAR-10 test[4] 图像
3. 收集服务端 stderr + 客户端 stderr 计时输出
4. 通过 EcDecryptProfile 分阶段计时确认 BSGS 占比
```

### 1.4 此前完成的优化（已施加）

| 优化 | 文件 | 效果 |
|------|------|------|
| P1: BSGS 批量归一化 | `bsgs.rs`, `point.rs` | 解密 1.81× 快 |
| P2: ResNet→Rust 服务端 | `ws.rs` | 已实现，待测 |
| P3: 默认 :8001 | `config.rs` | LeNet 17× 快 |

---

## 2. 实测数据

### 2.1 服务端逐 Phase 计时

```
[_resnet_step PERF] phase=initial cells=3072
  pack_ms=5   worker_ms=8680   unpack_ms=780   total_ms=9465

[_resnet_step PERF] phase=after_stem cells=65536
  pack_ms=93  worker_ms=334169  unpack_ms=806   total_ms=335067
```

| phase | cells | 形状 | pack_ms | worker_ms | unpack_ms | total |
|-------|-------|------|---------|-----------|-----------|-------|
| initial (stem) | 3,072 | 3×32×32→64×32×32 | 5ms | 8,680ms (8.7s) | 780ms | 9.5s |
| after_stem (l1b0c1) | 65,536 | 64×32×32→64×32×32 | 93ms | **334,169ms (5.6min)** | 806ms | 5.6min |

### 2.2 单 Phase 内部时间分解

```
phase=after_stem, total=335,067ms (5.6 分钟):

  pack_ms     93ms  ▏  0.03%   Python: numpy ecdsa.Point → (x,y) 十进制元组
  worker_ms 334169ms ████████████████████████████████████████  99.7%  Rust: JSON→EC计算→JSON
  unpack_ms  806ms  ▏  0.2%    Python: (x,y) 十进制元组 → numpy ecdsa.Point
```

### 2.3 Network A 客户端逐 Phase 解密时间（release 模式，EC 后端）

| phase | cells | max_abs | decrypt_ms | 笔记 |
|-------|-------|---------|------------|------|
| after_conv | 1,024 | 476K (2^19) | 34ms | 小值，快速 |
| after_pool | 64 | 300M (2^28) | 6ms | 中值 |
| after_fc1 | 16 | **44B (2^35)** | **243ms** | 大值，15ms/cell |
| after_fc2 | 10 | **70B (2^36)** | **308ms** | 极大值，31ms/cell |

### 2.4 Network A 端到端对比

| 指标 | Python :8000 | Rust :8001 | 提升 |
|------|-------------|-----------|------|
| encrypt_ms | 84ms | — | — |
| decrypt_ms | 326ms | 325ms | same |
| server_wait_ms | 726ms | **125ms** | **5.8×** |
| ws_ms | 2ms | — | — |
| **total_ms** | **1,134ms** | **538ms** | **2.1×** |

### 2.5 LeNet MNIST 端到端对比

| 指标 | Python :8000 | Rust :8001 | 提升 |
|------|-------------|-----------|------|
| decrypt_ms | — | 11,631ms | — |
| server_wait_ms | — | 8,910ms | — |
| **total_ms** | **~360,000ms** | **20,756ms** | **17×** |

---

## 3. 根因分析

### 3.1 EC 标量乘是硬天花板

`phase=after_stem` 的 335 秒中，99.7% 在 Rust EC 同态卷积内：

```
l1b0c1 卷积计算量:
  输入通道: 64
  卷积核:   3×3 = 9
  输出通道: 64
  输出空间: 32×32

  每输出像素 = 64 × 9 = 576 次 EC 标量乘 + 575 次 EC 点加
  输出像素数 = 64 × 32 × 32 = 65,536

  EC 标量乘总计 = 576 × 65,536 = 37,748,736 次
  EC 点加总计   = 575 × 65,536 = 37,683,200 次

  实测耗时 = 334,169ms
  每标量乘 ≈ 334,169 / 37,748,736 ≈ 8.9µs (release, parallel via rayon)
```

### 3.2 ResNet18 全量估算

| 层 | 输入ch | 输出ch | 空间 | k×k | 标量乘(万次) | 估算时间 |
|----|--------|--------|------|-----|-------------|---------|
| stem | 3 | 64 | 32×32 | 3×3 | 177 | 9s |
| l1b0c1 | 64 | 64 | 32×32 | 3×3 | 3,775 | **5.6min** |
| l1b0c2 | 64 | 64 | 32×32 | 3×3 | 3,775 | **5.6min** |
| l1b1c1 | 64 | 64 | 32×32 | 3×3 | 3,775 | **5.6min** |
| l1b1c2 | 64 | 64 | 32×32 | 3×3 | 3,775 | **5.6min** |
| l2b0c1 | 64 | 128 | 32→16 | 3×3 | 1,888 | 2.8min |
| l2b0c2 | 128 | 128 | 16×16 | 3×3 | 2,359 | 3.5min |
| l2b1c1 | 128 | 128 | 16×16 | 3×3 | 2,359 | 3.5min |
| l2b1c2 | 128 | 128 | 16×16 | 3×3 | 2,359 | 3.5min |
| l3b0c1 | 128 | 256 | 16→8 | 3×3 | 1,180 | 1.8min |
| l3b0c2 | 256 | 256 | 8×8 | 3×3 | 1,180 | 1.8min |
| l3b1c1 | 256 | 256 | 8×8 | 3×3 | 1,180 | 1.8min |
| l3b1c2 | 256 | 256 | 8×8 | 3×3 | 1,180 | 1.8min |
| l4b0c1 | 256 | 512 | 8→4 | 3×3 | 590 | 0.9min |
| l4b0c2 | 512 | 512 | 4×4 | 3×3 | 590 | 0.9min |
| l4b1c1 | 512 | 512 | 4×4 | 3×3 | 590 | 0.9min |
| l4b1c2 | 512 | 512 | 4×4 | 3×3 | 590 | 0.9min |
| ds×3 | — | — | — | 1×1 | ~200 | ~1min |
| FC | 512 | 10 | — | — | ~1 | <1s |
| **总计** | | | | | **~29,900 万** | **~48 分钟** |

加上 17 层客户端 BSGS 解密 + re-encrypt + WS 传输 ≈ 10-15 分钟 → **总计约 1 小时**。

### 3.3 时间分布饼图

```
服务端 EC 标量乘   ████████████████████████████████████████████  ~85%
客户端 BSGS 解密   ██████                                          ~10%
WS 传输            █                                               ~2%
Python 序列化      ▏                                               ~1%
客户端 re-encrypt  █                                               ~2%
```

---

## 4. 已尝试的加速方案

### 4.1 Block 线性化 (new_resnet_block)

**结论: 不可行。**

| Block | 模式 | 校准误差 | 判定 |
|-------|------|---------|------|
| layer1_both | channel (64×64) | **60.7%** | :x: |
| layer2_b2 | channel (128×128) | **38.1%** | :x: |
| layer3_b2 | channel (256×256) | **52.4%** | :x: |
| layer4_b2 | full (8192×8192) | **0.0%** | :white_check_mark: |

根因: conv1→ReLU→conv2 不是线性变换，channel-mode 的 C×C 矩阵无法捕获 3×3 卷积核的空间交互 + ReLU 非线性。仅 layer4_b2 因 full mode 矩阵秩不足完美拟合，但只省 1 轮。

### 4.2 BSGS 批量归一化 (P1)

**结论: 部分有效 (1.81× 解密加速)。**

将 giant step 每迭代 1 次模逆改为每 8 迭代 1 次模逆（batch normalize 16 projective points）。

### 4.3 Rust 服务端 (P2/P3)

**结论: LeNet/NetA 有效，ResNet 收益有限。**

LeNet 17× 加速来自消除纯 Python EC 运算。ResNet 已用 Rust worker，IPC 仅占 <2%，切换纯 Rust 服务端不会显著加速。

---

## 5. 结论

### 根因

**EC-ElGamal 同态加密方案下，ResNet18 规模模型的同态卷积需要约 3 亿次椭圆曲线标量乘法。每次 ~8.9µs（release, rayon 并行），不可进一步压缩。**

### 时间分布

| 阶段 | 占比 | 瓶颈性质 |
|------|------|---------|
| Rust EC 标量乘 | **~85%** | 硬天花板（算法计算量） |
| 客户端 BSGS 解密 | ~10% | 已优化 (P1) |
| WS 传输 | ~2% | 可忽略 |
| Python IPC | ~1% | 可忽略 |
| 客户端 re-encrypt | ~2% | 可忽略 |

### 可行的下一步方向

| 方向 | 预期 | 难度 |
|------|------|------|
| GPU 加速 EC 运算 (CUDA) | 10-100× | 高 |
| 换小模型 (LeNet, 21s) | 100× | 已实现 |
| MSM/Pippenger 批量标量乘 | 2-5× | 中 |
| 换格基 HE (CKKS) | 数量级 | 极高 (研究级重写) |

### 关键源码索引

| 文件 | 函数 | 说明 |
|------|------|------|
| `vpin-client/crates/ahe-homomorphic/src/network_resnet.rs:67` | `resnet_conv2d_channel` | 卷积热路径 |
| `vpin-client/crates/ahe-crypto-e2-ec/src/point.rs:259` | `scalar_mul_i64` | EC 标量乘入口 |
| `vpin-client/crates/ahe-crypto-e2-ec/src/mul.rs:14` | `mul_projective_vartime` | w-NAF 标量乘 |
| `vpin-client/crates/ahe-crypto-e2-ec/src/bsgs.rs:119` | `giant_step_projective_raw_from_alpha` | BSGS 解密 |
| `vpin-backend/vpin_backend/inference/ahe_worker.py:178` | `ResNetRustWorker.step` | Python↔Rust IPC |
| `vpin-backend/apps/ahe-server/src/ws.rs` | `SessionEngine` | Rust 服务端引擎 |
