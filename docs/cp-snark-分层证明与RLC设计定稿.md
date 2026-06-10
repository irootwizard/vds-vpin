# CP-SNARK 分层证明与 RLC 设计定稿

> **总路线图（唯一权威）：** [`综合未来工作路线图.md`](./综合未来工作路线图.md) — 阶段排期、M1–M5、废止项、已完成项均以该文为准。  
> **本文：** 设计定稿附录（三线分工、式 (9)、γ 策略、废弃 mac_rlc 的理由）。  
> **状态：** 2026-06-10

---

## 0. 文档索引（相关文档须引用本文）

| 文档 | 与本文关系 |
|------|------------|
| [**`cp-snark-实现规格-逐步可编码.md`**](./cp-snark-实现规格-逐步可编码.md) | **编码前必读**：冻结事实、M1–M5、函数名、阻塞表 |
| [`cp-snark-full-架构草案.md`](./cp-snark-full-架构草案.md) | 目录树与类型草案；**§1 原则以本文修订为准** |
| [`各层计算量证明算法-论文对齐.md`](./各层计算量证明算法-论文对齐.md) | 论文各式与代码落点；**验证策略以本文 §4 为准** |
| [`mac_rlc-论文论证与实现对照-讨论稿.md`](./mac_rlc-论文论证与实现对照-讨论稿.md) | 历史讨论稿；**已 superseded 于合并 π_mac 与桩电路部分** |
| [`模型参数密码学绑定与客户端验证规范.md`](./模型参数密码学绑定与客户端验证规范.md) | 客户端 Verify 与 γ 协议；与本文 §3 一致 |
| [`CP-SNARK自检与计算量预估.md`](./CP-SNARK自检与计算量预估.md) | 现状差距表；引用本文区分「原代码已有」与「cp-snark 待做」 |
| [`vpin-平台架构-独立客户端与服务端（协议合规）.md`](./vpin-平台架构-独立客户端与服务端（协议合规）.md) | 平台 P4–P6；γ 须客户端采样 |
| [`vPIN论文与代码对照说明.md`](../vPIN论文与代码对照说明.md) | 原仓库 rLCL/rLCR 与证明入口 |
| [`src/cp-snark-full/src/layer_proof/README.md`](../src/cp-snark-full/src/layer_proof/README.md) | 三条管线说明 |
| [`src/cp-snark-full/README.md`](../src/cp-snark-full/README.md) | crate 入口 |

---

## 1. 三条管线（必读，禁止混称）

```text
[A] 原仓库 · Python 同态推理（权威「计算侧」）
    cnn_networks/Server.py（及 convolution/Server.py）
      → rLCL / rLCR + assert
      → points_mult / point_one_Add 等 witness
      → rust_files/{network}/pointAdd|pointMult/*.json
    特点：式 (9)(10) 的 RLC **已在推理中实现**；挑战为服务器本地 pf(secret_key,i)，**非**客户端 γ。

[B] 原仓库 · Spartan 子证明（权威「EC gadget」）
    vPIN_proof_generation: proof_point_add / proof_point_mult
    特点：整网一批 PtAdd + 一批 PtMul；**不陈述**式 (9)(10)；**无** challenge 轮次。

[C] cp-snark-full（平台协议编排 · 演进中）
    prove/verify pipeline + ClientChallenge + ProtocolArtifacts
    特点：可接客户端 γ；**当前** mac_proof=None，π 实质仍为 [B]；
          layer_proof 标量 check 为开发期预检，**不是**产品级 Verify。
```

**口诀：** [A] 算对了什么 · [B] EC 代数 gadget 对不对 · [C] 如何把 [A][B] 绑成客户端可验协议。

---

## 2. 式 (9) 与原代码：已实现 vs 未实现

论文卷积 RLC（式 (9)）：

$$
\sum_r \gamma^r \hat{a}_r \;=\; \sum_r \gamma^r \langle f,\,\text{window}_r\rangle
$$

### 2.1 原代码（[A]）— **计算侧已实现**

