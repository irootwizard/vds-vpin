# Network A 任务状态与接续手册

> **用途**：跨会话查阅 plan 完成情况、验收结果、标准命令与后续步骤。  
> **最后更新**：2026-06-22  
> **当前 run**：`model_training/outputs/20260622_174721/`  
> **Registry**：`cnn-mnist-trained` → 上述目录绝对路径

---

## 1. Plan 任务清单（对照 `network_a_mnist_训练` plan）

| ID | 内容 | 状态 | 备注 |
|----|------|------|------|
| na-preprocess-fp | 预处理 + 定点 + truncation_config | ✅ | `vpin_client/data/official_mnist.py`、`network_a/fixed_point.py`、`truncation_config.py` |
| na-model-dataset | model.py + dataset.py（官方 MNIST） | ✅ | 不读 legacy npy |
| na-train-gpu | GPU Float 预热 + 定点 QAT | ⚠️ | Float **91.94%**；定点 **10.47%**（目标 ≥90% 未达） |
| na-export-register | 导出 npy + registry | ✅ | 4×npy、`truncation_config.json` 已写入 |
| na-evaluate-ahe | fixed / layerwise / bounds / AHE | ⚠️ | layerwise + AHE parity ✅；fixed + bounds ❌ |
| na-docs-run | README + run.py | ✅ | 见 `model_training/README.md` |
| na-truncation-sync | 校准 shift 同步 topology | ✅ | 当前 `shift_pool=24`, `shift_fc1=30`（`topology.py` 已对齐） |

---

## 2. 验收标准 vs 实测（`evaluation_report.json`）

| 指标 | 门槛 | 实测 | 通过 |
|------|------|------|------|
| 明文定点 test acc | ≥ 90% | **10.47%** | ❌ |
| AHE vs 明文定点 | 差 ≤ 0.1% | gap=0，mismatches=0（5 样本） | ✅ |
| layerwise max diff | 0 | 全层 0 | ✅ |
| 截断边界 | 各层 max\|x\| < 2³⁰ | `after_fc1_pre_relu` ≈ **2.15×10⁹** > 2³⁰ | ❌ |
| registry + backend | ModelSelectAck + ahe-infer | 已注册，WS 推理正常 | ✅ |

**解读**：

- **同态实现正确**（layerwise=0、AHE logits 一致），与分类精度脱钩。
- **定点精度低**是 Network A 拓扑 + 官方 MNIST 下的训练/算法问题，非 AHE 引擎 bug。详见 [network-a-official-mnist-ahe-分析.md](./network-a-official-mnist-ahe-分析.md)。
- **bounds 未过**说明部分测试图在 FC₁ 前激活超过 AHE 安全上限；parity 样本仍一致，但全量部署前需重训或加大 shift。

---

## 3. 标准命令（均在仓库根目录，Python 用 `.venv`）

### 3.1 自检

```powershell
.\.venv\Scripts\python.exe -m model_training.network_a.verify
```

### 3.2 训练 → 导出 → 注册

```powershell
.\.venv\Scripts\python.exe -m model_training.network_a.train --device cuda
$run = "model_training\outputs\20260622_174721"   # 或最新 timestamp 目录
.\.venv\Scripts\python.exe -m model_training.network_a.export_weights --run-dir $run
.\.venv\Scripts\python.exe -m model_training.network_a.register_backend --weights-dir $run
```

### 3.3 评估（需后端时先启动 §3.4）

```powershell
.\.venv\Scripts\python.exe -m model_training.network_a.evaluate --run-dir $run --mode all --model-id cnn-mnist-trained --ahe-limit 50
```

`--mode` 可选：`fixed` | `bounds` | `layerwise` | `ahe` | `all`。报告写入 `<run>/evaluation_report.json`。

### 3.4 后端 + 单样本 AHE

```powershell
# 终端 1
cd vpin-backend
..\.venv\Scripts\python.exe -m vpin_backend.main

# 终端 2 — CLI
cd vpin-client
..\.venv\Scripts\python.exe -m vpin_client.cli ahe-infer --model cnn-mnist-trained --mnist-index 0 --timing

# 或 E2E 验收（明文定点 vs AHE logits 逐元素一致）
..\.venv\Scripts\python.exe scripts\ahe_e2e_smoke.py --model cnn-mnist-trained --mnist-index 0
```

**AHE 打通状态（2026-06-22 实测）**：

| 模型 | smoke | layerwise | 说明 |
|------|-------|-----------|------|
| `cnn-mnist-trained` | PASS | max_diff=0 | registry 权重，官方 MNIST |
| `cnn-mnist` | PASS | — | legacy `Pre_trained_model` |

