# OVDS 逐日迭代实施计划

> **版本**：2026-07-12  
> **粒度**：每个 **Day N** 为 1 人 × 1 工作日（6–8h）可独立交付的任务包  
> **总工期**：28 工作日 → DataOnly MVP（`:8003` 可 E2E 上传/验证/绑定）  
> **上位方案**：[OVDS-Python到Rust迁移方案](./OVDS-Python到Rust迁移方案.md)  
> **密码学库**：[OVDS-密码学库调研](./OVDS-密码学库调研.md)

---

## 0. 使用说明

### 0.1 每日任务包结构

每个 Day 包含：

| 字段 | 含义 |
|------|------|
| **目标** | 当天结束前必须达成的单一成果 |
| **前置** | 必须先完成的 Day 编号 |
| **上午 / 下午** | 建议时间盒（可并行调整） |
| **文件清单** | 新建或修改的路径（相对于仓库根） |
| **命令** | 复制即运行的验收命令 |
| **验收清单** | 全部勾选才算 Day 完成 |
| **阻塞处理** | 当天完不成的降级方案 |

### 0.2 全局约定

- **曲线**：BN254（与 Python 一致，不改 BLS12-381）
- **Rust workspace**：`ovds-server/crates/{vads-crypto,vads-core,vads-engine}`
- **托管 workspace**：`vpin-custody-server/`（Day 22 起创建）
- **Python 参考**：保留于 `ovds-server/python-reference/`（Day 1 整理）
- **测试向量**：`ovds-server/fixtures/`（Day 2 生成）
- **不迁移**：`additional/avds_lib.py`、Solidity、Node.js

### 0.3 里程碑总览

| 里程碑 | 完成 Day | 标志 |
|--------|----------|------|
| M0 基线锁定 | Day 2 | Python 全绿 + fixtures 就绪 |
| M1 密码原语 | Day 10 | `cargo test -p vads-crypto` 全绿 |
| M2 协议核心 | Day 18 | Rust 镜像 `test_all.py` 全绿 |
| M3 引擎 trait | Day 21 | `VadsEngine` 单租户闭环 |
| M4 托管骨架 | Day 22 | `vpin-custody-server` 编译 + health |
| M5 DataOnly HTTP | Day 27 | 9 条 REST 路由可用 |
| M6 E2E | Day 28 | console 走真实 `:8003` |

### 0.4 关键路径

```
Day1 → Day2 → Day3–10 → Day11–18 → Day19–21 → Day22–27 → Day28
         fixtures          vads-crypto    vads-core      engine+custody   HTTP      E2E
```

---

## Phase 0：基线锁定（Day 1–2）

### Day 1 — 目录整理 + Python 环境 + 基线测试

**目标**：`ovds-server` 目录规范化，Python 测试套件可一键运行。

**前置**：无

#### 上午（3h）

| # | 任务 | 产出 |
|---|------|------|
| 1 | 将 `ovds-server/src/` 移至 `ovds-server/python-reference/src/` | 路径更新 |
| 2 | 将 `ovds-server/RSA-accumulator/` 移至 `ovds-server/python-reference/RSA-accumulator/` | 同上 |
| 3 | 修正 `vads_lib.py` 中 RSA 路径：`sys.path.insert(0, ...'RSA-accumulator')` | import 正常 |
| 4 | 创建 `ovds-server/fixtures/.gitkeep` | 空目录 |
| 5 | 创建 `ovds-server/scripts/run_python_tests.ps1` | 一键测试脚本 |

**文件清单**：

```
ovds-server/
├── python-reference/
│   ├── src/                    # 从原 src/ 移入
│   └── RSA-accumulator/        # 从原根目录移入
├── fixtures/
└── scripts/run_python_tests.ps1
```

#### 下午（3h）

| # | 任务 | 产出 |
|---|------|------|
| 6 | 创建 venv：`python -m venv ovds-server/.venv` | 虚拟环境 |
| 7 | 安装依赖：`pip install -r python-reference/requirements.txt` | charm-crypto |
| 8 | 运行 `python python-reference/src/test/test_all.py` | 基线日志 |
| 9 | 记录环境到 `fixtures/environment.json`（Python 版本、charm 版本、平台） | 可复现元数据 |

**命令**：

```powershell
cd ovds-server
python -m venv .venv
.\.venv\Scripts\pip install -r python-reference\requirements.txt
.\.venv\Scripts\python python-reference\src\test\test_all.py
```

**验收清单**：

- [ ] `python-reference/src/test/test_all.py` 退出码 0
- [ ] `fixtures/environment.json` 存在且含 charm 版本
- [ ] `scripts/run_python_tests.ps1` 可重复运行通过
- [ ] 原 `ovds-server/src/` 已不存在（已迁入 python-reference）

