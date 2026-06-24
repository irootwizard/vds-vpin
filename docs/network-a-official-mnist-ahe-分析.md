# Network A 官方 MNIST 训练与 AHE 同态推理分析

## 验收结论（2026-06-22）

| 项目 | 结果 | 说明 |
|------|------|------|
| 数据源 | 通过 | 官方 Yann LeCun MNIST（`model_training/data/mnist`，CVDF 镜像） |
| 与 `src/cnn_networks` 隔离 | 通过 | 训练/测试/CLI 均不读取 legacy npy 或 `Pre_trained_model` 图像 |
| 明文定点 layerwise | 通过 | `max_diff = 0`（Torch 路径 vs homomorphic 明文路径） |
| AHE WS 推理 | 通过 | 单样本 logits 与明文定点逐元素一致 |
| AHE parity（5 样本） | 通过 | `pred_mismatches=0`，`acc_gap=0` |
| 定点 test acc ≥90% | **未达标** | 当前约 **10.5%**（接近随机猜测） |
| 截断 bounds < 2³⁰ | **未达标** | `after_fc1_pre_relu` max ≈ 2.15×10⁹（见 `evaluation_report.json`） |

**跑通命令摘要：**

```powershell
# 训练产物
model_training\outputs\20260622_174721\

# 后端
cd vpin-backend
..\.venv\Scripts\python.exe -m vpin_backend.main

# 单样本 AHE（官方 MNIST index 0）
cd vpin-client
..\.venv\Scripts\python.exe -m vpin_client.cli ahe-infer --model cnn-mnist-trained --mnist-index 0 --timing

# 评估
..\.venv\Scripts\python.exe -m model_training.network_a.evaluate --run-dir model_training\outputs\20260622_174721 --mode all --model-id cnn-mnist-trained
```

**parity 样例（MNIST test index 0，label=7）：**

- 明文定点 `prediction=0`，logits 前 5 维：`[26903.75, 0, 0, 0, 9209.60]`
- AHE 推理 `prediction=0`，logits **完全相同**
- 分类错误来自模型表达能力，**不是**同态实现偏差

---

## 1. 算法层面：为何 Float 92% 但定点仅 10%？

Network A 不是普通 CNN，而是为 AHE 设计的**强约束定点流水线**：

```
uint8 → pad/min-max → int32 输入
→ 固定 conv [[1,0,1],[2,0,2],[1,0,1]]
→ ReLU（客户端）
→ sum-pool 4×4 × (1/16)₁₀bit
→ shift（pool，如 24→16 bit）
→ FC₁（权重 int16 量化）→ ReLU + shift（fc1，如 30→16 bit）
→ FC₂ → ReLU
```

### 1.1 信息瓶颈

1. **固定卷积核**不可训练，特征完全由预处理 + 池化决定。
2. **每图 min-max 归一化**（32×32 含 padding）使不同样本特征尺度差异大，官方 MNIST 与旧版 `image_mnist_32_32.npy` 分布不同。
3. **两次大 shift**（pool、fc1）将中间激活从 24/30 bit 压到 16 bit，等价于多次除以 2ⁿ，**大量低位信息被截断**。
4. **FC 权重**以 `real_to_fixed_point`（截断，非四舍五入）量化到 int32，与 float 训练最优解不对齐。

因此：**在 float 域训练的 FC 权重，几乎不能直接在定点链路上复用**。实验观测：

- Float test acc ≈ **92%**（`20260622_174721`）
- 同一 checkpoint 的 `forward_fixed_point` ≈ **10.5%**
- Legacy `Pre_trained_model` 权重在**同一官方 MNIST + 同一定点路径**上仅 ≈ **12%**（说明旧权重也从未针对官方数据 + 全链路定点优化）

### 1.2 截断校准

校准根据激活幅度建议 `shift_pool=24`、`shift_fc1=30`（默认 26/32）。shift 越小保留越多信息，但增大 int32 溢出风险；当前校准结果已写入 `truncation_config.json`，topology 仍为 24/30（与后端 WS 协议一致）。

