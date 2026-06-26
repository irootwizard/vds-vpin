# Network A 批次截断算法设计

> **状态**：设计定稿 + `truncation_config.py` 初版实现（2026-06-22）  
> **依据**：vPIN 论文 TReLU/客户端 shifting、`vPIN论文与代码对照说明.md` §二、`docs/task3-模型接入解析与存储方案.md` §6

---

## 1. 问题定义

### 1.1 「批次截断」在本仓库中的含义

文档与 plan 中**没有**「对整个 batch 做一次全局 min-max」的 batch truncation；AHE 明确要求**每张图独立**预处理与同态会话。

此处 **批次截断** 指：

1. **离线批次校准**：在官方 MNIST 训练/校准集上扫描 **N 张图**（如 200），统计各截断检查点的激活幅度；
2. **静态位宽预算**：用批次统计推导每层 `shifting(bits)` 是否安全、是否需在训练中约束权重；
3. **禁止**把多张图的 min-max 合并为一个全局 scale（会破坏 per-image 语义）。

### 1.2 论文算法（TReLU / shifting）

客户端在固定检查点执行（`Client.py` 与 `activation.py` 一致）：

```
real = fixed / 2^from_bits
new_fixed = truncate_to_int32(real * 2^16)
```

`from_bits` 是当前张量的**定点小数位数 f**，不是「想删几位」的任意旋钮。

Network A 自然尺度（由算子传播推导）：

| 检查点 | 算子 | 自然 from_bits |
|--------|------|----------------|
| after_pool | sum-pool 4×4 + ×(1/16)₁₀bit | **26** (=16+4+10) |
| after_fc1 | FC₁（输入 f=16，权重 f=16） | **32** (=16+16) |

Legacy 硬编码：`shifting(..., 26)`、`shifting(relu(...), 32)` — 与上表一致。

---

## 2. 已发现并修复的实现问题

### 2.1 错误校准（根因级）

旧版 `calibrate_shifts()` 把 `shift_bits` 当作 `ceil(log2(max))-16+1` 并 clamp 到 24–28 / 30–36，**降低了 from_bits**（如 24/30）。

这会 **错误缩放实数值**（例如把 f=26 的数据按 f=24 解码 → 放大 4×），与论文/legacy 不一致；AHE 各路径内部仍自洽（parity=0），但**分类精度受损**。

**修复**：`batch_calibrate_shifts()` 固定返回 **26/32**；批次扫描仅用于 **安全验证** 与训练诊断，不再修改 from_bits。

### 2.2 bounds 检查误用

旧版对 `after_fc1_pre_relu` 用 `2^30` 判定失败，但该值是 **shift 前** 的解密幅度；BSGS 可解上限约 `(3.2×10⁶)² ≈ 10¹³`。

**修复**：`validate_activation_stats()` 分层检查：

- **shift 前**：对比 `BSGS_ABS_SAFE_LIMIT`
- **shift 后**（重加密前）：对比 `INT32_ABS_SAFE_LIMIT`

---

## 3. 批次静态预算算法

### 3.1 输入

- 官方 MNIST 校准集 loader（默认 200 张，**逐图** min-max）
- Float 预热后的 `NetworkA` 权重
- 固定 `TruncationPlan(shift_pool=26, shift_fc1=32)`

### 3.2 扫描（`train.py::_calibrate_plan`）

对每张图记录：

```
max_after_pool_pre_shift
max_after_fc1_pre_relu
max_after_fc2_pre_relu
```

取批次 **max**（可扩展为 p99.9 分位数以兼顾精度与安全余量 δ）。

### 3.3 输出

```python
plan = batch_calibrate_shifts(...)  # shift 恒为 26/32
ok, errors = validate_activation_stats(plan.calibration, plan)
```

写入 `truncation_config.json`：

- `shift_pool` / `shift_fc1`：恒 26/32
- `calibration`：批次统计 + `max_post_*_shift`

### 3.4 判定公式（与对照说明 §二一致）

**shift 后重加密幅度**：

$$
M_{\mathrm{post}} = \frac{M_{\mathrm{pre}}}{2^{\mathrm{from\_bits}-16}}
$$

若 $M_{\mathrm{post}} \ge 2^{31}-1$ → 需在训练中 **缩小 FC 权重幅度** 或引入额外截断策略（当前协议无动态 `from_bits`）。

**解密安全**：$M_{\mathrm{pre}} < (m_{\mathrm{BSGS}})^2$。

### 3.5 精度优化方向（未实现）

| 策略 | 说明 |
|------|------|
| 分位数校准 | 用 p99.9 代替 max，减少离群图对诊断的误导 |
| 定点 QAT @ 26/32 | 在正确 from_bits 下重训 |
| 权重幅度正则 | 训练时惩罚使 $M_{\mathrm{post}}$ 贴近 int32 上限 |
| 动态 TruncateRequest | 平台架构 §4.3；需改 WS 协议，超出当前 Network A |

---

## 4. 与其他模型的关系

| 模型 | AHE 后端 | 训练栈 | 建议 |
|------|----------|--------|------|
| Network A | ✅ | ✅ | **当前唯一可 E2E 路线** |
| Network B–E | ❌ | ❌ | 需先 port `homomorphic_network_*.py` + `topology.py` |
| LeNet-5 | ❌ | ❌ | 多轮截断（26/33…），工程量大 |

在 Network A 定点精度未达标前，**不建议**并行开训 B/LeNet。

---

## 5. 验收命令

```powershell
.\.venv\Scripts\python.exe -m model_training.network_a.verify
.\.venv\Scripts\python.exe scripts\ahe_e2e_smoke.py --model cnn-mnist-trained --mnist-index 0

# 重启后端使 topology.py 26/32 生效后：
cd vpin-backend; ..\.venv\Scripts\python.exe -m vpin_backend.main
```

重训（官方 MNIST，正确截断）：

```powershell
.\.venv\Scripts\python.exe -m model_training.network_a.train --device cuda
```

---

## 6. 参考

- `model_training/network_a/truncation_config.py` — `batch_calibrate_shifts`, `validate_activation_stats`
- `src/cnn_networks/Client.py` L316–322 — legacy 26/32
- `vpin-client/vpin_client/crypto/ahe/activation.py` — `shifting`
- `vpin-backend/vpin_backend/crypto/ahe/topology.py` — WS 截断计划