**阻塞处理**：Windows 上 charm-crypto 安装失败 → 改用 WSL/Docker 跑 Python 基线，Rust 开发仍在 Windows 进行；在 `environment.json` 注明平台。

---

### Day 2 — 测试向量导出 + HG 向量捕获

**目标**：固定种子的 JSON fixtures 生成完毕，供 Rust 全程对照。

**前置**：Day 1

#### 上午（3h）

| # | 任务 | 产出 |
|---|------|------|
| 1 | 编写 `ovds-server/scripts/export_fixtures.py` | 导出脚本 |
| 2 | 在脚本顶部固定 `random.seed(42)`、`secrets` 替换为可复现源 | 确定性 |
| 3 | 导出 `fixtures/setup.json`：vk 中 `n,h,Acc_0,u,A` 的 hex；sk 中 `alpha,cnt` | -setup 向量 |
| 4 | 导出 G1/G2 点：sigma、HG 输出、配对结果 `e(σ,g)` 与 `e(H·u^s,A)` 的 hex | 配对向量 |

**`export_fixtures.py` 须导出字段**：

```json
{
  "seed": 42,
  "environment": { "charm_version": "...", "curve": "BN254" },
  "setup": {
    "n_hex": "...",
    "h_hex": "...",
    "Acc_0_hex": "...",
    "alpha_hex": "...",
    "u_g1_hex": "...",
    "g_g2_hex": "...",
    "A_g2_hex": "..."
  },
  "hg_samples": [
    { "input": "0||12345678901234567890123456789012", "g1_hex": "..." }
  ],
  "append": [
    { "index": 0, "s": 100, "tag_hex": "...", "sigma_g1_hex": "..." }
  ],
  "query_verify": {
    "index": 0,
    "s": 100,
    "pi_q": { "sigma_g1_hex": "...", "tag_hex": "...", "pi": { "x_hex": "...", "Y_hex": "..." } },
    "verify_accepted": true
  }
}
```

#### 下午（3h）

| # | 任务 | 产出 |
|---|------|------|
| 5 | 追加 3 条 append（s=100,200,300）到 fixtures | 多条目 |
| 6 | 导出 `query_star` 索引集 `J=[0,1,2]` 的 batch proof 结构 | batch 向量 |
| 7 | 编写 `fixtures/README.md` 说明各文件用途与生成命令 | 文档 |
| 8 | 在 `docs/ovds/` 记录 HG 算法观察笔记（charm `group.hash` 输入输出格式） | HG-对齐笔记 |

**命令**：

```powershell
cd ovds-server
.\.venv\Scripts\python scripts\export_fixtures.py
.\.venv\Scripts\python -c "import json; json.load(open('fixtures/setup.json'))"
```

**验收清单**：

- [ ] `fixtures/setup.json`、`fixtures/append.json`、`fixtures/query_verify.json` 存在
- [ ] 重新运行导出脚本两次，JSON 内容完全一致
- [ ] `hg_samples` 至少 3 条，含 `0||{tag}` 格式
- [ ] `fixtures/README.md` 含 regeneration 命令

**阻塞处理**：G1 序列化格式不确定 → 同时导出 charm 原始字节 + base64 + 压缩坐标，Rust 侧 Day 9 再选格式。

---

## Phase 1：vads-crypto（Day 3–10）

### Day 3 — Rust workspace 骨架 + 大整数工具

**目标**：`ovds-server` Cargo workspace 可编译，`vads-crypto` 含 bigint 工具函数。

**前置**：Day 2

#### 上午（3h）

| # | 任务 |
|---|------|
| 1 | 创建 `ovds-server/Cargo.toml` workspace（members: vads-crypto, vads-core, vads-engine） |
| 2 | 创建 `crates/vads-crypto/Cargo.toml`（ark-bn254 0.5、num-bigint、sha2） |
| 3 | 创建 `crates/vads-core/Cargo.toml`（依赖 vads-crypto，空 lib） |
| 4 | 创建 `crates/vads-engine/Cargo.toml`（依赖 vads-core，空 lib） |

#### 下午（3h）

| # | 任务 |
|---|------|
| 5 | 实现 `crates/vads-crypto/src/bigint.rs`：`mod_pow`、`mod_inv`、`xgcd`、`concat_int`（移植 helpfunctions） |
| 6 | 实现 `crates/vads-crypto/src/lib.rs` 模块导出 |
| 7 | 单元测试 `bigint.rs`：已知小整数 modinv 对照 Python |

**文件清单**：

```
ovds-server/Cargo.toml
ovds-server/crates/vads-crypto/src/{lib.rs,bigint.rs}
ovds-server/crates/vads-crypto/src/bigint.rs  # 含 #[cfg(test)]
ovds-server/crates/vads-core/src/lib.rs
ovds-server/crates/vads-engine/src/lib.rs
```