| 论文侧 | 原代码 | 文件 |
|--------|--------|------|
| 左端 $\sum \gamma^r \hat{a}_r$ | `rLCL(output_flatten, secret_key, …, type=0)` | `Server.py` |
| 右端（RLC 后 MAC 链） | `rLCR(filter, windows, secret_key, …, type=0)` | 同上 |
| 系数 $\gamma^i$ | `pf(secret_key, i)`（HMAC-PRF） | `pf()` |
| 挑战来源 | `secret_key = os.urandom(32)`，**服务器本地** | 同文件 |
| 检查方式 | `assert result_left == result_right` | **调试自检，非客户端验证** |

FC 式 (10)：`rLCL`/`rLCR` `type=1`，同一模式。

**结论：** 线性压缩方程在 **Python 推理路径中已等价实现**；`cp-snark-full` 的 `layer_proof::rlc` 是用论文符号 $\gamma^i$ 在**标量域重写同一等式**，不是新算法。

### 2.2 原代码（[B]）— **未把式 (9) 作为 SNARK 陈述**

- `prove_point_mult` 只证每次 PtMul 的 R1CS gadget；
- **不证**「全体 witness 满足式 (9)」；
- witness 来自 [A] 中 `rLCR` 填写的 `points_mult` / `weights_array`。

### 2.3 cp-snark-full 误加路径（**已废弃于设计，代码仍可能存在**）

| 组件 | 问题 | 定稿处置 |
|------|------|----------|
| `verify_conv_eq5` + `verify_conv_eq9` 串联 | eq9 在客户端 γ 下已足够；eq5 对 **验证** 冗余 | **验证只保留 eq9/eq10**；eq5 仅作单元测试或 prover 调试 |
| `circuit/mac_rlc` 桩（电路外算 left/right） | 与标量 check 重复；不证 witness 语义 | **不接入** `prover_pipeline`（现状 `mac_proof=None` 保持） |
| 合并 `MacRlcProof`（conv+fc 一个 π） | 违背「各层分开出证明」 | **改为按层** `π_conv` / `π_pool` / `π_fc` |
| `rlc_binding_hex` | SNARK 外弱绑定 | 删除或并入 transcript；不作为安全依据 |

---

## 3. 随机挑战 γ / γ′

### 3.1 角色对照

| | 论文 / 合规协议 | 原 Python [A] | cp-snark-full `ClientChallenge` |
|--|-----------------|---------------|----------------------------------|
| 卷积 γ | 验证方随机 | `pf(secret_key,i)` | `gamma`（**目标：仅客户端采样**） |
| FC γ′ | 验证方随机 | 同上 type=1 | `gamma_mult` |
| 池化 | **无** RLC | 无 | `gamma_add` **未用于池化**（勿误用） |

### 3.2 交互性

| 路径 | 是否交互 |
|------|----------|
| 原仓库 [A]+[B] | **非交互**：推理与证明同机/同批 JSON，无 challenge 消息 |
| 平台合规 [C] | **一轮交互**：客户端 P4 发 γ → 服务端 P5 prove（`sample-challenge` / `prove-with-challenge`） |
| SNARK 内部 FS | **非交互**（transcript 派生挑战） |

### 3.3 服务器知晓 γ 时

- **仅标量 RLC 检查**且 γ 由服务器预知：**可伪造**该检查（Freivalds 失效）。
- **γ 为公开输入且式 (9) 在 R1CS 内完整编码**：知晓 γ **不等于**能伪造 π（仍须满足 SNARK soundness）。
- **原 `pf(sk)` 自检**：不面向恶意服务器，**不得**替代客户端 γ。

---

## 4. MAC 与 RLC：什么重复、什么不重复

### 4.1 不重复（必须保留）

| 对象 | 说明 |
|------|------|
| 同态推理中的 MAC / PtMul 链 | `rLCR` **就是在算** $\langle f,\text{window}_r\rangle$ 的 RLC 压缩版；是**计算本体** |
| 每层 EC gadget 证明 | PtAdd/PtMul SNARK 证轨迹上每一步 EC 代数 |

