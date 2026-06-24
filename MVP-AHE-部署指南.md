# MVP-AHE 同态推理部署指南

MNIST-CNN 加法同态加密推理（Network A）端到端部署，含后端（Python）与 Tauri 桌面前端。

---

## 1. 系统要求

| 依赖 | 最低版本 | 用途 |
|------|---------|------|
| **Python** | 3.10+ | 推理后端 + 客户端加密 |
| **Rust** | 1.75+ (含 cargo) | Tauri 桌面端编译 |
| **Node.js** | 18+ (含 npm) | 前端 Vite 构建 |
| **Git** | 2.30+ | 仓库管理 |

> Windows：确保已安装 [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) C++ 工作负载（Tauri 编译需要）。

### 当前验证通过的版本

```
Python  3.11.7
Rust    1.91.1
Node.js 22.22.0
npm     11.9.0
```

---

## 2. 仓库结构

```
vPIN-main/
├── .venv/                        # Python 虚拟环境（不入仓库）
├── vpin-backend/                 # FastAPI 推理后端（8000 端口）
├── vpin-client/                  # Python 客户端（AHE 加解密 + WS 协议）
├── vpin_frontend/vpin-frontend/  # Vue3 + Tauri 桌面端（1420 端口）
├── model_training/               # 训练脚本
│   └── outputs/                  # ★ 预训练权重（npy + 元数据，随仓库分发）
│       ├── 20260622_184254/      #   Network A (cnn-mnist-trained)
│       └── 20260623_185935/      #   LeNet-CIFAR (lenet-cifar10)
├── src/Pre_computed_table/       # BSGS 预计算表（~230MB，需本地生成）
├── src/cnn_networks/             # Legacy 权重（随原仓库跟踪）
├── scripts/                      # 工具脚本
├── start-ahe.ps1                 # 一键启动脚本
└── MVP-AHE-部署指南.md           # 本文件
```

---

## 3. 环境初始化（首次）

### 3.1 创建 Python 虚拟环境

```powershell
cd vPIN-main
python -m venv .venv
```

### 3.2 安装 Python 依赖

```powershell
# 客户端（editable 安装，含 ecdsa/numpy/websockets/pillow）
.\.venv\Scripts\pip.exe install -e vpin-client

# 后端（FastAPI + uvicorn）
.\.venv\Scripts\pip.exe install -r vpin-backend\requirements.txt

# 数据加载（训练权重 + MNIST 数据集）
.\.venv\Scripts\pip.exe install torch torchvision pillow websockets
```

**完整 Python 依赖列表**：

| 包 | 版本 | 来源 |
|----|------|------|
| `ecdsa` | ==0.19.0 | ElGamal 曲线运算 |
| `numpy` | >=2.0.0 | 张量 / 定点运算 |
| `websockets` | >=12.0 | 客户端 WS 驱动 |
| `pillow` | >=10.0 | 图像预处理预览 |
| `fastapi` | >=0.110.0 | 后端 API 框架 |
| `uvicorn[standard]` | >=0.27.0 | ASGI 服务器 |
| `pydantic` | >=2.6.0 | 消息序列化 |
| `pydantic-settings` | >=2.2.0 | 后端配置 |
| `python-multipart` | >=0.0.9 | 文件上传 |
| `torch` | >=2.0 | MNIST 数据加载（仅 CPU） |
| `torchvision` | >=0.15 | 官方 MNIST 数据集 |

### 3.3 安装前端依赖

```powershell
cd vpin_frontend\vpin-frontend
npm install
cd ..\..
```

### 3.4 模型权重（已随仓库分发，无需重新训练）

仓库在 `model_training/outputs/` 中包含 **4 个预训练 run**，克隆后即可直接使用：

| Run 目录 | 网络 | 模型 ID | 权重文件 |
|---------|------|---------|---------|
| `20260622_174721/` | Network A | `cnn-mnist-trained`（备用） | `weight_fc1_64_16.npy` 等 4 个 |
| `20260622_184254/` | Network A | **`cnn-mnist-trained`**（主用） | 同上 + `proof_artifacts/` |
| `20260623_185153/` | LeNet-CIFAR | `lenet-cifar10`（备用） | `weight_conv1_6_3_5_5.npy` 等 13 个 |
| `20260623_185935/` | LeNet-CIFAR | **`lenet-cifar10`**（主用） | 同上 |

每个 run 含：npy 权重 + `registry_snippet.json` + `metrics.json` + `truncation_config.json`。

> **注意**：`.pt` checkpoint 文件已被 `.gitignore` 排除（可由 npy 完全替代）。
> `src/cnn_networks/Pre_trained_model/` 下的 legacy 权重已随原仓库跟踪，用于 `cnn-mnist` legacy 模型。

