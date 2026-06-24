# AHE 批量推理性能优化设计

> 状态：设计评审稿（不含实现）
> 范围：Network A（`cnn-mnist`）纯 AHE 同态推理 P0–P3 闭环
> 目标：把"逐图串行 ~33s/张"优化为可并行的批量推理，并评估算法级打包可行性

---

## 1. 现状与瓶颈

### 1.1 当前串行实现

```
vpin_client/pipeline/batch.py :: run_mnist_batch
  for i in range(limit):
      await run_ahe_inference(job)   # 一张做完才下一张
```

每张图独占一条 WebSocket 会话，循环内 `await` 完全串行。实测 10 张 ≈ 330s，单张 ≈ 33s。

### 1.2 单张推理算子规模（实测 op counters）

| 指标 | 值 |
|------|---|
| 服务端 EC 点乘 (`pt_mult`) | ~18,560 |
| 服务端 EC 点加 (`pt_add`) | ~18,330 |
| 客户端 BSGS 解密 cell 数 | conv 1024 + pool 64 + fc1 16 + fc2 10 |

### 1.3 时间分布与可并行性

| 环节 | 执行位置 | 主要成本 | 现状并行 |
|------|---------|---------|---------|
| keygen + BSGS prewarm | 客户端/会话启动 | 加载 230MB pickle、起进程池 | ❌ 每会话重复 |
| 输入加密（1024 cell） | 客户端 | EC 点乘 | ✅ 线程池 |
| Conv / Pool / FC1 / FC2 同态 | **服务端 event loop 线程** | EC 点运算 | ❌ 同步阻塞 |
| 各层解密 | 客户端 | BSGS giant-step | ✅ 3 进程池 |

**根本瓶颈**：服务端同态 EC 运算是纯 Python（`ecdsa`），同步阻塞跑在 asyncio event loop 线程内。即使开多条并发 WS，受 GIL + 阻塞调用影响，服务端无法真正并行。

---

## 2. 可共享 / 不可变数据清单

并发与流水线设计的前提，是先界定哪些数据**只读可共享**、哪些**必须每图独立**。

### 2.1 全局只读（跨会话、跨图共享，零拷贝/单例）

| 数据 | 位置 | 说明 |
|------|------|------|
| 曲线参数 / 生成元 G / 单位元 | `curve_e2_info()` | 常量 |
| 模型权重（conv 滤波器、fc1/fc2、bias） | `AheEngine.weights` | 注册即固定，只读 |
| BSGS 解密表（~230MB） | `load_bsgs_table` | 进程内单例缓存，进程池各 worker 各一份 |

### 2.2 每批次可共享（一个客户端的一批图复用一次）

| 数据 | 现状 | 优化点 |
|------|------|--------|
| 客户端密钥对 (sk, h=sk·G) | 每会话 `key_gen()` 重生成 | **整批复用一对密钥**：加性同态正确性不依赖每图换密钥；省 keygen + 公钥预计算 |
| bias 密文 `Enc(b_fc1)/Enc(b_fc2)` | 每层 `encrypt_bias` 现加密 | **每密钥对只加密一次**：bias 跨图不变，ElGamal 随机性不影响加性结果 → 整批复用 |
| BSGS 进程池 | 每会话 prewarm | 进程池整批只初始化一次 |

> 安全性说明：批内复用密钥对仅在"同一客户端、同一信任域"成立。跨客户端绝不复用。bias 密文复用不泄露额外信息（服务端本就持有明文权重）。

### 2.3 必须每图独立（不可共享）

| 数据 | 原因 |
|------|------|
| 输入密文 `Enc(x_i)` | 每图不同 |
| 各层中间密文张量 | 每图推理状态 |
| `AheEngine.phase` 状态机 | 每图独立推进 |

---

## 3. 方案 A：算法级密文打包（评估结论：**当前不可行**）

### 3.1 EC-ElGamal 没有 CKKS 式 slot

