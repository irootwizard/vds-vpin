# Network A · 官方 MNIST 自训练 · AHE 同态推理运行报告

> **报告日期**：2026-06-23  
> **结论**：**AHE 同态推理路线已端到端跑通**（训练 → 导出 → 注册 → WS 密态推理 → logits 与明文定点一致）。  
> **范围**：纯 AHE（P0–P3 WebSocket 会话），**不含** CP-SNARK 证明链。

---

## 1. 执行摘要

| 维度 | 状态 | 说明 |
|------|------|------|
| 自训练 Network A | ✅ | 官方 MNIST 上完成 float 训练并导出 npy 权重包 |
| 模型注册 `cnn-mnist-trained` | ✅ | 后端启动时自动挂载最新 `model_training/outputs/*` |
| 明文定点 / 同态明文路径 | ✅ | layerwise `max_diff = 0` |
| AHE WebSocket 全流程 | ✅ | SessionStart → … → InferenceComplete → SessionEnd |
| AHE vs 定点 parity | ✅ | `logit_max_diff = 0`，预测类一致 |
| 自动化测试 | ✅ | client 5 项 + backend 2 项 + `ahe_e2e_smoke.py` PASS |
| 定点分类精度 ≥90% | ⚠️ | 训练 metrics 显示 float/fixed 鸿沟；密码学闭环与分类精度为**正交目标** |
| `deployable=true`（HDC 门禁） | ⚠️ | `ahe_feasibility_report.json` 中 `deployable: false`（精度容差未过） |

**一句话**：密码学意义上的 AHE 推理链路已验证可用；若需业务侧 ≥90% 准确率，需在定点域继续优化训练（见 [network-a-official-mnist-ahe-分析.md](network-a-official-mnist-ahe-分析.md)）。

---

## 2. 模型与训练产物

### 2.1 当前注册模型

| 字段 | 值 |
|------|-----|
| 模型 ID | `cnn-mnist-trained` |
| 网络族 | **Network A**（`network: "A"`） |
| 权重目录 | `model_training/outputs/20260622_184254/` |
| 可训练参数 | **1,210**（FC 64→16→10；卷积核固定） |
| 输入 | 官方 MNIST `1×28×28` uint8 → 定点 `int32` |
| Float 测试精度 | **92.93%**（`metrics.json`） |
| 注册时间 | 2026-06-22（`registry_snippet.json`） |

### 2.2 目录结构

```
model_training/outputs/20260622_184254/
├── checkpoint.pt / checkpoint_float.pt
├── truncation_config.json      # shift_pool=26, shift_fc1=32
├── metrics.json
├── registry_snippet.json       # → cnn-mnist-trained
├── ahe_feasibility_report.json
├── weight_fc1_64_16.npy
├── bias_fc1_16.npy
├── weight_fc2_16_10.npy
└── bias_fc2_10.npy
```

### 2.3 Network A 拓扑（AHE 对齐）

```
uint8 MNIST 28×28
  → pad / min-max 归一化 → int32 固定点输入
  → 固定 3×3 conv [[1,0,1],[2,0,2],[1,0,1]]  （客户端 ReLU）
  → 4×4 sum-pool × (1/16)₁₀bit
  → shift（pool，26→16 bit）
  → FC₁ 64→16 → ReLU + shift（32→16 bit）
  → FC₂ 16→10 → ReLU
  → logits（客户端本地结束）
```

卷积核**不在 npy 包内**，由服务端 `homomorphic_network_a.py` 内置。

---

## 3. 数据与预处理

| 项 | 路径 / 说明 |
|----|-------------|
| 数据源 | 官方 Yann LeCun MNIST（CVDF 镜像） |
| 缓存 | `model_training/data/mnist/MNIST/raw/*.idx*-ubyte` |
| 加载 | `vpin_client/data/official_mnist.py`（直读 IDX，无 torchvision 热路径依赖） |
| 隔离 | **不**使用 `src/cnn_networks/Pre_trained_model` 或 legacy npy 图像 |

---

## 4. AHE 端到端链路（已跑通）

### 4.1 软件分层

```
[Tauri / CLI 客户端]  vpin_client.pipeline / ws_ahe_client
        │  WebSocket P0–P3
        ▼
[vpin-backend]  session.py → ahe_engine.py → homomorphic_network_a.py
        │
        ▼
[密码学]  EC 加法同态（指数 ElGamal 型）+ BSGS 标量乘表
```

### 4.2 协议阶段（P0–P3）

