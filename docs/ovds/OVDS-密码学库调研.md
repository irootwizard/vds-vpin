# OVDS 密码学库调研（Rust 生态）

> **更新**：2026-07-12  
> **目的**：为 Python → Rust 迁移选定底层密码学库，保证与 `ovds-server` 参考实现**协议语义一致**。  
> **Python 参考**：`ovds-server/src/vads_lib.py`、`ovds-server/RSA-accumulator/`

---

## 1. Python 侧实际依赖

| 组件 | 库/模块 | 参数 |
|------|---------|------|
| 双线性配对 + BLS 式签名 | `charm-crypto` `PairingGroup('BN254')` | Type-3 非对称配对；G1/G2/GT |
| RSA Accumulator | 自研 `RSA-accumulator/main.py` | 3072-bit 模数；128-bit hash-to-prime |
| 哈希 | `hashlib.sha256` | HG、H2 |
| hash-to-prime | `helpfunctions.hash_to_prime` | SHA256 + nonce 递增 + Miller-Rabin |
| 大整数 | Python `int`（任意精度） | 模幂、扩展欧几里得、Shamir trick |
| 可视化/测试辅助 | `matplotlib`、`numpy`、`merkletools` | **不迁移**至 Rust 核心路径 |

> **注意**：部分 vPIN 架构图写「BLS12-381」，但 Python 代码与 `OVDS协议完整流程.md` 均明确为 **BN254**。迁移须以代码为准。

---

## 2. 需求拆解

OVDS/VADS 密码层需要以下原语（非标准库封装，多为组合调用）：

| 原语 | 用途 | Python 位置 |
|------|------|-------------|
| BN254 配对 `e: G1×G2→GT` | append 验签、query/verify | `pair(sigma, g)` |
| G1 标量乘、点加 | σ = (H·u^s)^α | `u ** s`, `*` |
| G2 标量乘 | A = g^α | `g ** alpha` |
| HG: hash→G1 | 消息绑定 | `H_G` |
| HPrime: tag→素数 | RSA 累加器元素映射 | `H_prime` |
| HPrimes | 聚合非成员证明 | `H_Primes` |
| H2 | 挑战随机数 | `H_2` |
| RSA setup | 生成 n, Acc_0 | `accumulator_setup()` |
| RSA add/delete/batch | Acc_R 维护 | `main.py` |
| 非成员证明 | query/verify | `prove_non_membership`, `WitCreate_star` |
| NI-PoE | batch 操作见证 | `prove_exponentiation` |
| 大整数 modpow / modinv | 全程 | `pow`, `mul_inv`, `EEA` |

---

## 3. 候选库评估

### 3.1 BN254 配对

| 库 | 版本参考 | 优点 | 缺点 | 结论 |
|----|----------|------|------|------|
| **`ark-bn254` + `ark-ec` + `ark-ff`** | 0.5.x | 与 vPIN `vendor/ark-ec` 同系；底层 API 可复现自定义 BLS 变体 | 需手写 hash-to-G1；无高层 OVDS API | **首选** |
| `rust-bls-bn254` | 0.2.x | 封装 BLS 签名 | 标准 BLS API，与 OVDS 的 σ=(H·u^s)^α 不匹配 | 不采用 |
| `sylow` | latest | BN254 + hash-to-curve + pairing | 较新、审计状态不明；HG 行为须向量对齐 | **HG 对齐备选** |
| `blstrs` / `pairing` (zkcrypto) | — | 成熟、高性能 | **仅 BLS12-381**，曲线不同 | 不采用 |
| `charm-crypto` (FFI) | — | 与 Python 100% 一致 | C 依赖、Windows 构建难、违背迁移目标 | 不采用 |

**推荐组合**：

```toml
ark-bn254 = "0.5.0"
ark-ec    = "0.5.0"
ark-ff    = "0.5.0"
ark-serialize = "0.5.0"
sha2      = "0.10"
```

**关键风险**：`charm` 的 `group.hash(h, G1)` 与 ark 默认 hash-to-curve **不一定比特等价**。须在阶段 0 用固定种子导出测试向量，必要时实现 charm 兼容的 try-and-increment 映射。

---