**命令**：

```powershell
cd ovds-server
cargo build
cargo test -p vads-crypto bigint
```

**验收清单**：

- [ ] `cargo build` 无错误
- [ ] `mul_inv(3, 7)` 等小案例与 Python 一致
- [ ] workspace 3 个 crate 均在 `Cargo.toml` members 中

---

### Day 4 — hash.rs：hash_to_length + hash_to_prime + H2

**目标**：hash 模块与 `fixtures/` 中素数输出一致。

**前置**：Day 3

#### 上午（3h）

| # | 任务 |
|---|------|
| 1 | 实现 `hash.rs::hash_to_length`（移植 `helpfunctions.hash_to_length`） |
| 2 | 实现 `hash.rs::is_probably_prime` + `rabin_miller`（5 轮，与 Python 一致） |
| 3 | 实现 `hash.rs::hash_to_prime`（nonce 递增） |

#### 下午（3h）

| # | 任务 |
|---|------|
| 4 | 实现 `h2()`（SHA256 取前 16 字节 → BigInt） |
| 5 | 实现 `h_prime(tag)` → 调用 `hash_to_prime(str(tag), 128, 0)` |
| 6 | 测试：从 fixtures 读取输入，断言素数 hex 与 Python 一致 |

**命令**：

```powershell
cargo test -p vads-crypto hash
```

**验收清单**：

- [ ] `hash_to_prime("test-element", 128, 0)` 与 Python 同 nonce 输出相同
- [ ] `h2(b"gamma")` 可复现
- [ ] 至少 5 个 fixture 驱动的测试通过

---

### Day 5 — rsa_acc.rs（上）：setup + add + S 映射

**目标**：RSA 累加器初始化与单元素添加。

**前置**：Day 4

#### 上午（3h）

| # | 任务 |
|---|------|
| 1 | 定义 `RsaAccumulatorParams { n, a0 }`、`RsaState { acc, set: HashMap<String, u64> }` |
| 2 | 实现 `setup()`：生成 p,q（1536-bit）、A0 与 n 互质（见 ISSUE_A0_COPRIME） |
| 3 | **测试用**：支持从 fixtures 注入 `(n, a0)` 跳过随机生成 |

#### 下午（3h）

| # | 任务 |
|---|------|
| 4 | 实现 `add(acc, element, n)` + `S` 中存 nonce |
| 5 | 对照 `fixtures/setup.json` 的 `n_hex, Acc_0_hex` 做 add 冒烟测试 |
| 6 | 导出常量 `RSA_KEY_BITS=3072`、`ACCUMULATED_PRIME_BITS=128` |

**验收清单**：

- [ ] `setup()` 返回的 `gcd(a0, n) == 1`
- [ ] 固定 `(n, a0)` 下 `add` 结果与 Python `main.add` 一致
- [ ] `cargo test -p vads-crypto rsa_acc::setup`

---

### Day 6 — rsa_acc.rs（中）：membership + non-membership

**目标**：`prove_non_membership` / `verify_non_membership` 可用。

**前置**：Day 5

#### 全天任务

| # | 任务 | Python 对照 |
|---|------|-------------|
| 1 | `prove_membership` | `main.prove_membership` |
| 2 | `prove_non_membership` | `main.prove_non_membership` |
| 3 | `verify_non_membership` | `main.verify_non_membership` |
| 4 | 负指数路径：`a<0` 时用 `mod_inv` | 与 Python 分支一致 |
| 5 | 3 个 fixture 测试：成员/非成员/错误 nonce |

**验收清单**：

- [ ] 非成员证明验证等式 `(d^prime * A_final^b) mod n == A0`
- [ ] 成员元素调用 `prove_non_membership` 返回 `None`
- [ ] `cargo test -p vads-crypto rsa_acc::non_membership` 全绿

---

### Day 7 — rsa_acc.rs（下）：batch + NI-PoE + delete

**目标**：批量操作与删除完整移植。

**前置**：Day 6

#### 上午（3h）

| # | 任务 |
|---|------|
| 1 | `batch_add`、`batch_delete` |
| 2 | `prove_exponentiation` / `verify_exponentiation`（Fiat-Shamir NI-PoE） |
| 3 | `shamir_trick`（移植 helpfunctions） |

#### 下午（3h）

| # | 任务 |
|---|------|
| 4 | `batch_prove_membership`、`batch_verify_membership` |
| 5 | `delete` 单条 |
| 6 | 集成测试：add×5 → delete×2 → acc 值与 Python 一致 |

**验收清单**：

