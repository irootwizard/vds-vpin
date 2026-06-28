# model_training

该目录提供两套简单 CNN 训练实现，便于后续扩展到 MNIST / CIFAR-10：

- `train_pytorch.py`: PyTorch 版本，已支持 `mnist`、`cifar10`、`synthetic`
- `train_numpy.py`: 非 PyTorch 版本（NumPy 手写 CNN），支持 `synthetic` 和 `npz`
- `run.py`: 统一入口，根据 `--backend` 分发到对应实现

## 快速开始

### 1) PyTorch 版本

```bash
python model_training/run.py --backend pytorch --dataset mnist --epochs 1
python model_training/run.py --backend pytorch --dataset cifar10 --epochs 1
```

### 2) 非 PyTorch（NumPy）版本

```bash
python model_training/run.py --backend numpy --dataset synthetic --epochs 1 --batch-size 32 --lr 0.01
```

## 后续接入 MNIST / CIFAR-10 到 NumPy 版本

建议先将数据预处理为 `.npz`，包含以下键：

- `x_train`: `(N, C, H, W)`，float32
- `y_train`: `(N,)`，int
- `x_test`: `(M, C, H, W)`，float32
- `y_test`: `(M,)`，int

训练命令：

```bash
python model_training/run.py --backend numpy --dataset npz --data-path path/to/dataset.npz --epochs 3
```

## PyTorch 练习

新增练习目录：`model_training/exercises/`

- `ex1_tensor_device.py`：张量、设备、CPU/GPU 速度对比
- `ex2_min_train_loop.py`：最小训练循环（forward/loss/backward/step）
- `ex3_mnist_cnn.py`：MNIST 小型 CNN 训练

运行示例：

```bash
python model_training/exercises/ex1_tensor_device.py
python model_training/exercises/ex2_min_train_loop.py
python model_training/exercises/ex3_mnist_cnn.py
```

## Network A（AHE 对齐训练）

针对 vPIN Network A 拓扑（固定 conv + 可训 FC），与 `vpin_client` 预处理及 AHE 截断一致。

**数据集**：统一使用官方 Yann LeCun MNIST（torchvision idx，CVDF 镜像下载），缓存于 `model_training/data/mnist/`。训练与同态测试（`vpin-client ahe-infer` / `eval-mnist-ahe`）均走此数据源，**不使用** `src/cnn_networks` 或 `vpin-backend/data/mnist/*.npy`。

```powershell
# 训练（Float 预热 + 定点 QAT，目标 test acc ≥90%）
.\.venv\Scripts\python.exe -m model_training.network_a.train --device cuda

# 导出权重 → 注册 registry → 评估
$run = Get-ChildItem model_training\outputs | Sort-Object Name -Descending | Select-Object -First 1
.\.venv\Scripts\python.exe -m model_training.network_a.export_weights --run-dir $run.FullName
.\.venv\Scripts\python.exe -m model_training.network_a.register_backend --weights-dir $run.FullName
.\.venv\Scripts\python.exe -m model_training.network_a.evaluate --run-dir $run.FullName --mode all --model-id cnn-mnist-trained

# 或通过统一入口
.\.venv\Scripts\python.exe model_training/run.py --task network-a --device cuda
```

产物目录：`model_training/outputs/<timestamp>/`（含 `checkpoint.pt`、4 个 npy、`truncation_config.json`、`metrics.json`）。

---

## Network LeNet-CIFAR10（AHE 对齐，P2 验证轨）

CIFAR-10 LeNet 独立训练栈（`model_id: lenet-cifar10`，`network: lenet_cifar`），**禁止**使用 Network A 权重/拓扑。

**拓扑**：`Conv2d(3,6,5)` → ReLU → sum_pool 2×2 → `Conv2d(6,16,5)` → ReLU → sum_pool 2×2 → FC(400→120→84→10)

**截断相位**（§11.4，by formula，不手写 26）：

| π | 位置 | from_bits | 操作 |
|---|------|-----------|------|
| π1 | after_conv1 | 16 | relu |
| π2 | after_pool1 | **28** | shift |
| π3 | after_conv2 | 16 | relu |
| π4 | after_pool2 | **28** | shift |
| π5 | after_fc1 | **32** | relu_then_shift |
| π6 | after_fc2 | **32** | relu_then_shift |

```powershell
# 训练（Float 预热 + 定点 QAT，目标 CIFAR-10 test acc ≥60%）
.\.venv\Scripts\python.exe model_training\run.py --task network-lenet --dataset cifar10 --device cuda

# 或直接调用子模块
.\.venv\Scripts\python.exe -m model_training.network_lenet.train --dataset cifar10 --device cuda

# 导出 → 注册 → 验证 → 评估
$run = Get-ChildItem model_training\outputs | Sort-Object Name -Descending | Select-Object -First 1
.\.venv\Scripts\python.exe -m model_training.network_lenet.export_weights --run-dir $run.FullName
.\.venv\Scripts\python.exe -m model_training.network_lenet.register_backend --weights-dir $run.FullName
.\.venv\Scripts\python.exe -m model_training.network_lenet.verify --run-dir $run.FullName
.\.venv\Scripts\python.exe -m model_training.network_lenet.evaluate --run-dir $run.FullName --mode all

# 端到端 HDC 验收
.\.venv\Scripts\python.exe scripts\validate_cifar10_hdc.py --run-dir $run.FullName
```

测试（单元/冒烟）：

```powershell
.\.venv\Scripts\python.exe -m pytest model_training/tests/test_network_lenet.py -v
.\.venv\Scripts\python.exe -m model_training.network_lenet.verify     # smoke test（合成权重）
```

**验收状态（2026-06-22，run `20260622_174721`）**：

| 项目 | 状态 |
|------|------|
| 官方 MNIST + AHE parity + layerwise | 通过 |
| 定点 test acc ≥90% | **未达标**（约 10.5%） |
| 截断 bounds < 2³⁰ | **未达标**（FC₁ 前激活超限） |

- 持久化文档（跨会话查阅）：

- [docs/network-a/network-a-任务状态与接续.md](../docs/network-a/network-a-任务状态与接续.md) — plan 清单、命令、产物地图、接续步骤
- [docs/network-a/network-a-official-mnist-ahe-分析.md](../docs/network-a/network-a-official-mnist-ahe-分析.md) — 算法/实现分析
- [docs/network-a/network-a-批次截断算法设计.md](../docs/network-a/network-a-批次截断算法设计.md) — 批次静态预算、26/32 本征尺度、论文对齐