CKKS/BFV 等格基 HE 把向量打包进多项式 slot，可天然 SIMD。本系统是**椭圆曲线加性 ElGamal**，每个标量单独加密成 `(c1, c2)` 点对，**没有 slot 结构**。"把 B 张图同一像素位打进一个密文"在本方案里只有一种实现路径——**位置式整数打包**。

### 3.2 位置式打包原理与约束

把 B 张图同位置的值编码进一个标量：

```
m_packed = m_1 + m_2·D + m_3·D² + … + m_B·D^(B-1)
```

线性运算（点加、共享权重的标量乘）在各 lane 间天然分配，**前提是不发生跨 lane 进位**：

- `D` 必须大于该层线性运算后任一 lane 的最大幅值
- 整体打包值 `≈ D^B` 必须落在 BSGS 可解密范围内

无进位打包因子上界：

```
B_max = ⌊ log2(BSGS_range) / 每lane比特宽 ⌋
```

### 3.3 实测：BSGS 范围已被单图占满

| 量 | 值 | 比特 |
|----|----|----|
| BSGS 可解密范围（m=3.2e6, ±m²） | ±1.024×10¹³ | **43.2 bit** |
| conv 输出最大幅值 | 520,168 | 19 bit |
| pool 移位前最大 | 446,974,976 | 29 bit |
| fc1 relu 前最大 | 67,653,985,329 | 36 bit |
| fc2 relu 前最大 | 117,197,641,375 | **37 bit** |

按正确的位置式上界 `⌊43.2 / 每lane比特⌋`：

| 层 | 每lane比特 | B_max（无进位） |
|----|-----------|----------------|
| conv | 19 | 2 |
| pool | 29 | 1 |
| fc1 | 36 | 1 |
| **fc2** | **37** | **1** |

### 3.4 结论

- **FC1/FC2/Pool 层 B_max = 1**：连 2 张都打不进，因为单图动态范围（37 bit）已逼近 BSGS 上限（43 bit），仅剩 ~6 bit 余量。
- **仅 conv 层 B_max = 2**：但客户端在每层边界都要解密+截断，conv 之后立刻被 pool 的幅值膨胀（×inv_fp 再求和）顶破，且需额外的打包/拆包与无进位证明，收益（半条流水线 2×）远不抵复杂度与正确性风险。

> **打包要可行，必须先改底层密码学**：
> 1. 扩大 BSGS 表（m↑ → giant-step 循环时间/内存平方增长，已 m=3.2M），或
> 2. 更激进截断压缩单图动态范围（牺牲精度，当前定点已 90%），或
> 3. 迁移到格基 HE（CKKS/BFV，有真 slot + 大明文模数）——研究级重写。
>
> 三者都超出 MVP 范围。**密文打包暂不纳入路线。**

---

## 4. 方案 B：分层流水线并行（推荐核心）

利用"推理天然分层 + 协议 client/server 交替"的结构做流水线，是当前架构下收益最高、不动密码学的方案。

### 4.1 阶段划分（单图 8 阶段，server/client 交替）

```
S1 conv ─ C1 decrypt+relu ─ S2 pool ─ C2 decrypt+shift ─
S3 fc1  ─ C3 decrypt+relu+shift ─ S4 fc2 ─ C4 decrypt+relu+argmax
```

- S* = 服务端同态 EC 运算（CPU 密集，阻塞）
- C* = 客户端 BSGS 解密 + 非线性（已可多进程）

### 4.2 流水线重叠

串行：总时间 = Σ(所有阶段)。
流水线：图 i 在 S_k 时，图 i-1 在 C_k、图 i-2 在 S_{k+1}…重叠后吞吐由**最慢的单一阶段**决定（瓶颈级）。

```
时间 →
图1: S1 C1 S2 C2 S3 C3 S4 C4
图2:    S1 C1 S2 C2 S3 C3 S4 C4
图3:       S1 C1 S2 C2 S3 C3 S4 C4
```

理想稳态吞吐 ≈ 1 / max(单阶段耗时)，相对串行可逼近 stage 数倍（受瓶颈阶段与资源约束）。