- [ ] NI-PoE 验证：`Q^l * u^r == w`
- [ ] batch_add 后 acc 值正确
- [ ] `cargo test -p vads-crypto rsa_acc` 全绿

---

### Day 8 — pairing.rs（上）：类型 + 序列化 + 标量运算

**目标**：G1/G2/Fr 类型封装，点可序列化为 fixture 兼容 hex。

**前置**：Day 3（可与 Day 4–7 并行阅读 ark 文档）

#### 上午（3h）

| # | 任务 |
|---|------|
| 1 | `pairing.rs`：`G1Point`、`G2Point` 包装 `G1Affine`/`G2Affine` |
| 2 | `to_hex` / `from_hex` 使用 `ark-serialize` CanonicalSerialize |
| 3 | `g1_mul(u, s: u128)`、`g2_mul(g, alpha: Fr)` |

#### 下午（3h）

| # | 任务 |
|---|------|
| 4 | `g1_add`、`pairing(g2, g1) -> GT` |
| 5 | 测试：随机点序列化 roundtrip |
| 6 | 测试：配对双线性 smoke（`e(aP,bQ)` 类型检查） |

**验收清单**：

- [ ] G1/G2 hex 长度稳定（记录到 `fixtures/README.md`）
- [ ] `cargo test -p vads-crypto pairing::serialize` 通过
- [ ] 不依赖 fixtures 的 smoke 测试通过

---

### Day 9 — pairing.rs（下）：H_G 对齐日（关键）

**目标**：`hg_to_g1` 输出与 `fixtures/hg_samples` **完全一致**。

**前置**：Day 2（fixtures）、Day 8

> **这是全项目最高风险日**。若未通过，不进入 Day 11+。

#### 上午（3h）

| # | 任务 |
|---|------|
| 1 | 阅读 charm 源码或实验脚本：记录 `group.hash(sha256(str(x)), G1)` 行为 |
| 2 | 实现 `hg_to_g1(x)` 策略 A：SHA256(str(x)) → try-and-increment |
| 3 | 逐条对比 `fixtures/hg_samples` |

#### 下午（3h）

| # | 任务 |
|---|------|
| 4 | 若策略 A 失败：实现策略 B（复刻 charm BN254 hash-to-curve 字节流程） |
| 5 | 若仍失败：实现策略 C（`scripts/capture_hg_bruteforce.py` 建立查找表，仅测试环境） |
| 6 | 更新 `docs/ovds/HG对齐记录.md`：最终采用的算法与差异说明 |

**验收清单**：

- [ ] `hg_samples` 全部匹配（或文档记录可接受的等价判定）
- [ ] `verify_pairing(sign, right, pk, g)` 对 fixture append 条目通过
- [ ] **签字**：在 `HG对齐记录.md` 中注明采用策略及残余风险

**阻塞处理**：若 charm 不可分析 → 临时用 Python FFI 仅用于 HG（标记技术债），Rust 其他路径继续；不得静默跳过。

---

### Day 10 — wit_star.rs + vads-crypto 收尾

**目标**：`WitCreate_star` / `WitVerify_star` 完成；`cargo test -p vads-crypto` 全绿。

**前置**：Day 4–9

#### 上午（3h）

| # | 任务 |
|---|------|
| 1 | `wit_star.rs`：移植 `WitCreate_star`（`vads_lib.py` L133–250） |
| 2 | 移植 `H_Primes`（concat + hash_to_prime） |
| 3 | 移植 `EEA`（已在 bigint，复用） |

#### 下午（3h）

| # | 任务 |
|---|------|
| 4 | 移植 `WitVerify_star` |
| 5 | 对照 fixtures 或 Python 单步脚本验证聚合非成员证明 |
| 6 | **里程碑 M1**：`cargo test -p vads-crypto` 全部通过 |

**验收清单**：

- [ ] wit_star 创建+验证闭环测试通过
- [ ] `cargo test -p vads-crypto` 0 failed
- [ ] `vads-crypto` 公共 API 在 `lib.rs` 文档注释中列出

---

## Phase 2：vads-core（Day 11–18）

### Day 11 — 协议类型定义

**目标**：`Vk`、`Sk`、`ServerState`、`DbEntry`、`QueryProof` 等 Rust 类型就绪。

**前置**：Day 10

#### 全天任务

| # | 任务 |
|---|------|
| 1 | `vads-core/src/types.rs`：结构体替代 Python dict |
| 2 | `Vk`：存 `g,u,A,n,h,Acc_0` + 曲线点；不存闭包，改 fn 引用 |
| 3 | `Sk`：`alpha: Fr`、`cnt: u64`、`vk: Vk` |
| 4 | `ServerState`：`db: BTreeMap<u64, DbEntry>`、`r: HashSet<u128>`、`acc_r: BigInt`、`z_star: BigInt` |
| 5 | `DbEntry { s, sigma: G1Point, tag: u128 }` |
| 6 | `QueryProof`、`BatchProof`、`AuditProof` 子结构 |
| 7 | `serde` 序列化（为后续持久化准备） |

