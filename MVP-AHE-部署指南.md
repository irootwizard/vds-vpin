# MVP-AHE 同态推理部署指南

MNIST-CNN 加法同态加密推理（Network A）端到端部署，含 **Python 标准栈**、**Rust 加速栈**（Arkworks / EC 曲线）与 Tauri 桌面前端。

---

## 1. 系统要求

| 依赖 | 最低版本 | 用途 |
|------|---------|------|
| **Python** | 3.10+ | Python 推理后端 + `vpin-client` |
| **Rust** | 1.75+ (含 cargo) | Tauri 桌面壳 + **本仓 `vpin-client`/`vpin-backend` 中 `ahe-cli`/`ahe-server`** |
| **Node.js** | 18+ (含 npm) | 前端 Vite 构建 |
| **Git** | 2.30+ | 仓库管理 |

> **当前指南与一键脚本仅验证 Windows**（PowerShell、`.venv\Scripts\python.exe`、Tauri `lib.rs` 路径）。Linux/macOS 可参考 CLI 与后端部分，桌面端需自行适配 Python 路径。

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
experiment-reproduction/          # 示例父目录（路径因机器而异）
├── vPIN-main/                    # 本仓库
│   ├── .venv/                    # Python 虚拟环境（不入仓库）
│   ├── .env.example              # 环境变量模板（复制为 .env 可选）
│   ├── scripts/                  # setup / check-env / build-rust-ahe 等
│   ├── vpin-backend/             # FastAPI 推理后端（:8000）+ ahe-server
│   ├── vpin-client/              # Python 客户端 + ahe-cli（Rust）
│   ├── vpin_frontend/vpin-frontend/  # Vue3 + Tauri 桌面端（:1420）
│   ├── model_training/
│   │   └── outputs/              # ★ 预训练权重（npy + 元数据，随仓库分发）
│   ├── src/Pre_computed_table/   # Python BSGS table.pickle（~230MB，需本地生成）
│   ├── start-ahe.ps1             # 一键启动（Python + Tauri）
│   ├── docs/环境配置与手动步骤.md  # 无法自动化的步骤清单
│   └── MVP-AHE-部署指南.md
└── vpin-platform/                # （可选）旧 sibling 布局；Rust 栈已迁入 vPIN-main
```

Tauri `lib.rs` 默认在 `vpin-client/target/release/ahe-cli` 查找 Rust 客户端；BSGS `table.bin` 优先 `vpin-client/tests/fixtures/table.bin`（**不进 Git，须本地拷贝**，见 [`docs/环境配置与手动步骤.md`](docs/环境配置与手动步骤.md)）。

---

## 3. 环境初始化（首次）

> **推荐一键流程**（Windows）：
>
> ```powershell
> cd vPIN-main
> .\scripts\setup.ps1              # venv + pip + npm + Rust 检查
> .\scripts\generate-bsgs-pickle.ps1 # Python BSGS（~30 分钟，可后台）
> # 手动：拷贝 table.bin → vpin-client/tests/fixtures/（Rust 路线，见手动步骤文档）
> .\scripts\build-rust-ahe.ps1     # 可选：Rust 引擎
> .\scripts\check-env.ps1          # 预检
> ```
>
> 无法自动化的步骤（VS Build Tools、table.bin 拷贝、MNIST 首次下载等）见 **[`docs/环境配置与手动步骤.md`](docs/环境配置与手动步骤.md)**。

### 3.1 创建 Python 虚拟环境

**自动化**：`setup.ps1` 会创建 `.venv`。手动等价：

```powershell
cd vPIN-main
python -m venv .venv
```

### 3.2 安装 Python 依赖

**自动化**：`setup.ps1`。手动等价：

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
| `gmpy2` | >=2.1 | 大整数运算（`pip install -e vpin-client` 时安装） |

### 3.3 官方 MNIST 数据集（首次需联网）

MNIST **不随仓库分发**（`model_training/data/` 已在 `.gitignore` 中排除）。首次在**客户端**加载官方 MNIST 时，torchvision 会自动下载测试集到：

```
model_training/data/MNIST/raw/
  t10k-images-idx3-ubyte
  t10k-labels-idx1-ubyte
  ...