### 3.5 BSGS 预计算表

| 文件 | 路径 | 大小 | 说明 |
|------|------|------|------|
| BSGS 表 | `src/Pre_computed_table/table.pickle` | ~230MB | 椭圆曲线离散对数预计算，**不可缺少** |

BSGS 表因体积过大已被 `.gitignore` 排除。**首次部署须生成**：

```powershell
cd src\Pre_computed_table
..\..\..\.venv\Scripts\python.exe baby-step-giant-step.py
# 约 30 分钟，生成 table.pickle (~230MB)
```

### 3.6 模型注册表

| 文件 | 路径 | 说明 |
|------|------|------|
| 注册表 | `vpin-backend/data/models/registry.json` | 后端启动时自动 bootstrap |

后端首次启动会扫描 `model_training/outputs/` 下含 `registry_snippet.json` 的 run，自动注册为可用模型。无需手动配置。

---

## 4. 一键启动

### 4.1 PowerShell 启动脚本

项目已提供一键启动，在 **项目根目录** 按顺序在两个终端执行：

**终端 1 — 后端**：

```powershell
cd vPIN-main
.\.venv\Scripts\python.exe -m vpin_backend.main
# 输出：Uvicorn running on http://127.0.0.1:8000
```

**终端 2 — Tauri 桌面端**（自动启动 Vite + Rust 编译）：

```powershell
cd vPIN-main\vpin_frontend\vpin-frontend
npm run tauri dev
# 首次编译 Rust 约 1–3 分钟，后续增量编译 <10s
# 弹出「VDS-VPIN 工作台」桌面窗口
```

> **注意**：不要单独运行 `npm run dev`（会占用 1420 端口），`tauri dev` 会自动管理 Vite。

### 4.2 验证部署成功

| 检查项 | 方式 | 预期 |
|--------|------|------|
| 后端健康 | 浏览器访问 `http://127.0.0.1:8000/docs` | Swagger UI |
| 模型列表 | `http://127.0.0.1:8000/api/v1/models?capability=ahe` | JSON 含 `cnn-mnist-trained` |
| MNIST 预处理 | `http://127.0.0.1:8000/api/v1/data/official/test/0` | JSON 含 `preview_png_base64` |
| Tauri 窗口 | 桌面 | 「VDS-VPIN 工作台」窗口 |
| AHE 推理页 | 窗口内 → 模型仓库 → AHE 推理 | `/demo/ahe` 页面 |

### 4.3 CLI 快速验证（无需前端）

```powershell
# 单图 AHE 推理（约 45–70s）
.\.venv\Scripts\python.exe -m vpin_client ahe-infer `
  --backend ws://127.0.0.1:8000/api/v1/session/ws `
  --model cnn-mnist-trained `
  --mnist-index 0 `
  --timing

# E2E 正确性对照（AHE vs 明文同态路径）
.\.venv\Scripts\python.exe scripts\ahe_e2e_smoke.py `
  --model cnn-mnist-trained --mnist-index 0 --json
```

预期：`prediction=7, label=7, logit_max_diff=0.0, pass=true`

### 4.4 批量 AHE 评估（CLI，前端尚未实现）

桌面端 `/demo/ahe` **目前仅支持单图推理**；批量吞吐能力请先用 CLI。UI 适配方案见 [`docs/ahe/ahe-批量推理-性能优化设计.md` §11](docs/ahe/ahe-批量推理-性能优化设计.md)。

```powershell
# 批量评估 test 集前 10 张，并发 4（约 2 分钟，acc 应与串行一致）
.\.venv\Scripts\python.exe -m vpin_client eval-mnist-ahe `
  --backend ws://127.0.0.1:8000/api/v1/session/ws `
  --model cnn-mnist-trained `
  --limit 10 --concurrency 4 --progress
```

结果写入仓库根目录 `reports/batch_{limit}_{时间戳}.json`。`--concurrency 1` 为串行回退；详见设计文档 §10.4 实测数据。

---

## 5. 端口与服务架构