**验收清单**：

- [ ] `cargo build -p vads-core` 通过
- [ ] 类型单元测试：空 `ServerState` 默认值 `z_star=1`、`acc_r=Acc_0`
- [ ] 与 `fixtures/setup.json` 可手动构造 `Vk`

---

### Day 12 — setup()

**目标**：`vads-core::setup()` 与 Python `setup()` 输出结构等价。

**前置**：Day 11

#### 上午（3h）

| # | 任务 |
|---|------|
| 1 | `protocol/setup.rs`：调用 `vads-crypto::rsa_setup` + BN254 随机元 |
| 2 | 支持 `SetupOptions { seed: Option<u64> }` 测试模式 |
| 3 | 返回 `(Vk, Sk, ServerState)` |

#### 下午（3h）

| # | 任务 |
|---|------|
| 4 | 测试 `test_setup` 镜像：字段存在性断言 |
| 5 | 固定 seed 下 `n,h,Acc_0,u,A` hex 与 fixtures 一致 |
| 6 | `sk.cnt == 0`，`server_state.db` 为空 |

**命令**：

```powershell
cargo test -p vads-core setup
```

**验收清单**：

- [ ] 镜像 `test_setup.py` 全部断言通过
- [ ] 固定 seed fixture 对齐

---

### Day 13 — append_client + append_server

**目标**：拆分 append 两端，支持索引预占（`i` 不必等于 `cnt`）。

**前置**：Day 12

#### 上午（3h）

| # | 任务 | 对照 |
|---|------|------|
| 1 | `append_client(sk, s) -> (i, s, sigma, tag)` | `vads_lib.append_client` |
| 2 | `tag`：`rand u128` 或测试 RNG | `secrets.randbits(128)` |
| 3 | `sigma = (HG(i\|\|tag) + u^s)^alpha` | L468–473 |

#### 下午（3h）

| # | 任务 |
|---|------|
| 4 | `append_server(vk, state, i, s, sigma, tag) -> Result<()>` |
| 5 | 验签 `e(sigma,g)==e(HG·u^s,A)`；**不检查** `i==cnt` |
| 6 | 写入 `state.db[i]`；`append_client` 递增 `sk.cnt` |
| 7 | 镜像 `test_append.py` |

**验收清单**：

- [ ] 添加 s=100,200 后 db 大小正确
- [ ] 错误签名被拒绝
- [ ] fixture `append.json` 中 sigma 验证通过

---

### Day 14 — query + verify（单次）

**目标**：DataOnly 最小闭环：查询 + 客户端验证。

**前置**：Day 13

#### 上午（3h）— query

| # | 任务 |
|---|------|
| 1 | `query(vk, state, i) -> Option<(s, QueryProof)>` |
| 2 | 计算 `z_i = HPrime(tag_i)`，用缓存 `z_star` |
| 3 | `EEA(z_star, z_i)` → `(x,y)`，`Y = h^y mod n` |
| 4 | 构造 `pi_q = {sigma, tag, pi:{x,Y}}` |

#### 下午（3h）— verify

| # | 任务 |
|---|------|
| 5 | `verify(vk, s, i, pi_q, acc_r) -> Option<s>` |
| 6 | BLS 验签 + RSA 检查 `(Acc_R)^x * Y^z_i == h` |
| 7 | 镜像 `test_query.py` + `test_verify.py` |

**验收清单**：

- [ ] `fixtures/query_verify.json` 完整流程通过
- [ ] 篡改 `s` 或 `tag` 后 verify 返回 `None`
- [ ] `cargo test -p vads-core query_verify`

---

### Day 15 — query_star + verify_star（批量）

**目标**：批量查询/验证与 Python `query_star`/`verify_star` 一致。

**前置**：Day 14

#### 全天任务

| # | 任务 |
|---|------|
| 1 | `query_star(vk, state, indices: &[u64])` |
| 2 | 聚合 `Q_J` 素数集 + `WitCreate_star` 证明 |
| 3 | `verify_star(vk, values, indices, pi_q, acc_r, r)` |
| 4 | 镜像 `test_query_star.py`、`test_verify_star.py` |
| 5 | 至少 3 索引批量测试 |

**验收清单**：

- [ ] batch 证明结构字段与 Python 一致
- [ ] 部分索引不存在时行为与 Python 一致
- [ ] `cargo test -p vads-core batch` 通过

---

### Day 16 — update()

**目标**：单条更新维护 `R`、`Acc_R`、`z_star`。