```

加载与预处理逻辑均在 `vpin-client/vpin_client/data/`（`official.py`、`upload.py`、`core.py`），由 Tauri 本地 spawn `.venv` Python 或 CLI 调用，**明文不出机**。**克隆后第一次**在 AHE 推理页加载官方 MNIST 需要可访问外网；下载完成后可离线使用。

### 3.4 安装前端依赖

```powershell
cd vpin_frontend\vpin-frontend
npm install
cd ..\..
```

### 3.5 模型权重（已随仓库分发，无需重新训练）

仓库在 `model_training/outputs/` 中包含 **4 个预训练 run**，克隆后即可直接使用：

| Run 目录 | 网络 | 模型 ID | 权重文件 |
|---------|------|---------|---------|
| `20260622_174721/` | Network A | `cnn-mnist-trained`（备用） | `weight_fc1_64_16.npy` 等 4 个 |
| `20260622_184254/` | Network A | **`cnn-mnist-trained`**（主用） | 同上 + `proof_artifacts/` |
| `20260623_185153/` | LeNet-CIFAR | `lenet-cifar10`（备用） | `weight_conv1_6_3_5_5.npy` 等 13 个 |
| `20260623_185935/` | LeNet-CIFAR | **`lenet-cifar10`**（主用） | 同上 |

每个 run 含：npy 权重 + `registry_snippet.json` + `metrics.json` + `truncation_config.json`。

> **MVP-AHE 桌面演示**当前仅支持 **Network A**（`cnn-mnist-trained` / `cnn-mnist`）。LeNet-CIFAR 权重在仓内供训练/后续扩展，**不会**出现在 `?capability=ahe` 列表。

> **注意**：`.pt` checkpoint 文件已被 `.gitignore` 排除（可由 npy 完全替代）。
> `src/cnn_networks/Pre_trained_model/` 下的 legacy 权重已随原仓库跟踪，用于 `cnn-mnist` legacy 模型。

### 3.6 BSGS 预计算表

Python 与 Rust 使用**不同格式**的 BSGS 表，按所选推理引擎准备：

| 栈 | 文件 | 路径 | 说明 |
|----|------|------|------|
| **Python** | `table.pickle` | `src/Pre_computed_table/table.pickle` | ~230MB，`ecdsa` 客户端解密用 |
| **Rust** | `table.bin` | `vpin-client/tests/fixtures/table.bin`（推荐） | `ahe-cli` / `ahe-server` 用；**不进 Git，须本地拷贝** |
| Rust 回退 | `table.bin` | `src/Pre_computed_table/table.bin` | fixture 不存在时使用 |
| 旧 layout | `table.bin` | `../vpin-platform/tests/fixtures/table.bin` | sibling platform 仍存在时 |

**Python 表**因体积过大已被 `.gitignore` 排除。**自动化生成**：

```powershell
.\scripts\generate-bsgs-pickle.ps1
```

**Rust 表**：从开发机或 sibling `vpin-platform` **手动拷贝**到 `vpin-client/tests/fixtures/table.bin`。勿使用损坏文件，否则 Rust 推理报 `discrete log not found`。

### 3.7 模型注册表

| 文件 | 路径 | 说明 |
|------|------|------|
| 注册表 | `vpin-backend/data/models/registry.json` | **随仓库分发**，克隆即可用 |
| 训练片段 | `model_training/outputs/*/registry_snippet.json` | 各 run 的模型元数据，bootstrap 扫描合并 |

仓库已包含默认注册表（`cnn-mnist`、`cnn-mnist-trained`、`lenet-cifar10` 等）。后端每次启动执行 `bootstrap_ahe_models()`：

1. 扫描 `model_training/outputs/` 中含 `registry_snippet.json` 的 run 并 upsert 到注册表  
2. 调用 `repair_registry_paths()`，将陈旧的本机绝对路径改写为**仓库相对路径**

**`weights_dir` 路径约定**（换机器 clone 后必须遵守）：

| 写法 | 示例 | 说明 |
|------|------|------|
| ✅ 推荐 | `model_training/outputs/20260622_184254` | 相对仓库根、正斜杠 |
| ✅ Legacy | `src/cnn_networks/Pre_trained_model` | 原仓库 legacy 权重 |
| ❌ 禁止 | `D:\WorkStation\...\20260622_184254` | 本机绝对路径，换环境会失效 |

注册、上传模型时后端通过 `store_weights_path()` 自动写入相对路径；API 与 bootstrap 通过 `resolve_weights_dir()` 解析（支持相对路径，并对旧绝对路径尝试按 `model_training/`、`src/` 片段回退）。

**一般无需手动编辑** `registry.json`；若从旧环境拷贝了含绝对路径的注册表，重启后端即可自动修复。

### 3.8 Rust AHE 栈（本仓 `vpin-client` / `vpin-backend`，可选）

UI `/demo/ahe` 提供三种推理引擎；除 Python 外，另两种需编译并启动 Rust server：

| UI 引擎 | 客户端（Tauri spawn） | 服务端 | WS 端口 | 密码栈 |
|---------|----------------------|--------|---------|--------|
| Python 标准 · vpin-backend | `vpin_client.cli` | `vpin-backend` | **8000** | Python `ecdsa` |
| Rust 加速 · Arkworks | `ahe-cli --crypto-backend ark` | `ahe-server` | **8001** | Rust E2 |
| Rust 加速 · EC 曲线 | `ahe-cli --crypto-backend ec` | `ahe-server` | **8002** | Rust EC |

**自动化编译**：

```powershell
.\scripts\build-rust-ahe.ps1
# 输出:
#   vpin-client/target/release/ahe-cli.exe
#   vpin-backend/target/release/ahe-server.exe
```

**自动化启动 Rust server**：

```powershell
.\scripts\start-rust-ahe.ps1 -Both   # :8001 + :8002
```

Rust 栈与 Python 栈共用 `VPIN_REPO_ROOT` 下的权重与 MNIST；模型列表 REST API 仍走 Python `:8000`，Rust server 启动时读取同一 `registry.json`。

> 全栈 UI 测试步骤见 [`docs/ahe-ui-client-server-test-startup.md`](docs/ahe-ui-client-server-test-startup.md)。

---

## 4. 一键启动

### 4.1 推荐：`start-ahe.ps1`（项目根目录）

完成 §3 环境初始化且已生成 BSGS 表后，在 **项目根目录** 执行：

```powershell
cd vPIN-main
.\start-ahe.ps1
```

脚本会检查：`.venv`、BSGS 表、模型 npy 权重、Python 依赖、端口占用；随后启动 **Python 后端（:8000）** 与 `npm run tauri dev`。按 Enter 停止全部服务。

> **不含 Rust server**：使用 UI 中「Rust Ark / Rust EC」引擎前，须另开终端启动 §4.6 中的 `ahe-server`（:8001 / :8002）。

### 4.2 手动分终端启动（与脚本等价）

**终端 1 — 后端**（须在 `vpin-backend/` 下运行，`vpin_backend` 包不在仓库根目录）：

```powershell
cd vPIN-main\vpin-backend
..\.venv\Scripts\python.exe -m vpin_backend.main
# 输出：Uvicorn running on http://127.0.0.1:8000
```

**终端 2 — Tauri 桌面端**（自动启动 Vite + Rust 编译）：

```powershell
cd vPIN-main\vpin_frontend\vpin-frontend
npm run tauri dev
# 首次编译 Rust 约 1–3 分钟，后续增量编译 <10s
# 弹出「VDS-VPIN 工作台」桌面窗口
```

> **注意**：不要在根目录直接 `python -m vpin_backend.main`（会报 `No module named 'vpin_backend'`），除非已执行 `pip install -e vpin-backend`。
>
> **注意**：不要单独运行 `npm run dev`（会占用 1420 端口），`tauri dev` 会自动管理 Vite。

### 4.3 验证部署成功

| 检查项 | 方式 | 预期 |
|--------|------|------|
| 后端健康 | 浏览器访问 `http://127.0.0.1:8000/docs` | Swagger UI |
| 模型列表 | `http://127.0.0.1:8000/api/v1/models?capability=ahe` | JSON 含 `cnn-mnist-trained` |
| MNIST 预处理（本地） | Tauri AHE 页 → 官方 MNIST 画廊 | 缩略图与定点张量（**首次需联网**下载 MNIST；不经后端 REST） |
| Rust server（可选） | `http://127.0.0.1:8001/api/v1/health` 或 `:8002` | 200（测 Rust 引擎时） |
| Tauri 窗口 | 桌面 | 「VDS-VPIN 工作台」窗口 |
| AHE 推理页 | 窗口内 → 模型仓库 → AHE 推理 | `/demo/ahe`：选择推理引擎 + 模型 + 单图/批量 |

### 4.4 CLI 快速验证（无需前端）

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

### 4.5 批量 AHE 评估

**桌面端**（Tauri `/demo/ahe`）：推理区选择「批量」模式，可指定 MNIST 序号范围或画廊多选，并设置并发 WebSocket 会话数（建议 ≤ CPU 核数）。需先在同一预处理轨完成样本选择。

**CLI**（无需前端，适合脚本化压测）：

```powershell
# 批量评估 test 集前 10 张，并发 4（约 2 分钟，acc 应与串行一致）
.\.venv\Scripts\python.exe -m vpin_client eval-mnist-ahe `
  --backend ws://127.0.0.1:8000/api/v1/session/ws `
  --model cnn-mnist-trained `
  --limit 10 --concurrency 4 --progress
```

CLI 结果写入仓库根目录 `reports/batch_{limit}_{时间戳}.json`。`--concurrency 1` 为串行回退。UI 与 CLI 并发设计见 [`docs/ahe/ahe-批量推理-性能优化设计.md` §10–11](docs/ahe/ahe-批量推理-性能优化设计.md)。

### 4.6 Rust AHE 启动与验证（可选）

**推荐启动顺序**：Python `:8000`（REST + Python 推理，始终需要）→ Rust `:8001` / `:8002`（按 UI 引擎）→ Tauri。

**终端 — Rust server · Ark（:8001）**

```powershell
.\scripts\start-rust-ahe.ps1
# 或手动：
$env:VPIN_REPO_ROOT = "D:\path\to\vPIN-main"
$env:VPIN_BSGS_TABLE = "D:\path\to\vPIN-main\vpin-client\tests\fixtures\table.bin"
$env:AHE_SERVER_PORT = "8001"
.\vpin-backend\target\release\ahe-server.exe
```

**终端 — Rust server · EC（:8002）**

```powershell
.\scripts\start-rust-ahe.ps1 -Both
# 或手动将 AHE_SERVER_PORT=8002 另开进程
```

**CLI 单图冒烟（无需 Tauri）**

```powershell
$env:VPIN_REPO_ROOT = "D:\path\to\vPIN-main"
$env:VPIN_BSGS_TABLE = "D:\path\to\vPIN-main\vpin-client\tests\fixtures\table.bin"
.\vpin-client\target\release\ahe-cli.exe infer `
  --crypto-backend ec `
  --model cnn-mnist-trained `
  --mnist-index 0 `
  --timing
```

**CLI 批量**

```powershell
.\target\release\ahe-cli.exe eval-mnist-ahe `
  --crypto-backend ec `
  --model cnn-mnist-trained `
  --start 0 --limit 10 --concurrency 2 --progress-ndjson
```

**三引擎自动化对照**（需 8000 + 8001 + 8002 均已启动）：

```powershell
.\scripts\run_ahe_triple_test.ps1 -Limit 10
```

UI 中切换引擎时，预处理区分为 **Python 轨**（REST :8000）与 **Rust 轨**（本地 `ahe-cli` 预处理）；两轨画廊与时间线相互独立。

---

## 5. 端口与服务架构

### 5.1 三引擎总览

| 推理引擎 | 预处理轨 | Client（Tauri spawn） | Server | 端口 |
|----------|----------|----------------------|--------|------|
| Python 标准 | Python 预处理区（REST） | `vpin_client.cli` | `vpin-backend` | **8000** |
| Rust · Arkworks | Rust 预处理区 | `ahe-cli` | `ahe-server` (ark) | **8001** |
| Rust · EC 曲线 | Rust 预处理区 | `ahe-cli` | `ahe-server` (ec) | **8002** |

- **REST**（模型列表、Python 预处理、上传）：始终走 `:8000`
- **AHE 推理**：按 UI 所选引擎连接对应 WebSocket
- **私钥**：仅驻留本地 Client 进程，不经网络传输
- **浏览器**（`npm run dev`）：仅可预览预处理；推理须在 Tauri 桌面端

### 5.2 Python 路线（默认）

```
┌──────────────────────────────────────────────────────┐
│  Tauri 桌面端  (vpin-frontend.exe)                    │
│  ┌────────────────────┐   ┌────────────────────────┐ │
│  │ Vue3 SPA (Vite)    │   │ Rust bridge (lib.rs)   │ │
│  │ localhost:1420      │   │ invoke → .venv/python  │ │
│  └────────┬───────────┘   └──────────┬─────────────┘ │
│           │ /api/v1 proxy             │ 本地预处理     │
│           │ (models 等)               │ vpin_client   │
└───────────┼───────────────────────────┼──────────────┘
            │                           │ 加密后密文
            ▼                           ▼ ws://:8000/session/ws
┌──────────────────────────────────────────────────────┐
│  Python 后端  (vpin_backend)  127.0.0.1:8000          │
│  ├─ REST API  /api/v1/models（无 /data/* 预处理）      │
│  └─ WebSocket /api/v1/session/ws  ←→  AheEngine       │
└──────────────────────────────────────────────────────┘
```

### 5.3 Rust 路线（Ark / EC）

```
┌──────────────────────────────────────────────────────┐
│  Tauri 桌面端                                         │
│  lib.rs → spawn ahe-cli (VPIN_REPO_ROOT + table.bin) │
└──────────────────────────┬───────────────────────────┘
                           │ ws://:8001 或 :8002/session/ws
                           ▼
┌──────────────────────────────────────────────────────┐
│  ahe-server  (vpin-platform, axum)                    │
│  同态卷积 / 池化 / 全连接（Rust 密码栈 ark 或 ec）     │
└──────────────────────────────────────────────────────┘
         权重 / registry ← VPIN_REPO_ROOT → vPIN-main
```

进度事件：`stderr` NDJSON → Tauri `ahe-progress` → UI 时间线（Python / Rust 共用）。

---

## 6. 配置项

### 6.1 Python 后端（`vpin-backend`）

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `VPIN_REPO_ROOT` | 自动检测 | 仓库根目录；跨机器部署时优先检查 |
| `VPIN_DATA_DIR` | `vpin-backend/data/` | 模型注册表、上传目录 |
| `VPIN_BSGS_TABLE` | `src/Pre_computed_table/table.pickle` | Python BSGS 表 |
| `VPIN_API_HOST` | `127.0.0.1` | 后端绑定地址 |
| `VPIN_API_PORT` | `8000` | 后端端口 |

> 所有 `weights_dir` 均相对 `VPIN_REPO_ROOT` 解析。

### 6.2 Rust AHE（本仓 + Tauri）

| 环境变量 | 作用 | 典型值 |
|---------|------|--------|
| `VPIN_REPO_ROOT` | 权重、MNIST、registry 根 | `...\vPIN-main` |
| `VPIN_CLIENT_ROOT` | Tauri 定位 `ahe-cli` | `...\vPIN-main\vpin-client` |
| `VPIN_BSGS_TABLE` | Rust 客户端 BSGS | `...\vpin-client\tests\fixtures\table.bin` |
| `AHE_SERVER_HOST` | Rust server 绑定 | `127.0.0.1` |
| `AHE_SERVER_PORT` | Rust server 端口 | `8001`（ark）/ `8002`（ec） |

Rust 密码栈由 **`ahe-cli --crypto-backend ark|ec`** 指定，非 `AHE_CRYPTO_BACKEND` 环境变量。

Tauri 前端代理配置：

```javascript
// vpin_frontend/vpin-frontend/vite.config.js
proxy: { "/api/v1": { target: "http://127.0.0.1:8000" } }
```

---

## 7. AHE 推理协议（P0–P3）

Python（`vpin-backend`）与 Rust（`ahe-server`）WebSocket 会话均遵循同一 P0–P3 四轮交互；Client 侧分别为 `vpin_client` 与 `ahe-cli`。

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
netstat -ano | findstr ":8000"
netstat -ano | findstr ":8001"
netstat -ano | findstr ":8002"
netstat -ano | findstr ":1420"
Stop-Process -Id <PID> -Force
```

### Rust 引擎无法推理

1. 确认已编译：`vpin-backend\target\release\ahe-server.exe` 与 `vpin-client\target\release\ahe-cli.exe`（`scripts\build-rust-ahe.ps1`）
2. 确认对应端口 server 已启动（`scripts\start-rust-ahe.ps1 -Both`）
3. 确认 `VPIN_BSGS_TABLE` 指向有效 `table.bin`（见手动步骤文档）  
4. 确认 `VPIN_REPO_ROOT` 指向 `vPIN-main` 根目录（含 `model_training/outputs/`）

停止 Rust server：`Get-Process ahe-server -ErrorAction SilentlyContinue | Stop-Process -Force`

### BSGS 表缺失（首次部署必须生成）

**Python 路线**：生成 `table.pickle`（见 §3.6）。

**Rust 路线**：手动拷贝有效 `table.bin` 到 `vpin-client/tests/fixtures/`（见 [`docs/环境配置与手动步骤.md`](docs/环境配置与手动步骤.md) §3.2）。

### Tauri 编译失败

确认已安装：
- Rust：`rustup update`
- VS Build Tools C++ 工作负载
- WebView2（Windows 10/11 自带）

### MNIST 预处理失败 / 超时

确认本机可访问外网。首次请求会下载到 `model_training/data/MNIST/raw/`。若公司网络拦截，可在一台能下载的机器上拷贝该目录到克隆仓库的相同路径。

### 模型权重未被识别

1. 确认 `model_training/outputs/` 下对应 run 含完整 npy 文件  
2. 检查 `vpin-backend/data/models/registry.json` 是否随 clone 存在  
3. 查看 `weights_dir` 是否为**相对路径**（如 `model_training/outputs/20260622_184254`），勿保留 `D:\...` 等绝对路径  
4. **重启后端**：`bootstrap_ahe_models()` 会扫描 `registry_snippet.json` 并执行 `repair_registry_paths()` 自动修复陈旧路径  
5. 若仍失败，设置 `VPIN_REPO_ROOT` 为 clone 根目录后重试  
6. 验证：`http://127.0.0.1:8000/api/v1/models?capability=ahe` 应含 `cnn-mnist-trained`

后端启动时若 bootstrap 异常，会打印 `Warning: Model bootstrap failed` 但服务仍会继续；此时模型列表可能为空，需根据 stderr 排查依赖或路径问题。

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