### 4.2 对验证冗余（定稿删除或降级）

| 对象 | 说明 |
|------|------|
| 逐格 `verify_conv_eq5` **作为客户端必验步骤** | 在客户端随机 γ 下，**仅 eq9 足够** |
| `mac_rlc` 桩 SNARK | 与标量 eq9 **三重重复** |
| 标量 eq9 + Python assert + mac_rlc 同时存在 | 只保留一条验证链 |

### 4.3 逻辑关系（验证方）

```text
客户端 γ 已知且随机
  → 仅检查式 (9)  [卷积]
  → 仅检查式 (10) [FC]
  → 仅检查式 (7)  [池化，无 γ]
  → 再加该层 π_ec（PtAdd/PtMul gadget）

不需要：先 eq5 再 eq9（eq5 仅当调试「展开 RLC」时使用）
```

---

## 5. 目标架构：各层分开出证明

### 5.1 原则（修订 P2 / P4）

| # | 定稿原则 |
|---|----------|
| P2′ | **陈述按层、证明按层**：Conv / Pool / FC 各产出可独立验证的 π 块（可共享同一 transcript） |
| P4′ | **RLC 优先**：卷积只证式 (9)；FC 只证式 (10)；池化只证式 (7) + PtAdd |
| P3 | 不变：标量 `check_scalar` 仅供 prover 自检/测试；**客户端只验 π + transcript** |
| P1 | 不变：一个 $\mathsf{cm}_W$，不为每层各建 cm |

### 5.2 目标产物（`ProtocolArtifacts` 演进）

```text
π_conv   — 公开输入含 γ_conv；陈述 = 式 (9)（in-circuit 或 π_mac_conv + π_ec_conv 子块）
π_pool   — 陈述 = 式 (7)；π_ec 仅 PtAdd
π_fc[k]  — 公开输入含 γ′；陈述 = 式 (10)
```

**禁止：** 单个 `mac_rlc` 桩把 left/right 在电路外算完再约束相等。

### 5.3 witness 来源

- 仍由 [A] `Server.py` 推理 + `rLCR`/`rLCL` 产生；
- [C] 只改：**γ 由客户端注入**替换 `pf(secret_key,i)` 用于**验证侧**与 transcript；
- 推理侧可继续用 PRF 做服务器自检，但与 P4 客户端 γ **解耦**。

---

## 6. 实现状态快照（2026-06-10）

| 能力 | [A] Python | [B] vPIN_proof_generation | [C] cp-snark-full |
|------|------------|---------------------------|-------------------|
| 式 (9) 计算 | ✅ rLCL/rLCR | — | —（复用 trace） |
| 式 (9) 客户端验证 | ❌ | ❌ | ⚠️ 标量 eq9 可跑，未进 SNARK |
| 式 (9) in-circuit π | ❌ | ❌ | ❌（mac_rlc 桩已停用） |
| EC gadget π | witness 已采集 | ✅ 整批 | ✅ 整批（同 [B]） |
| 客户端 γ | ❌ | ❌ | ⚠️ API 有，生产未闭合 |
| 按层分开 π | ❌ | ❌ | ❌ **目标** |

---

## 7. 对协作者的要求

1. 新增文档或代码注释涉及 RLC/MAC/γ 时，**须引用本文**并标明属于 [A]/[B]/[C] 哪条管线。  
2. 不得将 `layer_proof::verify_eq5` 描述为客户端必验步骤。  
3. 不得将 `mac_rlc` 桩描述为已实现的安全 π_mac。  
4. 不得声称「式 (9) 仅在 cp-snark-full 实现」— **原 Server.py 已实现计算侧**。  
5. UI/产品文案：`proof_coverage` 须与 §6 表一致，禁止过度宣称。

---

## 8. 修订记录

| 日期 | 说明 |
|------|------|
| 2026-06-10 | 初版定稿：澄清三线分工、式 (9) 已在原代码、γ 客户端化、废弃合并 mac_rlc 与双标量验证、按层 π 目标 |
