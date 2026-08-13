# model_training

训练与测试的**完整指南**见：

**[docs/model-training/模型训练与测试指南.md](../docs/model-training/模型训练与测试指南.md)**

---

## 入口速查

```powershell
# Network A（MNIST · AHE 主轨）
.\.venv\Scripts\python.exe -m model_training.network_a.train --device cuda
.\.venv\Scripts\python.exe -m model_training.network_a.evaluate --run-dir <run> --mode full_test

# LeNet CIFAR-10
.\.venv\Scripts\python.exe model_training\run.py --task network-lenet --dataset cifar10 --device cuda

# 练习用基线 CNN
python model_training/run.py --backend pytorch --dataset mnist --epochs 1
```

统一 launcher：`model_training/run.py`（`--task network-a|network-b|network-lenet|network-resnet`）。

练习脚本：`model_training/exercises/`。