### 4.3 调度器设计

```
BatchScheduler
  - 共享：1 个密钥对、1 套 bias 密文、1 个 BSGS 进程池、1 个服务端计算执行器
  - in_flight: List[ImageState]（各自 phase + 中间密文）
  - server_executor: ProcessPoolExecutor（卸载 S* 阻塞计算，见方案 C）
  - decrypt_pool: 复用现有解密进程池（C*）
  - 事件循环：每个 ImageState 完成一个阶段就投递下一阶段，server/client 阶段分派到各自执行器
  - 背压：Semaphore 限制 in_flight 数（受内存约束，见 §6）
```

### 4.4 正确性约束

- 各图状态机严格隔离，禁止共享中间密文。
- 共享只读资源（权重、bias 密文、BSGS 表）只读访问，无写竞争。
- 单图内部阶段仍严格 S1→C1→…→C4 有序；并行只发生在**不同图之间**。

---

## 5. 方案 C：服务端进程池卸载（解锁真正并发）

流水线要真正并行，必须解决"服务端阻塞 event loop"。

### 5.1 改造点

把 `conv2_ciphertext / avg_pool_ciphertext / fc1_layer / fc2_layer` 用
`loop.run_in_executor(ProcessPoolExecutor, …)` 卸载到工作进程。

### 5.2 难点

| 难点 | 说明 | 对策 |
|------|------|------|
| EC `Point` 跨进程序列化 | `ecdsa.Point` 需可 pickle | 传 `(x, y)` 整数对，worker 内用共享曲线重建 |
| 权重/曲线重复加载 | 每 worker 初始化 | `initializer` 预载权重与曲线（只读） |
| 进程数 vs 内存 | 见 §6 | 限并发度 = CPU-1，且与解密池错峰 |

### 5.3 与流水线的关系

方案 C 是方案 B 的使能项：没有 C，B 的 server 阶段仍在主线程串行排队。二者需同步落地。

---

## 6. 资源约束与并发度

| 约束 | 数值 | 影响 |
|------|------|------|
| BSGS 表常驻内存 | ~230MB / 进程 | 解密池 3 进程 ≈ 690MB；服务端计算池无需 BSGS |
| CPU 核数 | 影响总并发度 | 计算池 + 解密池总进程数 ≤ 物理核 |
| 单图中间密文内存 | conv 1024 点对×2 等 | in_flight 上限受内存约束 |

**推荐并发度**：先验证 in_flight=2、服务端计算池=2、解密池沿用 3，压测后再调。

---

## 7. 综合推荐架构

```
            ┌─────────────────────── BatchScheduler ───────────────────────┐
            │  共享: keypair · bias密文 · BSGS池 · 权重(只读)               │
            │                                                               │
  图队列 ─► │  in_flight (Semaphore 限流)                                   │
            │    每图: phase 状态机 + 中间密文                              │
            │      ├─ server 阶段 ─► ProcessPool(计算, 重建曲线)  ← 方案C   │
            │      └─ client 阶段 ─► ProcessPool(BSGS 解密, 复用)          │
            └───────────────────────────────────────────────────────────────┘
```

- 方案 B（流水线）+ 方案 C（服务端卸载）+ §2 数据共享 = 完整批量方案
- 方案 A（打包）在当前 BSGS/截断参数下不可行，列为"需先改密码学"的长期项

---

## 8. 分阶段路线（建议）

| 阶段 | 内容 | 风险 | 预期收益 |
|------|------|------|---------|
| P1 | §2 共享化：批内复用 keypair + bias 密文 + BSGS 池单次初始化 | 低 | 单张省 2–5s 固定成本 |
| P2 | 方案 B+C：流水线调度 + 服务端进程池卸载 | 中高 | 批量吞吐逼近瓶颈阶段倍数（~2–3×） |
| P3 | 算法级（打包/换 HE 后端） | 高/研究级 | 数量级，但需改密码学，暂缓 |

---

## 9. 验收口径（实现阶段使用）

