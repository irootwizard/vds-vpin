# OVDS Rust 实现 — 架构与依赖说明

## 项目位置

```
vpin-backend/
  crates/ovds-core/       # 密码学核心库
  apps/ovds-server/       # axum REST 服务
```

## 依赖库

### ovds-core

| Crate | 版本 | 用途 |
|-------|------|------|
| `blst` | 0.3 | BLS12-381 椭圆曲线配对, 提供 BLS 签名方案的 sign/verify/pairing |
| `num-bigint` | 0.4 | 大整数运算, RSA 3072-bit 模数生成与模幂运算 |
| `num-traits` | 0.2 | 数值 trait (Zero, One) |
| `sha2` | 0.10 | SHA-256 哈希, 用于 hash-to-g1 和 hash-to-prime |
| `rand` | 0.8 | 随机数生成 (密钥, tag, nonce) |
| `serde` | 1.0 | 序列化/反序列化 (VK, 证明结构体) |
| `thiserror` | 2.0 | 错误类型派生宏 |

### ovds-server

| Crate | 版本 | 用途 |
|-------|------|------|
| `ovds-core` | path | 核心协议库 |
| `axum` | 0.7 | HTTP/WebSocket 框架 |
| `tokio` | 1 | 异步运行时 |
| `sled` | 0.34 | 嵌入式 KV 存储, 用于持久化 DB/R/acc_r |
| `serde_json` | 1.0 | JSON 序列化 |
| `hex` | 0.4 | 十六进制编解码 |
| `tracing` | 0.1 | 结构化日志 |

## 代码架构

### ovds-core 模块

```
src/
  lib.rs          # crate 入口, 公共 re-export
  bls.rs          # BLS12-381 签名方案
  rsa_acc.rs      # RSA Accumulator (3072-bit)
  hash.rs         # 哈希函数 (HG, HPrime, H2)
  protocol.rs     # VADS 协议 (setup/append/query/verify/update/audit/judge)
  types.rs        # 数据结构 (VK, SK, Record, ServerState, 证明)
  error.rs        # 错误类型 (OvdsError)
```

#### bls.rs — BLS 签名

基于 `blst` crate 的 min-pk 模式 (签名在 G1, 公钥在 G2)。

- `key_gen() -> (BlsSecretKey, BlsPublicKey)`: 生成 BLS12-381 密钥对. 公钥为 G2 点 (96 bytes), 私钥为 32 bytes 标量.
- `sign(sk, msg) -> BlsSignature`: BLS 签名. 内部调用 blst 的 hash-to-g1 将消息映射到 G1 点, 然后用私钥标量乘得到签名 (48 bytes).
- `verify(pk, msg, sig) -> bool`: BLS 验证. 检查配对等式 e(sig, g2) == e(H(msg), pk).
- `aggregate_signatures(sigs) -> BlsSignature`: G1 签名聚合, 用于批量验证.
- `g1_add(a, b) -> G1Point`: G1 点加法, 用于协议中的 HG(i||tag) * u^s 计算.

对照 Python `vads_lib.py`:
- Python 使用 `charm-crypto` 的 BN254 配对
- Rust 使用 `blst` 的 BLS12-381 配对
- 曲线不同, 但签名方案和验证方程完全一致

#### rsa_acc.rs — RSA Accumulator

3072-bit RSA 模数, 提供成员增删和非成员证明.

- `setup() -> (n, h, phi)`: 生成 2 个 1536-bit 素数 p, q, 计算模数 n=p*q, phi=(p-1)(q-1), 随机选取生成元 h.
- `add_member(acc, x, n) -> acc'`: 累加器添加成员: acc^x mod n.
- `remove_member(acc, x, n, phi) -> acc'`: 累加器删除成员: acc^(x^(-1) mod phi) mod n.
- `egcd_bezout(x, y) -> (g, a, b)`: 扩展欧几里得算法, 求 Bezout 系数.
- `mul_inv(a, n) -> Option<a^(-1)>`: 模逆.
- `prove_non_membership(acc_r, z_star, q, n, h) -> NonMembershipProof`: 创建非成员证明. 利用 Bezout 系数证明 q 不是 z_star 的因子.
- `verify_non_membership(acc_r, z_star, q, pi, n, h) -> bool`: 验证非成员证明.

对照 Python `helpfunctions.py` + `vads_lib.py` Algorithm 2:
- Python 的 WitCreate_star/WitVerify_star 是完整的聚合非成员证明算法
- Rust 实现: 单元素用 Bezout 直接证明, 多元素用乘积聚合 (简化版 Algorithm 2)

#### hash.rs — 哈希函数

- `hg(data) -> BigUint`: SHA-256 哈希到 256-bit 整数, 用于 Schnorr challenge 和协议中的消息摘要.
- `hg_indexed(i, tag) -> BigUint`: 拼接索引和 tag 后哈希.
- `hprime(tag) -> BigUint`: 哈希到 128-bit 素数. 迭代 SHA-256 直到找到 Miller-Rabin 素数.
- `h2(data) -> BigUint`: 哈希到 128-bit 整数 (取 SHA-256 前 16 bytes).

