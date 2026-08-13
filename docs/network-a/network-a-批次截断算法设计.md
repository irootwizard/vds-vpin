# Network A 批次截断算法设计

> **已收束** → 请参阅 **[模型训练与测试指南](../model-training/模型训练与测试指南.md)** §4.6。

要点：本征尺度 **shift_pool=26 / shift_fc1=32**；批次扫描仅验证 BSGS/int32 安全，不降低 from_bits。

实现：`model_training/network_a/truncation_config.py`
