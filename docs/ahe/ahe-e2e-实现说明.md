# AHE 端到端实现说明

## 概述

本实现提供 **Network A (`cnn-mnist`)** 的纯 AHE 同态推理闭环（P0–P3），无 CP-SNARK / Pedersen 承诺。

## 环境

所有 Python 命令使用项目虚拟环境：

```powershell
cd d:\WorkStation\pythoncode\experiment-reproduction\vPIN-main
.\.venv\Scripts\python.exe -m pip install -e vpin-client
.\.venv\Scripts\pip.exe install -r vpin-backend\requirements.txt torchvision pillow websockets
```

## 数据准备

**推荐（官方 MNIST + 训练权重）**：见 [network-a-任务状态与接续.md](./network-a-任务状态与接续.md)。数据缓存于 `model_training/data/mnist/`，权重注册为 `cnn-mnist-trained`。

**Legacy（仅验证旧预训练权重）**：

```powershell
.\.venv\Scripts\python.exe scripts\restore_network_a_weights.py
```

> `scripts/prepare_mnist_network_a.py` 与 `vpin-backend/data/mnist/` 为旧流程，新验收请使用官方 MNIST（`vpin_client.data.official_mnist`）。

## 启动服务端

```powershell
cd vpin-backend
..\.venv\Scripts\python.exe -m vpin_backend.main
```

默认：`http://127.0.0.1:8000`，WebSocket：`ws://127.0.0.1:8000/api/v1/session/ws`

## 客户端 CLI

单图推理（含计时 JSON）：

```powershell
.\.venv\Scripts\python.exe -m vpin_client ahe-infer `
  --backend ws://127.0.0.1:8000/api/v1/session/ws `
  --model cnn-mnist-trained `
  --mnist-index 0 `
  --timing
```

**E2E 验收脚本**（对比 AHE logits 与 homomorphic 明文路径，需后端已启动）：

```powershell
.\.venv\Scripts\python.exe scripts\ahe_e2e_smoke.py --model cnn-mnist-trained --mnist-index 0
.\.venv\Scripts\python.exe scripts\ahe_e2e_smoke.py --model cnn-mnist --mnist-index 0
```

批量评估（单图门槛通过后）：

```powershell
.\.venv\Scripts\python.exe -m vpin_client eval-mnist-ahe --limit 50 --progress
```

## 协议流程（P0–P3）

1. `SessionStart` → `SessionAccept`
2. `ModelSelect` → `ModelSelectAck`（含 `weights_digest_hex`、截断计划）
3. `InputDigest` → `InputDigestAck`（SHA256 摘要，仅日志）
4. `PublicKey` + `CiphertextPayload(initial)`
5. 四轮：`CiphertextPayload`（服务端输出）→ `TruncateRequest` → 客户端解密/relu/shift/重加密 → `CiphertextPayload`（回传）
6. `InferenceComplete` → `SessionEnd`

| phase_id   | client_action   | shift_bits |
|------------|-----------------|------------|
| after_conv | relu            | —          |
| after_pool | shift           | 24         |
| after_fc1  | relu_then_shift | 30         |
| after_fc2  | relu_only       | —（本地结束）|

## 前端

- 路由：`/demo/ahe`（AHE 密态推理实验室）
- Tauri 命令：`ahe_preprocess`、`run_ahe_inference`（调用 `.venv` Python）
- Dev proxy：`vite.config.js` → `http://127.0.0.1:8000`

## 关键模块

| 模块 | 路径 |
|------|------|
| 同态 Network A | `vpin-backend/vpin_backend/inference/homomorphic_network_a.py` |
| 推理状态机 | `vpin-backend/vpin_backend/inference/ahe_engine.py` |
| WS 路由 | `vpin-backend/vpin_backend/api/routes/session.py` |
| 客户端驱动 | `vpin-client/vpin_client/protocol/ws_ahe_client.py` |
| 预处理 | `vpin-client/vpin_client/data/preprocess.py` |

## 性能说明

单次推理涉及数千次椭圆曲线点加/乘与 BSGS 解密，**完整 E2E 可能需数分钟**（取决于 CPU）。验收指标：`crypto_infer_ms < 4s` 为理想目标，当前实现为功能正确性优先的参考移植。