| 步骤 | 消息 | 执行方 |
|------|------|--------|
| 0 | `SessionStart` / `SessionAccept` | 双方 |
| 1 | `ModelSelect` / `ModelSelectAck` | 权重摘要 + 截断计划 |
| 2 | `InputDigest` / `InputDigestAck` | 输入 SHA256 |
| 3 | `PublicKey` + 初始 `CiphertextPayload` | 客户端加密上传 |
| 4 | 四轮截断环 | 服务端同态线性层 → 客户端 ReLU/shift/重加密 |
| 5 | `InferenceComplete` / `SessionEnd` | 客户端得 logits |

截断计划（WS 热路径，`topology.py`）：

| phase_id | client_action | shift_bits |
|----------|---------------|------------|
| after_conv | relu | — |
| after_pool | shift | **24**（topology 默认；权重目录 json 为 26，以 topology 为准） |
| after_fc1 | relu_then_shift | **30**（同上） |
| after_fc2 | relu_only | — |

### 4.3 同态运算量（单图）

| 指标 | 数值 |
|------|------|
| `num_pt_mult` | **18,560** |
| `num_pt_add` | **18,330** |

---

## 5. 验收结果

### 5.1 密码学 / 实现验收（AHE 跑通判定依据）

| 检查项 | 结果 | 证据 |
|--------|------|------|
| 明文定点 layerwise | ✅ `max_diff=0` | `evaluate --mode layerwise` |
| AHE logits 数值一致 | ✅ `logit_max_diff=0` | `scripts/ahe_e2e_smoke.py` |
| 预测类一致 | ✅ | smoke + parity |
| WS 握手与会话 | ✅ | `test_ws_session.py` |
| Pipeline 编排 | ✅ | `test_pipeline.py` |

### 5.2 2026-06-23 实测（本机复验）

**环境**：Windows 10；Intel i5-13500H；15.7 GB RAM；Python `.venv`。

**后端**：

```powershell
cd vpin-backend
..\.venv\Scripts\python.exe -m vpin_backend.main
```

**E2E Smoke（`scripts/ahe_e2e_smoke.py`）**：

```json
{
  "model_id": "cnn-mnist-trained",
  "mnist_index": 0,
  "label": 7,
  "plain_prediction": 7,
  "ahe_prediction": 7,
  "prediction_match": true,
  "logit_max_diff": 0.0,
  "num_pt_add": 18330,
  "num_pt_mult": 18560,
  "timing_ms": 153646.75,
  "weights_dir": ".../model_training/outputs/20260622_184254",
  "pass": true
}
```

| 字段 | 解读 |
|------|------|
| `pass: true` | AHE WS 输出与 homomorphic 明文路径**逐元素一致** |
| `label=7` / `prediction=7` | 该样本分类正确（实现正确性的样例，非全量精度承诺） |
| `timing_ms ≈ 154 s` | 纯密态推理 wall-clock（含 WS 序列化；不含 SNARK） |

**单元 / 集成测试**：

| 套件 | 结果 |
|------|------|
| `vpin-client/tests/test_ahe.py` + `test_pipeline.py` | **5 passed** |
| `vpin-backend/tests/test_ahe_demo.py` + `test_ws_session.py` | **2 passed** |

### 5.3 历史验收（2026-06-22）

较早 run `20260622_174721` 上曾记录：

- AHE parity（5 样本）：`pred_mismatches=0`，`acc_gap=0`
- 单样本 index 0：明文定点与 AHE logits **完全相同**（当时 `prediction=0`，label=7，属模型精度问题而非同态偏差）

详见 [network-a-official-mnist-ahe-分析.md](network-a-official-mnist-ahe-分析.md)。

### 5.4 未纳入「AHE 跑通」的指标（单独跟踪）

| 指标 | 当前状态 | 说明 |
|------|----------|------|
| 定点 test acc ≥90% | 未达标 | `metrics.json` 中 QAT fixed ≈10%；与 float 92% 存在鸿沟 |
| `ahe_feasibility` deployable | `false` | 精度容差 `acc_gap` 未过；**不影响** parity=0 的结论 |
| `crypto_infer_ms < 4 s` | 未达标 | 计划目标；当前 Python EC 路径 ~91–154 s |
| CP-SNARK 证明 | 未在本报告范围 | 见 `cp-snark/M5-performance-report.md` |

---

## 6. 性能摘要

| 指标 | 数值 | 备注 |
|------|------|------|
| `crypto_infer_ms` | **~91–154 s** | 视负载与后端状态；瓶颈：EC 标量乘、BSGS、pickle 分块 WS |
| `preprocess_ms` | **~2 ms** | 官方 MNIST IDX 直读（优化后） |
| 运算量 | 18.5k pt-mult + 18.3k pt-add | 与论文 Network A 量级一致 |

