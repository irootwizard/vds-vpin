# OVDS 协议完整流程

## 一、文档说明

本文档描述 OVDS (Optimized Verifiable Data Streaming) 的**完整协议流程**，涵盖密码学层（VADS）与应用层（多模态数据处理）两个层次。

- **实现参考**：`src/vads_lib.py`（OVDS 主流程的唯一密码层实现）
- **应用方案参考**：`OVDS实际应用多模态数据方案.md`
- **安全参数**：λ = 128 bits；椭圆曲线 BN254；RSA 模数 3072 位

> **范围说明**：`src/additional/avds_lib.py` 与 `src/additional/clvc_aux.py` 属于**另一套 AVDS**（q=2 树 + CLVC 向量承诺），用于独立实验或对比实现，**不是**当前 OVDS 主流程的一部分。阅读或集成 OVDS 时请以 `vads_lib.py` 为准，勿与 AVDS 模块混用。

---

## 二、协议架构

### 2.1 分层结构

```
┌─────────────────────────────────────────────────────┐
│              应用层（OVDS 多模态封装）                  │
│  预处理 → 分块 → 整数编码 → 索引管理 → 重组与哈希校验    │
└────────────────────────┬────────────────────────────┘
                         │ 每个数据块作为整数 s 调用 VADS
┌────────────────────────▼────────────────────────────┐
│              密码层（VADS 核心协议）                  │
│  Setup → Append → Query/Verify → Update → Audit    │
└─────────────────────────────────────────────────────┘
```

### 2.2 参与方与状态

| 参与方 | 持有内容 | 说明 |
|--------|----------|------|
| **客户端** | `sk = {α, cnt, vk}` | 秘密密钥，含签名私钥 α 和计数器 |
| **客户端** | `file_index.json` | 文件 ID → VADS 块索引映射（应用层） |
| **服务器** | `vk` | 验证密钥（公参，可公开） |
| **服务器** | `DB = {i: (s, σ_i, tag_i)}` | 数据库存储 |
| **服务器** | `R` | 已撤销的 tag 集合（Update 产生） |
| **服务器** | `Acc_R`, `z_star` | RSA Accumulator 状态及缓存 |

### 2.3 密码学组件

| 组件 | 用途 |
|------|------|
| **BLS 签名**（BN254 配对） | 保证每条数据 `(i, s)` 的完整性与不可伪造 |
| **RSA Accumulator** | 证明 `tag_i ∉ R`（当前 tag 未被撤销） |
| **哈希函数 HG** | `{0,1}* → G1`，用于签名消息绑定 |
| **哈希函数 HPrime** | `tag → 素数`，用于 Accumulator 运算 |

---

## 三、阶段 0：Setup（系统初始化）

**算法**：`setup(security_param=128)`  
**触发时机**：系统部署或租户首次接入时执行一次。

### 3.1 客户端操作

```
1. 初始化 BN254 双线性配对群 (G1, G2, GT, e, p)
2. 随机生成 g ∈ G2（G2 生成元）
3. 随机生成 u ∈ G1
4. 随机生成秘密值 α ∈ Z_p
5. 计算公钥 A = g^α ∈ G2
6. 初始化 RSA Accumulator：
   - 生成 3072 位模数 n
   - 初始值 Acc_0 = h
7. 初始化哈希函数 HG, HPrime, H2
8. 设置计数器 cnt = 0
9. 构造验证密钥 vk = {group, g, u, A, n, h, Acc_0, HG, HPrime, ...}
10. 构造秘密密钥 sk = {α, cnt, vk}
```

### 3.2 服务器操作

```
1. 接收并保存 vk
2. 初始化服务器状态：
   - DB = {}
   - R = ∅
   - Acc_R = Acc_0
   - z_star = 1    # z* = ∏_{tag_j ∈ R} HPrime(tag_j) mod n
```

### 3.3 输出

```
(vk, sk, server_state)
```

客户端本地加密保存 `sk`（建议 AES-256）；`vk` 可同步给服务器及审计方。

---

## 四、阶段 1：Append（数据写入）

**算法**：`append_client` + `append_server`（或合并 `append`）  
**输入**：数据项 `s`（整数，由应用层文件块转换而来）

### 4.1 客户端 `append_client(sk, s)`

```
Step 1  i ← cnt                          # 分配单调递增索引
Step 2  tag_i ←$ {0,1}^λ                 # 随机 128 位标签
Step 3  σ_i ← (HG(i||tag_i) · u^s)^α     # BLS 签名
Step 4  cnt ← cnt + 1
Step 5  发送 (i, s, σ_i, tag_i) 至服务器
```

### 4.2 服务器 `append_server(vk, server_state, i, s, σ_i, tag_i)`