- **正确性优先**：批量结果必须与现串行逐图结果 **逐图 bit-exact**（prediction 与 logits 完全一致），否则视为回归。
- 用 `scripts/ahe_e2e_smoke.py` 单图基线 + `eval-mnist-ahe` 批量交叉校验。
- 性能指标：批量总耗时、单图均摊耗时、稳态吞吐（图/分钟）。

---

## 附：关键证据

- BSGS 范围 ±43.2 bit、各层动态范围（19/29/36/37 bit）均为本机实测（`model_training/outputs/20260622_184254` 权重，MNIST test）。
- 串行基线：10 张 330s（≈33s/张），op counters：pt_mult≈18.5k / pt_add≈18.3k / 图。

---

## 10. 实测数据档案（2026-06-24，本机基准）

> 环境：16 核 CPU；权重 `model_training/outputs/20260622_184254`（cnn-mnist-trained，Network A）；
> BSGS 表 `src/Pre_computed_table/table.pickle`（~230MB）；后端 `127.0.0.1:8000`。
> 所有"正确性"均以 AHE 密文路径与定点明文路径 `logit_max_diff == 0.0`（bit-exact）为准。

### 10.1 单层算子成本（单进程，1024-cell conv 层）

| 阶段 | 耗时 | 位置 | 说明 |
|------|------|------|------|
| 输入加密 1024 cell | **10.4s** | 客户端 | 优化前：ThreadPool，GIL 绑定，等效单核 |
| 服务端 conv（1→1024） | **0.3s** | 服务端 | 同态 EC，**非瓶颈** |
| 解密 conv 1024 cell | **6.1s** | 客户端 | ProcessPool 3 worker（BSGS giant-step） |

**结论**：瓶颈在客户端加解密，不在服务端同态计算。服务端进程池卸载（P2）只改善跨会话并行，单图瓶颈是加密。

### 10.2 加密进程池化前后（1024 cell，热态）

| 实现 | 耗时 | 倍数 |
|------|------|------|
| ThreadPool（GIL 绑定，优化前） | 10.4s | 1× |
| ProcessPool（`_encrypt_parallel_mp`，8 worker） | **2.6s** | **4×** |

正确性：MP 加密结果解密后与顺序加密、与原始明文**逐元素相等**。

### 10.3 端到端单图推理

| 场景 | 耗时 | 备注 |
|------|------|------|
| 优化前（基线） | ~42s | — |
| MP 加密后 · 热态稳态 | **19.4s** | **2.2×**；池已 spawn，无冷启动 |
| MP 加密后 · CLI 冷启动单次 | 50–71s | 含 ~11 进程池 spawn（8 加密 + 3 解密 BSGS×230MB），单图不摊销 |

> 冷启动开销仅一次性，批量场景被摊销；单图延迟敏感可调小 `VPIN_AHE_ENCRYPT_WORKERS`。

### 10.4 批量吞吐

| 配置 | 张数 | 总耗时 | 均摊/张 | acc | 备注 |
|------|------|--------|---------|-----|------|
| 串行（优化前） | 10 | 330s | 33s | — | 原始基线 |
| 串行（MP 加密） | 10 | 278s | 27.8s | 90% | 含冷启动 |
| 并发=2（仅 P1+P2，未 MP 加密） | 4 | 122s | 30.5s | 100% | 两两并行可见 |
| 并发=4（P1+P2 + MP 加密） | 4 | 69s | 17.2s | 100% | 预测 [7,2,1,0]=标签 |
| 并发=4（P1+P2 + MP 加密） | 10 | **124s** | **12.4s** | 90% | 相对优化前 **2.66×** 吞吐 |

### 10.5 准确率基线（与性能无关，留档）

| 路径 | 样本 | 准确率 |
|------|------|--------|
| float 模型 | 10000 | 92.93% |
| 定点同态明文 | 100 | 90.0% |
| AHE 密文（=定点，bit-exact） | 10 | 90.0% |

### 10.6 改动与依据对照