业界纯 FHE 对照见 [mnist-同态推理方案调研.md](../ahe/mnist-同态推理方案调研.md)（本路线为 **EC 加法同态**，不可与 CKKS 秒数直接横比）。

---

## 7. 复现命令（验收清单）

```powershell
# 0. 环境（仓库根目录）
.\.venv\Scripts\python.exe -m pip install -e vpin-client
.\.venv\Scripts\pip.exe install -r vpin-backend\requirements.txt

# 1. 训练（若需重新产出权重）
.\.venv\Scripts\python.exe -m model_training.network_a.train
.\.venv\Scripts\python.exe -m model_training.network_a.export_weights --run-dir model_training\outputs\<run_id>
.\.venv\Scripts\python.exe -m model_training.network_a.register_backend --run-dir model_training\outputs\<run_id>

# 2. 启动后端
cd vpin-backend
..\.venv\Scripts\python.exe -m vpin_backend.main

# 3. 单图 AHE + 计时
cd ..\vpin-client
..\.venv\Scripts\python.exe -m vpin_client.cli ahe-infer --model cnn-mnist-trained --mnist-index 0 --timing

# 4. E2E smoke（必须通过）
cd ..
.\.venv\Scripts\python.exe scripts\ahe_e2e_smoke.py --model cnn-mnist-trained --mnist-index 0

# 5. 全量评估（layerwise + AHE parity，需后端）
.\.venv\Scripts\python.exe -m model_training.network_a.evaluate `
  --run-dir model_training\outputs\20260622_184254 `
  --mode all --model-id cnn-mnist-trained

# 6. 自动化测试
cd vpin-client && ..\.venv\Scripts\python.exe -m pytest tests\test_ahe.py tests\test_pipeline.py -q
cd ..\vpin-backend && ..\.venv\Scripts\python.exe -m pytest tests\test_ahe_demo.py tests\test_ws_session.py -q
```

**Tauri 桌面端**：启动 `npm run tauri dev` 后访问 `/demo/ahe`（需本地后端已运行）。

---

## 8. 结论

1. **自训练 Network A（`cnn-mnist-trained`）在官方 MNIST 上已完成训练、权重导出与后端注册。**
2. **AHE 同态推理全链路已跑通**：客户端加密 → 服务端 `homomorphic_network_a` 密态线性运算 → 四轮截断回传 → 客户端 logits；与明文定点路径 **bit 级一致**（`logit_max_diff=0`）。
3. **自动化测试与 smoke 脚本均通过**，可作为回归门禁。
4. **分类精度与部署门禁（`deployable`）仍为后续训练/校准工作**，与「AHE 实现是否正确」无关。

---

## 9. 相关文档

| 文档 | 内容 |
|------|------|
| [ahe-e2e-实现说明.md](../ahe/ahe-e2e-实现说明.md) | P0–P3 协议与 CLI |
| [network-a-official-mnist-ahe-分析.md](network-a-official-mnist-ahe-分析.md) | float vs 定点精度分析 |
| [network-a-任务状态与接续.md](network-a-任务状态与接续.md) | 任务看板与接续命令 |
| [综合未来工作路线图.md](../roadmap/综合未来工作路线图.md) | **唯一总路线图** §0 完成度、§16 近期工作包 |
| [ahe-数据与模型预处理流程.md](../ahe/ahe-数据与模型预处理流程.md) | 预处理与权重格式 |
| [mnist-同态推理方案调研.md](../ahe/mnist-同态推理方案调研.md) | 业界对比 |

---

## 10. 与计算量证明的衔接（2026-06-24）

本报告验收范围**仅含 AHE 同态推理**（P0–P3）。计算量证明（CP-SNARK）为**独立管线**，尚未接入 WS 会话。

| 项 | AHE 本报告 | CP-SNARK / 证明 |
|----|------------|-----------------|
| 会话入口 | `session.py` | `cp-snark-full` CLI / `CpSnarkBridge` |
| 当前状态 | ✅ E2E 跑通 | ⚠️ EC gadget + 链外标量验 |
| `proof_coverage` | 不适用 | `ec_gadget_only` → 目标 `layer_proofs` |
| 下一步 | 定点精度（工作包 E） | P0 trace 重导 → M1 → M-B′ + M5 |

**优先动作**（证明线，不阻塞 AHE parity）：

```powershell
.\.venv\Scripts\python.exe -m model_training.network_a.export_proof_artifacts `
  --run-dir model_training\outputs\20260622_184254 --mirror-cp-snark
```

详见 [`综合未来工作路线图.md`](../roadmap/综合未来工作路线图.md) §0、§16.1。