```
┌──────────────────────────────────────────────────────┐
│  Tauri 桌面端  (vpin-frontend.exe)                    │
│  ┌────────────────────┐   ┌────────────────────────┐ │
│  │ Vue3 SPA (Vite)    │   │ Rust bridge (lib.rs)   │ │
│  │ localhost:1420      │   │ invoke → .venv/python  │ │
│  └────────┬───────────┘   └──────────┬─────────────┘ │
│           │ /api/v1 proxy             │ ahe-infer CLI │
└───────────┼───────────────────────────┼──────────────┘
            │                           │
            ▼                           ▼
┌──────────────────────────────────────────────────────┐
│  Python 后端  (vpin_backend)  127.0.0.1:8000          │
│  ├─ REST API  /api/v1/models, /data/official/...      │
│  └─ WebSocket /api/v1/session/ws  ←→  AheEngine       │
│     同态卷积 / 池化 / 全连接（密文上操作）              │
└──────────────────────────────────────────────────────┘
            ▲
            │ P0–P3 WebSocket 四轮交互
            ▼
┌──────────────────────────────────────────────────────┐
│  Python 客户端  (vpin_client)  由 Tauri/CLI 调用       │
│  ├─ ElGamal 加解密 (ecdsa + BSGS)                     │
│  ├─ ReLU / 截断 / 重加密                               │
│  └─ 私钥驻留本地，不经网络传输                          │
└──────────────────────────────────────────────────────┘
```

---

## 6. 配置项

后端配置通过环境变量或 `.env` 文件（可选）：

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `VPIN_REPO_ROOT` | 自动检测 | 仓库根目录 |
| `VPIN_DATA_DIR` | `vpin-backend/data/` | 模型注册表、上传目录 |
| `VPIN_BSGS_TABLE` | `src/Pre_computed_table/table.pickle` | BSGS 查找表路径 |
| `VPIN_API_HOST` | `127.0.0.1` | 后端绑定地址 |
| `VPIN_API_PORT` | `8000` | 后端端口 |

Tauri 前端代理配置：

```javascript
// vpin_frontend/vpin-frontend/vite.config.js
proxy: { "/api/v1": { target: "http://127.0.0.1:8000" } }
```

---

## 7. AHE 推理协议（P0–P3）

```
客户端                                服务端
  ├─ P0 SessionStart ──────────────→ SessionAccept
  ├─ P1 ModelSelect ───────────────→ ModelSelectAck (截断计划+权重摘要)
  ├─ P2 InputDigest(SHA256) ───────→ InputDigestAck
  ├─ P3 PublicKey(h=sk·G) ────────→ 加载权重 → 构造 AheEngine
  ├─ encrypt(fixed_int32) ────────→ 同态卷积 + 偏置
  │  ←── 密文(after_conv) + TruncateRequest(relu)
  ├─ 解密 → ReLU → 重加密 ────────→ 同态池化 + 展平
  │  ←── 密文(after_pool) + TruncateRequest(shift 26)
  ├─ 解密 → shift → 重加密 ───────→ 同态 FC1
  │  ←── 密文(after_fc1) + TruncateRequest(relu_then_shift 32)
  ├─ 解密 → ReLU → shift → 重加密 → 同态 FC2
  │  ←── 密文(after_fc2) + TruncateRequest(relu_only)
  └─ 解密 → ReLU → argmax          InferenceComplete → SessionEnd
```

---

## 8. 常见问题

### 端口被占用

```powershell
# 查看占用
netstat -ano | findstr ":8000"
netstat -ano | findstr ":1420"
# 释放
Stop-Process -Id <PID> -Force
```

### Tauri 编译失败

确认已安装：
- Rust：`rustup update`
- VS Build Tools C++ 工作负载
- WebView2（Windows 10/11 自带）

### BSGS 表缺失（首次部署必须生成）

```powershell
cd src\Pre_computed_table
..\..\..\.venv\Scripts\python.exe baby-step-giant-step.py
# 生成 table.pickle（约 230MB，需 30 分钟）
```

### 模型权重未被识别

确认 `model_training/outputs/` 下的 run 包含 npy 文件和 `registry_snippet.json`。后端启动时 `bootstrap_ahe_models()` 会自动扫描并注册。可手动检查：`http://127.0.0.1:8000/api/v1/models?capability=ahe`

### 推理超时 / WebSocket 断连

单次推理约 45–70 秒，WebSocket 默认无 ping/timeout。若后端被前一个会话阻塞，重启后端即可。

### Tauri 版本警告

```
tauri (v2.11.3) : @tauri-apps/api (v2.10.1)
```

不影响运行。对齐版本：`cd vpin_frontend/vpin-frontend && npm update @tauri-apps/api`

---

## 9. 性能参考

| 指标 | 值 | 说明 |
|------|---|------|
| 单次 E2E 推理 | 45–70s | CPU 密集（椭圆曲线点加/乘 + BSGS） |
| 预处理 | <5ms | pad + normalize + quantize |
| 点加/乘次数 | ~18k/~18k | Network A 全链路 |
| logit 精度 | bit-exact | AHE 与明文同态路径差为 0.0 |
| MNIST 准确率 (float) | 92.93% | Network A 训练后测试集准确率 |
| 定点/AHE 推理准确率 | 90.0% (100 样本) | Q16 定点截断路径，AHE 密文与明文 bit-exact |