**前置**：Day 15

#### 全天任务

| # | 任务 |
|---|------|
| 1 | `update(sk, i, s_prime, vk, state)` |
| 2 | 旧 tag 加入 `R`；`update_z_star` |
| 3 | 重签新 `(sigma', tag')`；更新 `db[i]` |
| 4 | 更新 `Acc_R`（按协议删除旧 tag 累加状态） |
| 5 | update 后旧 verify 失败、新 verify 通过 |

**验收清单**：

- [ ] update 前后 `z_star` 变化正确
- [ ] 旧 tag 的 verify 失败
- [ ] 至少 1 个集成测试覆盖 update→query→verify

---

### Day 17 — audit + judge

**目标**：审计路径可用（P2 能力，但测试套件要求）。

**前置**：Day 16

#### 全天任务

| # | 任务 |
|---|------|
| 1 | `audit(vk, indices, state) -> AuditProof` |
| 2 | `judge(vk, pi_a, acc_r, r) -> bool` |
| 3 | 镜像 `test_audit.py`、`test_judge.py` |
| 4 | 关注大整数内存（10+ 索引） |

**验收清单**：

- [ ] audit+judge 对全库和子集均通过
- [ ] 篡改 audit proof 后 judge 拒绝

---

### Day 18 — test_all 镜像 + 里程碑 M2

**目标**：`vads-core/tests/integration_test.rs` 一键跑通全流程。

**前置**：Day 11–17

#### 上午（3h）

| # | 任务 |
|---|------|
| 1 | 创建 `tests/integration_test.rs`：严格按 `test_all.py` 顺序 |
| 2 | 创建 `tests/common/mod.rs`：加载 fixtures、构建 seeded setup |

#### 下午（3h）

| # | 任务 |
|---|------|
| 3 | 失败用例逐个修到全绿 |
| 4 | **里程碑 M2**：`cargo test -p vads-core` 0 failed |
| 5 | 在 `vads-core/README.md`（crate 内）写公共 API 表 |

**命令**：

```powershell
cargo test -p vads-core
```

**验收清单**：

- [ ] 集成测试覆盖 setup→append→query→verify→query_star→verify_star→audit→judge
- [ ] 与 Python `test_all.py` 同等断言数量级
- [ ] M2 达成

---

## Phase 3：vads-engine + custody-vads（Day 19–22）

### Day 19 — VadsEngine 类型与错误码

**目标**：引擎层 trait 边界类型定义完毕。

**前置**：Day 18

#### 全天任务

| # | 任务 |
|---|------|
| 1 | `vads-engine/src/error.rs`：`VadsError` 枚举 |
| 2 | `vads-engine/src/types.rs`：`SetupParams`、`SignedBlock`、`AppendItem`、`QueryResult`、`QueryProof`（HTTP 友好） |
| 3 | `vads-engine/src/traits.rs`：`VadsEngine`、`IndexAllocator`（对齐接口规格 §2） |
| 4 | `bytes` ↔ `u128` 数据编解码约定（大端 / LEB128 选型并文档化） |

**验收清单**：

- [ ] trait 方法签名与 `vpin-custody-server-接口规格.md` §2 一致
- [ ] `cargo doc -p vads-engine` 可生成 trait 文档

---

### Day 20 — TenantVadsEngine：sign + append + query + verify

**目标**：单租户 `VadsEngine` 实现核心四轮。

**前置**：Day 19

#### 全天任务

| # | 任务 | 映射 |
|---|------|------|
| 1 | `TenantVadsEngine { sk, vk, state, allocator }` | 租户实例 |
| 2 | `setup()` | 初始化 |
| 3 | `sign_block(index, data) -> SignedBlock` | `append_client` 拆分 |
| 4 | `append(AppendItem)` | `append_server` |
| 5 | `query(index)` | `query` |
| 6 | `verify(index, data, proof)` | `verify` |

**验收清单**：

- [ ] 单租户：`reserve` 不适用，手动 `sign→append→query→verify` 闭环
- [ ] `cargo test -p vads-engine core_loop`

---

### Day 21 — IndexAllocator + batch + 里程碑 M3

**目标**：索引预占与批量接口完成。

**前置**：Day 20

#### 上午（3h）

| # | 任务 |
|---|------|
| 1 | `AtomicIndexAllocator`：`reserve(count)->base`，`current()` |
| 2 | `sign_block` 使用 `base+k` 而非 `cnt`（对齐工程优化 §4.2） |

#### 下午（3h）

| # | 任务 |
|---|------|
| 3 | `batch_append`、`query_batch`、`verify_batch` trait 方法 |
| 4 | `update`、`audit`、`judge` trait 方法（可先 `todo` 标记 P2） |
| 5 | **里程碑 M3**：`cargo test -p vads-engine` 全绿 |