| 改动 | 文件 | 依据（本档数据） |
|------|------|------------------|
| 客户端加密 ThreadPool→ProcessPool | `vpin-client/.../crypto/ahe/codec.py` `_encrypt_parallel_mp` | §10.1 加密 10.4s 为最大单项；§10.2 实测 4× |
| 服务端同态卸载到 ProcessPool（P2） | `vpin-backend/.../api/routes/session.py`、`inference/ahe_worker.py` | §10.1 服务端单层 0.3s（解锁跨会话并行，非单图加速） |
| 批内共享 keypair（P1） | `vpin-client/.../protocol/ws_ahe_client.py`（可选 `keys`）、`pipeline/batch.py` | §2 keypair 跨图可复用；省 keygen 固定成本 |
| 批量并发驱动 + `--concurrency` | `vpin-client/.../pipeline/batch.py`、`cli.py` | §10.4 并发吞吐提升 |
| bias 密文缓存（P1-服务端）**未做** | — | bias 加密 ~26 次 vs 18k 算子（<0.2%），收益边际，风险不划算 |

### 10.7 可调参数（环境变量）

| 变量 | 默认 | 作用 |
|------|------|------|
| `VPIN_AHE_ENCRYPT_WORKERS` | min(8, 核-1) | 客户端加密进程数 |
| `VPIN_AHE_SERVER_POOL` | 1 | 服务端同态卸载开关（0 关闭回退） |
| `VPIN_AHE_SERVER_WORKERS` | min(3, 核-1) | 服务端同态进程数 |
| 解密 worker（硬编码） | min(3, 核-1) | `codec.py _get_mp_decrypt_pool`，16 核下可放宽至 6–8（待验证） |

### 10.8 待办（基于以上数据）

1. 解密池 worker 数放宽（当前硬编码 3，16 核欠用）：§10.1 解密 6.1s 是第二大单项。
2. Tauri 单图场景：后端常驻 + 客户端池复用，消除冷启动（§10.3 冷启动 30s+）。
## 11. 前端 UI 适配建议（批量推理）

当前 `/demo/ahe` 仅实现了单图推理交互（`aheInfer`）。底层 `vpin_client` 已支持并发批量评估，要在前端开放此能力，建议如下适配：

### 11.1 交互设计

1. **入口**：在「样本预览」卡片增加「批量评估」按钮（例如：`评估当前预览的 N 张图`）。
2. **进度反馈**：
   - 批量模式下不展示详细的单图 P0–P3 trace（信息量过大导致 UI 卡顿）。
   - 改为展示**进度条**（`已完成 / 总数`）和**实时指标**（`当前准确率`、`已耗时`、`ETA`）。
3. **结果展示**：
   - 完成后展示汇总表格：`序号 | 标签 | 预测 | 结果 (✅/❌)`。
   - 顶部展示最终准确率和总耗时。

### 11.2 Tauri 接口扩展

在 `src-tauri/src/lib.rs` 中新增命令绑定 `eval-mnist-ahe` CLI：

```rust
#[tauri::command]
async fn run_ahe_batch(
    limit: u32,
    concurrency: u32,
    backend_ws: String,
    model_id: String,
    window: tauri::Window,
) -> Result<serde_json::Value, String> {
    // 1. 构造参数: vpin_client eval-mnist-ahe --limit {limit} --concurrency {concurrency} ...
    // 2. 必须开启 --progress，并通过 stdout 解析进度
    // 3. 解析到 [  3/10 ] correct=2 acc=... 时，通过 window.emit("batch-progress", payload) 推送给前端
    // 4. 结束后读取 reports/batch_{limit}_*.json 返回最终结果
}
```

### 11.3 前端状态管理

在 `useAheDemoSession.js` 中新增批量状态：

```javascript
const batchState = reactive({
  running: false,
  limit: 10,
  completed: 0,
  correct: 0,
  accuracy: 0,
  elapsed_s: 0,
  eta_s: 0,
  results: []
});
```

通过 Tauri 的 `listen("batch-progress", (event) => { ... })` 更新状态，驱动进度条渲染。