```
Step 1  验证 BLS 签名：
        e(σ_i, g) == e(HG(i||tag_i) · u^s, A)
Step 2  验证通过 → DB[i] ← (s, σ_i, tag_i)
        验证失败 → 返回 ⊥，拒绝写入
```

### 4.3 应用层封装（多模态存储）

```
1. 文件预处理
   ├─ 计算 SHA-256 文件哈希
   ├─ 按块大小分块（默认 1 MB）
   └─ 每块字节流 → 大整数 s

2. 逐块 Append
   ├─ 对每个块执行 append_client → append_server
   └─ 记录 vads_index 与 chunk_index 的映射

3. 更新客户端索引 file_index.json
   └─ 保存 file_id、metadata、chunk_indices
```

### 4.4 数据流示意

```
原始文件
  → [块0] → s₀ → append → DB[0] = (s₀, σ₀, tag₀)
  → [块1] → s₁ → append → DB[1] = (s₁, σ₁, tag₁)
  → ...
  → [块n] → sₙ → append → DB[n] = (sₙ, σₙ, tagₙ)
```

---

## 五、阶段 2：Query + Verify（查询与验证）

### 5.1 单次查询 `query(vk, server_state, i)`

**客户端**：根据 `file_index` 获取 VADS 索引 `i`，发送查询请求。

**服务器**：

```
Step 1  从 DB[i] 检索 (s_i, σ_i, tag_i)
Step 2  z_i ← HPrime(tag_i)
Step 3  利用缓存 z_star，通过 EEA 计算 (x, Y)
Step 4  构造非成员证明 π = (x, Y)
Step 5  构造 π_q = {σ_i, tag_i, π}
Step 6  返回 (s_i, π_q)
```

**非成员证明含义**：证明 `tag_i` 不在撤销集 `R` 中，即该数据项未被 Update 替换。

### 5.2 单次验证 `verify(vk, s_i, i, π_q, Acc_R)`

**客户端**：

```
Step 1  BLS 签名验证：
        e(σ_i, g) == e(HG(i||tag_i) · u^s_i, A)
Step 2  RSA 非成员证明验证：
        (Acc_R)^x · Y^z_i ≡ h (mod n)
Step 3  两步均通过 → 接受 s_i
        任一步失败 → 拒绝，返回 ⊥
```

### 5.3 批量查询 `query_star(vk, server_state, J)`

**输入**：索引集合 `J = [j₁, j₂, ..., jₖ]`（支持乱序、跨文件）

**服务器**：

```
Step 1  对每个 j ∈ J：
        - 从 DB[j] 取 (s_j, σ_j, tag_j)
        - Q_J 添加 HPrime(tag_j)
Step 2  生成聚合非成员证明 π_J = WitCreate*(Acc_R, R, Q_J)
Step 3  返回 (S_J, π_q = {items, π_J})
        其中 items = [(j, σ_j, tag_j) | j ∈ J]
```

### 5.4 批量验证 `verify_star(vk, S_J, J, π_q, Acc_R, R)`

**客户端**：

```
Step 1  聚合 BLS 验证：
        σ_J = ∏ σ_j
        s' = Σ s_j
        e(σ_J, g) == e(∏ HG(j||tag_j) · u^s', A)
Step 2  聚合非成员证明验证：
        WitVerify*(Acc_R, R, Q_J, π_J) == 1
Step 3  通过 → 接受 S_J
```

### 5.5 应用层数据恢复

```
1. 根据 file_id 从 file_index 获取所有块的 vads_index
2. 调用 query 或 query_star 获取各块数据（可随机顺序）
3. 对每块执行 verify 或 verify_star
4. 按 chunk_index 排序
5. 整数 → 字节流 → 拼接
6. 校验重组文件的 SHA-256 哈希
```

---

## 六、阶段 3：Update（数据更新）

**算法**：`update(sk, i, s', vk, server_state)`  
**场景**：修改索引 `i` 处已有数据块的值。

### 6.1 客户端操作

```
Step 1  从 DB[i] 取旧数据 (s_i, σ_i, tag_i)
Step 2  验证旧签名：
        e(σ_i, g) == e(HG(i||tag_i) · u^s_i, A)
Step 3  生成新标签 tag_i' ←$ {0,1}^λ
Step 4  计算新签名：
        σ_i' ← (HG(i||tag_i') · u^s')^α
Step 5  将 (i, s', σ_i', tag_i') 提交服务器
```

### 6.2 服务器操作

```
Step 1  验证新签名：
        e(σ_i', g) == e(HG(i||tag_i') · u^s', A)
Step 2  更新 DB[i] ← (s', σ_i', tag_i')
Step 3  将旧 tag 加入撤销集：R ← R ∪ {tag_i}
Step 4  更新 z_star ← z_star · HPrime(tag_i) mod n
Step 5  更新 Acc_R ← h^z_star mod n
```