### 3.2 RSA Accumulator

| 库 | 优点 | 缺点 | 结论 |
|----|------|------|------|
| **自移植 + `num-bigint`** | 与 `RSA-accumulator/` 算法完全一致；3072-bit 可配；项目已用 `num-bigint` | 需完整移植 ~280 行 Python | **首选** |
| `cambrian/accumulator` | 内置 `hash_to_prime`、高性能 GMP | 固定 RSA-2048 模数；API/证明格式不同 | 不采用（协议不兼容） |
| `accumulator-rs` | 多构造对比 | RSA 路径不完整；非 OVDS 算法 | 不采用 |
| 2024 无 hash-to-prime 累加器论文实现 | 性能更优 | 改变密码假设与证明格式 | 远期研究，当前不采用 |

**推荐组合**：

```toml
num-bigint  = { version = "0.4", features = ["rand"] }
num-traits  = "0.2"
num-integer = "0.1"
```

**性能备选**：若 `hash_to_prime` 在批量 append 时成为瓶颈，可引入 `rug`（GMP 绑定）替换 Miller-Rabin 热路径，但须保持输出与 Python 一致。

**已知修复**：`ISSUE_A0_COPRIME.md` 要求 `Acc_0` 与 `n` 互质；Python 已修复，Rust 移植须保留 `gcd(A0,n)==1` 检查。

---

### 3.3 hash-to-prime

| 方案 | 说明 | 结论 |
|------|------|------|
| **移植 `helpfunctions.py`** | SHA256 分块拼接 → 整数 → nonce 递增 → Miller-Rabin(5轮) | **唯一正确路径** |
| `cambrian/accumulator::hash_to_prime` | 同类思路但内部表示为 U256 | 行为可能不同，不宜直接替换 |
| `num-prime` crate | 通用素性检测 | 可作 Miller-Rabin 参考，算法须与 Python 一致 |

---

### 3.4 序列化

| 类型 | Python | Rust 建议 |
|------|--------|-----------|
| G1/G2 点 | charm 内部序列化（测试显示 σ≈46B） | `ark-serialize` CanonicalSerialize；固定长度编码供 mmap |
| 大整数 n, Acc_R | `int` 字符串/字节 | `num-bigint` `to_bytes_be` / `from_bytes_be`；mmap 定长 384B |
| tag | 128-bit 整数 | `[u8; 16]` 或 `u128` |

---

## 4. 不迁移的 Python 依赖

| 依赖 | 原因 |
|------|------|
| `matplotlib` / `numpy` | 仅 benchmark 可视化 |
| `merkletools` | RSA-accumulator 对照实验，非 VADS 主路径 |
| `RSA-accumulator` Solidity contracts | 链上验证实验，托管服务不需要 |
| `src/additional/avds_lib.py` | AVDS（q=2 树 + CLVC），非 OVDS 主路径 |

---

## 5. 推荐 Crate 分层

```
ovds-server/crates/
├── vads-crypto/          # 底层原语（本节选型落地）
│   ├── pairing.rs        # ark-bn254
│   ├── hash.rs           # sha2 + hash_to_prime 移植
│   └── rsa_acc.rs        # RSA-accumulator 移植
├── vads-core/            # vads_lib.py 协议状态机
└── vads-engine/          # VadsEngine trait 实现
```

---

## 6. 验证策略

1. **单元测试**：每个原语函数对照 Python 单步输出。
2. **Fixture 测试**：`ovds-server/fixtures/` 存放 JSON 测试向量（阶段 0 导出）。
3. **集成测试**：移植 `src/test/test_*.py` 为 Rust `#[test]`，流程一致。
4. **性能基准**：对比 Python `test_thread_performance.py` / `eva_data_size.py` 指标，不作为正确性门槛。

---

## 7. 外部参考

| 资源 | 链接 |
|------|------|
| arkworks BN254 | https://docs.rs/ark-bn254 |
| RSA Accumulator (BBF18) | https://eprint.iacr.org/2018/1188 |
| Cambrian accumulator（对比用） | https://github.com/cambrian/accumulator |
| 无 hash-to-prime 累加器（远期） | https://eprint.iacr.org/2024/505 |