**验收清单**：

- [ ] 并行预占 10 索引不重叠
- [ ] batch_verify 3 分片通过
- [ ] M3 达成

---

### Day 22 — vpin-custody-server workspace 骨架

**目标**：托管 workspace 编译通过，health 路由可访问。

**前置**：Day 21

#### 上午（3h）

| # | 任务 |
|---|------|
| 1 | 创建 `vpin-custody-server/Cargo.toml` workspace |
| 2 | `crates/custody-domain`：错误码、`CustodyCapabilityMode` |
| 3 | `crates/custody-vads`：re-export trait + `UnimplementedVadsEngine` |

#### 下午（3h）

| # | 任务 |
|---|------|
| 4 | feature `ovds-rust` → `path = "../ovds-server/crates/vads-engine"` |
| 5 | `apps/custody-server`：Axum + `GET /api/v1/health` |
| 6 | **里程碑 M4**：`cargo run -p custody-server` 返回 `{"status":"ok"}` |

**文件清单**：

```
vpin-custody-server/
├── Cargo.toml
├── apps/custody-server/src/main.rs
└── crates/
    ├── custody-domain/
    └── custody-vads/
```

**命令**：

```powershell
cd vpin-custody-server
cargo run -p custody-server
curl http://127.0.0.1:8003/api/v1/health
```

**验收清单**：

- [ ] 默认 feature 编译（stub 引擎）
- [ ] `--features ovds-rust` 编译并注入 `TenantVadsEngine`
- [ ] health 返回 200

---

## Phase 4：DataOnly HTTP（Day 23–28）

### Day 23 — custody-storage + 内存 MetadataStore

**目标**：会话与文件元数据可存取（内存实现）。

**前置**：Day 22

#### 全天任务

| # | 任务 |
|---|------|
| 1 | `crates/custody-storage`：`MetadataStore`、`ChunkStagingStore` trait |
| 2 | `InMemoryMetadataStore`：tenant、file、session |
| 3 | `InMemoryChunkStore`：`(session_id, chunk_k) -> bytes` |
| 4 | 单元测试 CRUD |

**验收清单**：

- [ ] session 状态机枚举：`Created/Uploading/Ready/Committing/Committed/Cancelled`
- [ ] `cargo test -p custody-storage`

---

### Day 24 — UploadCoordinator + 创建会话 API

**目标**：`POST /v1/files/upload-sessions` 可用。

**前置**：Day 23

#### 上午（3h）

| # | 任务 |
|---|------|
| 1 | `crates/custody-services/src/upload_coordinator.rs` |
| 2 | 创建会话：`total_chunks` → `IndexAllocator.reserve(N)` → `index_base` |
| 3 | 返回 `session_id`、`index_base`、chunk URL 模板 |

#### 下午（3h）

| # | 任务 |
|---|------|
| 4 | `crates/custody-api/src/routes/upload.rs` |
| 5 | `POST /v1/files/upload-sessions` handler |
| 6 | `GET /api/v1/capabilities` → `{"implemented":["data_only"]}` |
| 7 | curl 手工测试 |

**验收清单**：

- [ ] POST 返回 `session_id` + `index_base`
- [ ] 重复创建同 file 不冲突（或按 spec 返回 409）
- [ ] capabilities 路由可用

---

### Day 25 — 分片上传 + commit API

**目标**：`PUT chunks/{k}` + `POST commit` 将分片写入 VADS。

**前置**：Day 24

#### 上午（3h）

| # | 任务 |
|---|------|
| 1 | `PUT /v1/upload-sessions/{sid}/chunks/{k}`：暂存分片 + 验签字段 |
| 2 | 解码 `data_value` 为整数 `s` |
| 3 | 调用 `VadsEngine::append` |

#### 下午（3h）

| # | 任务 |
|---|------|
| 4 | `POST /v1/upload-sessions/{sid}/commit` |
| 5 | 会话 `READY→COMMITTING→COMMITTED` |
| 6 | `DELETE` 取消会话 → 不写 VADS |
| 7 | 3 分片上传 + commit 集成测试 |

**验收清单**：

- [ ] commit 后 VADS `db` 含 N 条
- [ ] 取消会话后 db 不变
- [ ] 错误签名返回 422

---

### Day 26 — Manifest + Download + VerifyOrchestrator

**目标**：文件 manifest 与下载验证计划。

**前置**：Day 25

#### 全天任务

| # | 任务 |
|---|------|
| 1 | `ManifestService`：`file_revision`、`chunk_map`（vads_index 列表） |
| 2 | `GET /v1/files/{fid}` → FileManifest |
| 3 | `VerifyOrchestrator`：按 `CustodyServerDefaults` 选 `verify_star` 或并行 `verify` |
| 4 | `GET /v1/files/{fid}/download?batch=k` → 分批计划 + proof |