#### protocol.rs — VADS 协议

对照 Python `vads_lib.py` 逐函数迁移:

- `setup() -> (vk, sk, state)`: 系统初始化. 生成 BLS 密钥对 + RSA accumulator.
- `append_client(sk, s) -> (i, record)`: 客户端签名数据. 生成随机 tag, BLS 签名 (i, tag, s).
- `append_server(vk, state, i, record) -> ()`: 服务端验证签名并存储. 更新 RSA accumulator.
- `query(state, i) -> QueryResponse`: 单条查询, 返回数据和证明.
- `query_star(state, indices) -> QueryStarResponse`: 批量查询, 返回聚合证明.
- `verify_query(vk, resp) -> bool`: 验证单条查询证明.
- `verify_query_star(vk, resp) -> bool`: 验证批量查询证明.
- `update(sk, i, s', state) -> Record`: 更新数据. 旧 tag 加入撤销集合 R, 生成新签名.
- `update_batch(sk, updates, state) -> Vec<Record>`: 批量更新.
- `append_batch(sk, values, state) -> Vec<(u64, Record)>`: 并发批量追加. rayon 并行签名.
- `audit(state, indices) -> AuditProof`: 服务端生成审计证明 (聚合签名 + RSA 非成员证明).
- `judge(vk, indices, values, proof) -> bool`: 客户端验证审计证明.

### ovds-server 架构

```
src/
  main.rs          # axum 服务入口, 路由注册, 状态初始化, sled 持久化恢复
  routes.rs        # 请求处理函数 + 持久化逻辑
```

#### 状态管理

```rust
pub struct AppState {
    pub vk: RwLock<Option<VerificationKey>>,   // 验证密钥
    pub server_state: RwLock<Option<ServerState>>, // 服务端状态
    pub sk: RwLock<Option<SecretKey>>,          // 秘密密钥
    pub db: sled::Db,                           // 持久化存储
}
```

所有可变状态用 `tokio::sync::RwLock` 保护, 支持多 reader 单 writer 并发访问.

#### API 端点

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | /health | 健康检查 |
| POST | /setup | 系统初始化, 生成 VK/SK/ServerState |
| POST | /append | 追加单条数据 |
| POST | /append_batch | 批量并发追加数据 (rayon) |
| POST | /update | 更新单条数据 |
| POST | /update_batch | 批量更新数据 |
| GET | /query?index=N | 查询单条记录 |
| POST | /query | 查询单条记录 (JSON body) |
| POST | /query_batch | 批量查询 |
| POST | /verify | 验证查询证明 |
| POST | /verify_batch | 批量验证 |

#### 持久化

使用 sled 嵌入式数据库. 每次 append/setup 后将完整状态序列化为 JSON 写入 sled:
- VK (验证密钥)
- SK (秘密密钥, 含 alpha 和 cnt)
- DB (所有记录的 HashMap)
- R (撤销集合)
- acc_r, z_star, n, phi

服务启动时从 sled 恢复状态, 实现重启后数据不丢失.

## 数据流

```
客户端                         服务端
  |                              |
  |-- POST /setup -------------->|  生成 BLS 密钥对 + RSA accumulator
  |<-- VK -----------------------|
  |                              |
  |-- POST /append {value} ----->|  
  |   (服务端: sign + verify + store + persist)
  |<-- {index, sigma, tag} ------|
  |                              |
  |-- GET /query?index=N ------->|  从 DB 读取 + 生成 RSA 证明
  |<-- {value, proof} ----------|
  |                              |
  |-- POST /verify {vk, resp} -->|  验证 BLS 签名
  |<-- {valid: true/false} ------|
```

## 对照 Python 实现的差异

| 项 | Python (charm-crypto) | Rust (blst) |
|----|----------------------|-------------|
| 椭圆曲线 | BN254 | BLS12-381 |
| 安全级别 | ~100 bit | ~128 bit |
| BLS 公钥 | G2 点 | G2 点 (96 bytes) |
| BLS 签名 | G1 点 | G1 点 (48 bytes) |
| RSA 模数 | 3072 bit | 3072 bit |
| 配对库 | charm-crypto (PBC) | blst (汇编优化) |
| 非成员证明 | 完整 Algorithm 2 | 简化单元素证明 |
| 并发 | 无 (单线程 Python) | tokio + RwLock |
| 持久化 | 无 (内存) | sled |

## 构建与测试

```bash
# 构建
cd vpin-backend
cargo build --release -p ovds-core
cargo build --release -p ovds-server

# 单元测试
cargo test -p ovds-core

# 启动服务
cargo run --release -p ovds-server

# 测试 API
curl -X POST http://127.0.0.1:9000/setup
curl -X POST http://127.0.0.1:9000/append -H 'Content-Type: application/json' -d '{"value":"42"}'
curl 'http://127.0.0.1:9000/query?index=0'
```