**注意**：后端入口为 `python -m vpin_backend.main`，不要用裸 uvicorn。单次推理约 40–50s（CPU 椭圆曲线运算）。

### 3.5 校准 shift 与 topology 同步

若新 run 的 `truncation_config.json` 中 shift 与 `vpin-backend/.../topology.py` 不一致：

```powershell
.\.venv\Scripts\python.exe -m model_training.network_a.sync_topology --run-dir $run
```

---

## 4. 产物与代码地图

### 4.1 当前 run 产物

```
model_training/outputs/20260622_174721/
├── checkpoint.pt / checkpoint_float.pt   # QAT 未达标，均为 float 权重
├── truncation_config.json                # shift_pool=24, shift_fc1=30
├── metrics.json
├── weight_fc1_64_16.npy, bias_fc1_16.npy
├── weight_fc2_16_10.npy, bias_fc2_10.npy
└── evaluation_report.json
```

### 4.2 关键源码

| 路径 | 作用 |
|------|------|
| `vpin-client/vpin_client/data/official_mnist.py` | 官方 MNIST 唯一下载源（CVDF 镜像） |
| `model_training/network_a/model.py` | Float / 定点 / QAT 前向 |
| `model_training/network_a/train.py` | 两阶段训练 + float 备份恢复 |
| `model_training/network_a/evaluate.py` | 四类验收 |
| `vpin-backend/vpin_backend/api/routes/session.py` | PublicKey 时加载 registry 权重 |
| `vpin-backend/vpin_backend/inference/homomorphic_network_a.py` | AHE 明文对照路径 |

### 4.3 数据约束

- ✅ 使用：`model_training/data/mnist/`（torchvision 官方 idx）
- ❌ 不用：`src/cnn_networks/`、`vpin-backend/data/mnist/*.npy`、legacy `Pre_trained_model` 图像

---

## 5. 已知问题与已修复项

### 5.1 未解决（需算法/训练迭代）

1. **定点 test acc ≈10%**（float ≈92%）：固定 conv + 双次 shift + int16 FC + 每图 min-max，float 权重无法直接用于定点链。
2. **bounds 超限**：`after_fc1_pre_relu` 在 500 张抽样上 max ≈ 2.15×10⁹。
3. Legacy `Pre_trained_model` 在**同一官方 MNIST + 定点路径**上也仅 ~12%，说明问题在拓扑而非数据文件。

### 5.2 本会话已修复

| 问题 | 处理 |
|------|------|
| `calibrate_shifts` 误将 from_bits 降到 24/30 | 固定本征尺度 **26/32**（论文/legacy）；批次扫描仅做安全验证 |
| bounds 用 2³⁰ 判 shift 前激活 | 分层：BSGS 解密上限 + int32 重加密上限 |
| topology.py 曾为 24/30 | 已恢复 **26/32**；需重启后端 |
| `evaluate --mode all` bounds 崩溃 | 已改为写入 report |
| 其他历史修复 | 见 [分析文档 §2](./network-a-official-mnist-ahe-分析.md#2-实现层面已修复的关键问题) |

---

## 6. 后续接续步骤（优先级）

1. **定点域训练**：更长 QAT、蒸馏（float teacher → fixed student）、shift 搜索；见分析文档 §1.3。
2. **bounds 达标**：训练时约束激活或增大 `shift_fc1`（需重新校准 + `sync_topology`）。
3. **AHE 抽样扩大**：`--ahe-limit 200`（全量 10k 极慢，~40s/张）。
4. **文档**：`docs/ahe-e2e-实现说明.md` 仍提及 legacy `prepare_mnist_network_a.py`，与官方 MNIST 策略不一致，宜标注 deprecated。

---

## 7. 相关文档

| 文档 | 内容 |
|------|------|
| [network-a-批次截断算法设计.md](./network-a-批次截断算法设计.md) | **批次静态预算**、26/32 本征尺度、论文 TReLU 对齐 |
| [network-a-official-mnist-ahe-分析.md](./network-a-official-mnist-ahe-分析.md) | 算法/实现深度分析、parity 样例 |
| [model_training/README.md](../model_training/README.md) | Network A 快速命令 |
| Plan（勿编辑） | `.cursor/plans/network_a_mnist_训练_d5e787de.plan.md` |

---

## 8. 快速判断「卡在哪」

```
verify 失败        → 环境/导入/数据下载
layerwise ≠ 0      → 定点实现与 homomorphic 明文不一致（实现 bug）
AHE mismatches > 0 → 后端权重/拓扑/session 加载问题
fixed acc 低但 layerwise=0 → 权重未在定点域优化（算法/训练）
bounds 失败        → shift 过小或权重幅度过大，有溢出风险
```