### 1.3 QAT 为何暂未拉高定点精度

已对齐 `forward_fixed_point_train` 与 `_run_fixed_point`（含 CPU 整数 conv、int64 FC 前向 + STE 反传），但：

- 从随机或 float 初始化做定点 QAT，loss 在极大 logits 尺度上仍难优化；
- 30 epoch 纯定点训练 test acc 仍 ≈10%；
- **同态 parity 与分类精度是正交目标**：parity 要求实现与明文一致；精度要求权重适应截断噪声。

**后续算法方向（未实现）：**

- 更长定点 QAT + 学习率调度 / 温度缩放 logits；
- 知识蒸馏：float teacher → fixed student；
- 放宽 shift 搜索或 per-layer 校准；
- 在固定 conv 下引入可训 scale（需改 AHE 协议，超出当前 Network A）。

---

## 2. 实现层面：已修复的关键问题

### 2.1 数据源统一

- 新增 `vpin_client/data/official_mnist.py` 为**唯一下载源**；
- `load_mnist_test()`、`build_mnist_loaders()`、`evaluate.py`、CLI 全部走官方 MNIST；
- 路径：`model_training/data/mnist/`（与 `src/cnn_networks` 无关）。

### 2.2 定点路径对齐（parity）

| 问题 | 修复 |
|------|------|
| CUDA `avg_pool2d` 不支持 int | pool 前转 float；整数语义的 sum-pool |
| CUDA float conv 与 CPU int conv 不一致 | `_conv_fixed_int` 在 CPU 上 round |
| `shift` 用 round 而非 truncate | 与 `astype(int32)` 一致，改为截断 |
| FC float matmul 溢出/精度丢失 | int64 累加；QAT 用 int 前向 + STE |
| `_fc_ste` 训练时前向误用 float 路径 | 改为 `out + (out_ste - out_ste.detach())` |
| `session.py` 未加载 registry 权重 | `PublicKey` 时 `load_network_a_weights(weights_dir)` |
| `wdir` 拼写错误 | 改为 `weights_dir` |

验证：`python -m model_training.network_a.verify` 与 `evaluate --mode layerwise` 均为 `max_diff=0`。

### 2.3 训练流程

- 保存 `checkpoint_float.pt`，QAT 未达标时恢复 float 权重；
- 仅当 QAT 明显优于随机时才覆盖 `checkpoint.pt`；
- 记录 `float_fixed_acc` 便于诊断 float/定点鸿沟。

---

## 3. 产物说明

```
model_training/outputs/20260622_174721/
├── checkpoint.pt          # float 权重（QAT 未达标，已恢复 float）
├── checkpoint_float.pt    # 同上备份
├── truncation_config.json # shift_pool=24, shift_fc1=30
├── metrics.json
├── weight_fc1_64_16.npy   # 已导出
├── bias_fc1_16.npy
├── weight_fc2_16_10.npy
├── bias_fc2_10.npy
└── evaluation_report.json
```

Registry：`cnn-mnist-trained` → 上述目录绝对路径。

---

## 4. 结论

1. **AHE 同态推理在官方 MNIST 上已跑通**：WS 全流程、logits 与明文定点一致、layerwise 中间张量 diff=0。
2. **分类精度未达 90%** 是 Network A 定点拓扑 + 官方 MNIST 预处理下的**训练/算法问题**，不是同态引擎实现错误。
3. 若业务需要 ≥90% 且 AHE parity，需在定点域重新设计训练策略（见 §1.3），或接受较低精度仅验证密码学闭环。

---

## 5. 参考文件

- **接续手册**：[network-a-任务状态与接续.md](./network-a-任务状态与接续.md)

- 数据：`vpin-client/vpin_client/data/official_mnist.py`
- 模型：`model_training/network_a/model.py`（`_run_fixed_point` / `forward_fixed_point_train`）
- 训练：`model_training/network_a/train.py`
- 评估：`model_training/network_a/evaluate.py`
- 后端 WS：`vpin-backend/vpin_backend/api/routes/session.py`