### 6.3 关键语义

- 索引 `i` **不变**，数据值和 tag 均更新。
- 旧 `tag_i` 进入 `R` 后，基于旧签名的查询证明将验证失败。
- 应用层文件更新：仅对变更块执行 Update，并更新 `file_index` 元数据。

---

## 七、阶段 4：Audit + Judge（数据审计）

用于验证服务器是否篡改、丢失或伪造数据。

### 7.1 审计发起 `audit(vk, I, server_state)`

**输入**：审计索引集 `I`（`None` 表示全库审计）

**客户端**：

```
对每个 i ∈ I，随机选择挑战系数 v_i ∈ Z_p
生成挑战集 v_dict = {(i, v_i)}
```

**服务器**：

```
Step 1  初始化 ν = 0, σ_I = 1, Q_I = []
Step 2  对每个 i ∈ I：
        - 取 (s_i, σ_i, tag_i) from DB[i]
        - ν ← ν + v_i · s_i
        - σ_I ← σ_I · σ_i^v_i
        - Q_I 添加 HPrime(tag_i)
Step 3  生成 π_1 = WitCreate*(Acc_R, R, Q_I)
Step 4  返回 π_a = {ν, σ_I, π_1, tags, v_dict, I}
```

### 7.2 审计评判 `judge(vk, π_a, Acc_R, R)`

**客户端**：

```
Step 1  从 π_a 提取 {ν, σ_I, π_1, tags, v_dict, I}
Step 2  构造 Q_I = {HPrime(tag_i) | i ∈ I}
Step 3  RSA 证明验证：
        WitVerify*(Acc_R, R, Q_I, π_1) == 1
Step 4  计算 Γ = ∏_{i∈I} HG(i||tag_i)^v_i
Step 5  配对验证：
        e(σ_I, g) == e(Γ · u^ν, A)
Step 6  通过 → 返回 1；失败 → 返回 0
```

### 7.3 审计模式

| 模式 | 索引集 I | 适用场景 |
|------|----------|----------|
| 单文件审计 | 该文件所有块的 vads_index | 定点抽查 |
| 抽样审计 | 随机子集 | 大规模数据定期巡检 |
| 全库审计 | `I = None`（所有 DB 键） | 完整一致性校验 |

---

## 八、端到端生命周期

```
┌──────────┐                              ┌──────────┐
│  客户端   │                              │  服务器   │
└────┬─────┘                              └────┬─────┘
     │                                         │
     │  ══════ 0. Setup ══════                 │
     │  生成 sk, vk ──────────────────────────>│ 初始化 DB, R, Acc_R
     │                                         │
     │  ══════ 1. Append ══════                │
     │  文件分块 → 整数 s                       │
     │  append_client(i,s,σ,tag) ─────────────>│ append_server 验签存储
     │  更新 file_index                         │
     │                                         │
     │  ══════ 2. Query ══════                 │
     │  query(i) / query_star(J) ──────────────>│ 返回数据 + 证明
     │  verify / verify_star                   │
     │  重组文件 + SHA-256 校验                  │
     │                                         │
     │  ══════ 3. Update（可选）════════       │
     │  update(i, s') ────────────────────────>│ 更新 DB，旧 tag 入 R
     │                                         │
     │  ══════ 4. Audit（可选）════════        │
     │  生成挑战 v_i                            │
     │  audit(I) ─────────────────────────────>│ 返回聚合证明 π_a
     │  judge(π_a) → 1/0                       │
     │                                         │
```

---

## 九、算法与代码映射

| 协议阶段 | 算法名称 | 实现函数 | 执行方 |
|----------|----------|----------|--------|
| 初始化 | Setup | `setup()` | 客户端 + 服务器 |
| 写入（客户端） | Append-Client | `append_client()` | 客户端 |
| 写入（服务器） | Append-Server | `append_server()` | 服务器 |
| 写入（合并） | Append | `append()` | 客户端 + 服务器 |
| 单次查询 | Query | `query()` | 服务器 |
| 单次验证 | Verify | `verify()` | 客户端 |
| 批量查询 | Query* | `query_star()` | 服务器 |
| 批量验证 | Verify* | `verify_star()` | 客户端 |
| 更新 | Update | `update()` | 客户端 + 服务器 |
| 审计 | Audit | `audit()` | 客户端挑战 + 服务器响应 |
| 评判 | Judge | `judge()` | 客户端 |

---

## 十、消息与证明结构

### 10.1 Append 消息

```
Client → Server: (i, s, σ_i, tag_i)
```

### 10.2 Query 响应