**验收清单**：

- [ ] commit 后 `GET files/{fid}` 返回正确 chunk_map
- [ ] download 返回可验证的 proof 结构
- [ ] 至少 4 分片文件 batch 下载测试通过

---

### Day 27 — BindingService + 里程碑 M5

**目标**：`POST /v1/bindings` 产出 `ovds_verify_ref`。

**前置**：Day 26

#### 全天任务

| # | 任务 |
|---|------|
| 1 | `BindingService`：组装 `DataBindingRecord` |
| 2 | `POST /v1/bindings` handler |
| 3 | 字段：`file_id`、`vads_indices`、`ovds_verify_ref`、`capability_mode` |
| 4 | dev JWT 中间件（本地 Bearer `dev-token`） |
| 5 | **里程碑 M5**：9 条 DataOnly 路由全部 2xx（占位除外） |

**验收清单**：

- [ ] bindings 返回非空 `ovds_verify_ref`
- [ ] 无 token 返回 401
- [ ] M5 达成

---

### Day 28 — E2E：console 切换真实 OVDS

**目标**：关闭 `LocalCustodyShim`，console 走 `:8003` 完成上传闭环。

**前置**：Day 27

#### 上午（3h）

| # | 任务 |
|---|------|
| 1 | 启动 `custody-server :8003` |
| 2 | 确认 `config/client-endpoints.example.json` 指向 8003 |
| 3 | 定位 `vpin-console` 中 `TEMP-LOCAL-CUSTODY` 开关 |

#### 下午（3h）

| # | 任务 |
|---|------|
| 4 | 切换 bridge 到 `reqwest` → custody-server |
| 5 | 手工 E2E：create session → upload 2 chunks → commit → binding |
| 6 | **里程碑 M6**：记录 E2E 步骤到 `docs/ovds/E2E验证记录.md` |

**验收清单**：

- [ ] console 上传进度事件正常
- [ ] binding 含 `ovds_verify_ref`
- [ ] M6 达成
- [ ] E2E 文档含截图或日志摘录

---

## Phase 5：后续迭代（Day 29+，各 1 天/项）

以下不在 28 天 MVP 内，每项可独立排期：

| Day+ | 任务 | 验收 |
|------|------|------|
| D+1 | `custody-auth` JWT 真实校验（OIDC） | 非法 token 401 |
| D+2 | `custody-acl` 文件级 RBAC | 越权 403 |
| D+3 | SQLite `MetadataStore` 替换内存 | 重启后会话恢复 |
| D+4 | VADS 状态持久化（租户 pickle/SQLite） | 重启后 verify 仍通过 |
| D+5 | mmap `db_mmap.dat` 原型（1e6 条） | 随机 query O(1) |
| D+6 | `rug` 加速 hash_to_prime 基准 | 较 num-bigint 提速 ≥2× |
| D+7 | InferencePeer 路由 501 → stub 文档化 | 返回明确 error body |
| D+8 | `scripts/start-ovds-server.ps1` 加入 release 包 | build-release 通过 |

---

## 附录 A：每日站会模板（复制使用）

```markdown
## Day N 站会

- **昨日完成**：Day N-1 验收清单 x/x
- **今日目标**：（复制当日「目标」一行）
- **阻塞**：
- **风险**：
- **EOD 验收命令**：（复制当日命令块）
```

---

## 附录 B：fixture 文件索引

| 文件 | 生成 Day | 消费 Day |
|------|----------|----------|
| `environment.json` | 1 | 全程 |
| `setup.json` | 2 | 5, 12 |
| `hg_samples.json` | 2 | 9 |
| `append.json` | 2 | 13 |
| `query_verify.json` | 2 | 14 |
| `batch.json` | 2 | 15 |

---

## 附录 C：与上位方案映射

| 上位阶段 | 逐日范围 |
|----------|----------|
| 阶段 0 基线锁定 | Day 1–2 |
| 阶段 1 vads-crypto | Day 3–10 |
| 阶段 2 vads-core | Day 11–18 |
| 阶段 3 vads-engine + trait | Day 19–22 |
| 阶段 4 DataOnly HTTP | Day 23–28 |
| 阶段 5 持久化/规模 | Day 29+ |

---

## 附录 D：评审决策默认值（已写入计划）

若评审无异议，按以下默认执行：

1. 曲线：**BN254**
2. Workspace：**ovds-server/crates** + **vpin-custody-server**
3. 阶段 0：**Day 1–2 立即执行**
4. AVDS：**忽略**
5. HG：**Day 9 必须对齐后才继续**
