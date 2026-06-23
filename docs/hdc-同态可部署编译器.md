# HDC 同态可部署编译器

同态可部署编译器（Homomorphic Deployability Compiler, HDC）将训练权重、LayerGraph 尺度公式与校准集实测合并为 `homomorphic_deploy_plan.json`，供后端 session 与编排门控使用。

## 模型分工（§12）

| 模型 | `model_id` | 数据集 | 训练目录 |
|------|------------|--------|----------|
| Network A | `cnn-mnist-trained` | MNIST | `model_training/network_a/` |
| LeNet-CIFAR | `lenet-cifar10` | CIFAR-10 | `model_training/network_lenet/` |

硬约束：MNIST → Network A/B；CIFAR-10 → `lenet_cifar`；禁止 Network A 处理 CIFAR。

## LeNet-CIFAR 尺度（§11.4）

- 2×2 sum pool：`f_pool = 16 + log2(4) + 10 = 28`
- FC：`f_fc = 32`；client shift 回 `F=16`
- 截断相位 Π：π1–π6（conv ReLU、pool shift、fc relu+shift）

## 标准流水线

```powershell
.\.venv\Scripts\python.exe model_training\run.py --task network-lenet --dataset cifar10 --device cuda
.\.venv\Scripts\python.exe -m model_training.network_lenet.export_weights --run-dir model_training\outputs\<id>
.\.venv\Scripts\python.exe -m model_training.network_lenet.verify --run-dir model_training\outputs\<id>
.\.venv\Scripts\python.exe -m model_training.network_lenet.register_backend --weights-dir model_training\outputs\<id>
.\.venv\Scripts\python.exe scripts\validate_cifar10_hdc.py --run-dir model_training\outputs\<id>
```

## 公式 vs 实测（§13）

`verify` 产出 `hdc_validation_report.json`：`pi_match`、`checkpoints`（M_pre/M_post、BSGS/int32）、`deployable`。

## 模块映射

| 职责 | 路径 |
|------|------|
| LayerGraph / 尺度 | `vpin-client/vpin_client/hdc/layer_ir.py`, `scale_rules.py` |
| 校准 Compile | `compile_deploy_plan.py`, `range_propagate.py` |
| CIFAR adapter | `hdc/data_adapters/cifar10_rgb.py` |
| 训练栈 | `model_training/network_lenet/` |
| 编排门控 | `vpin-backend/vpin_backend/pipeline/orchestrator.py`, `gates.py` |
| API | `GET /models/{id}/ahe-manifest`, `POST /models/{id}/ahe-onboard` |