```
Server → Client: (s_i, π_q)
π_q = {
    sigma_i: G1 元素,
    tag_i:   128 位整数,
    pi:      { x: 整数, Y: 整数 }   # RSA 非成员证明
}
```

### 10.3 Query* 响应

```
Server → Client: (S_J, π_q)
π_q = {
    items: [(j, σ_j, tag_j), ...],
    pi_J:  { x, Y }                  # 聚合非成员证明
}
```

### 10.4 Audit 响应

```
Server → Client: π_a
π_a = {
    nu:       域元素（聚合数据挑战响应）,
    sigma_I:  G1 聚合签名,
    pi_1:     { x, Y },
    tags:     { i: tag_i },
    v_dict:   { i: v_i },
    I:        索引列表
}
```

---

## 十一、安全属性

### 11.1 协议保证

| 属性 | 说明 |
|------|------|
| **完整性** | 服务器无法篡改 `s` 而不被客户端发现 |
| **可验证性** | 每次查询/审计均可密码学验证 |
| **不可伪造** | 无 `α` 无法生成合法 BLS 签名 |
| **撤销感知** | Update 后旧 tag 的证明自动失效 |
| **客户端轻量** | 无需长期保存原始数据，仅需 `sk` + 索引 |

### 11.2 协议不保证

| 属性 | 说明 |
|------|------|
| **对服务器保密** | 数据以明文整数 `s` 存储于 `DB`，服务器可见内容 |
| **访问隐藏** | 服务器可知查询了哪些索引 |
| **抗量子** | 基于 BN254 与 RSA，非后量子安全 |

---

## 十二、典型调用顺序

### 12.1 最小可用流程

```python
from vads_lib import setup, append, query, verify

vk, sk, server_state = setup()
result = append(sk, data_int, server_state)   # 写入
i = result[0]

s_i, pi_q = query(vk, server_state, i)        # 查询
verified = verify(vk, s_i, i, pi_q, server_state['Acc_R'])
```

### 12.2 完整生产流程

```python
from vads_lib import (
    setup, append_client, append_server,
    query_star, verify_star, update, audit, judge
)

# 1. 初始化
vk, sk, server_state = setup()

# 2. 批量写入（应用层先完成分块编码）
for s in chunk_integers:
    i, s, sigma, tag = append_client(sk, s)
    append_server(vk, server_state, i, s, sigma, tag)

# 3. 批量查询与验证
J = [0, 2, 1, 3]  # 可乱序
S_J, pi_q = query_star(vk, server_state, J)
S_J = verify_star(vk, S_J, J, pi_q, server_state['Acc_R'], server_state['R'])

# 4. 更新（可选）
update(sk, 0, new_value, vk, server_state)

# 5. 审计（可选）
pi_a = audit(vk, None, server_state)  # 全库审计
result = judge(vk, pi_a, server_state['Acc_R'], server_state['R'])  # 1=通过
```

---

## 十三、与相关模块的关系

| 模块 | 关系 |
|------|------|
| `OVDS实际应用多模态数据方案.md` | 应用层：多模态预处理、分块策略、索引管理 |
| `document/OVDS工程优化方案.md` | 工程层：大文件并行 Append/Update、会话、验证策略 |
| `document/OVDS数据托管服务器技术文档.md` | 服务层：托管架构、JWT/ACL、多租户 API |
| `src/vads_lib.py` | **密码层（主流程）**：VADS 协议完整实现，OVDS 依赖此模块 |
| `mmap_design.md` | 服务器端 DB 持久化方案（工程优化） |

### 13.1 非主流程模块（勿与 OVDS 混用）

| 模块 | 说明 |
|------|------|
| `src/additional/avds_lib.py` | **另一套 AVDS**：基于 q=2 树结构的可验证数据结构，与 VADS 协议不同 |
| `src/additional/clvc_aux.py` | AVDS 的依赖：CLVC（Commitment-Linked Vector Commitment）多项式承诺 |

上述 `additional/` 目录下的 AVDS + CLVC 代码为独立子系统，**不属于**本文档描述的 OVDS 主流程；其 Setup / Append / Query 等接口与 `vads_lib.py` 不兼容，不应在同一数据流中串联调用。

---

## 十四、总结

OVDS 协议由 **VADS 密码核心** 与 **多模态应用封装** 两层组成，完整生命周期为：

```
Setup → Append → [Query/Verify] → [Update] → [Audit/Judge]
         ↑                              ↓
    应用层：预处理/分块/索引        应用层：重组/哈希校验
```

协议的核心价值在于：在不可信服务器上实现**可验证的流式数据存储**，客户端以极小本地状态即可验证数据完整性；若需对服务器隐藏数据内容，须在应用层额外增加客户端加密，不属于当前 VADS 协议范畴。
