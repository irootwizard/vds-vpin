# AHE 全栈 UI–Client–Server 测试启动指南

供测试 Agent 启动各端并验证 **Tauri UI ↔ 本地 Client ↔ AHE Server** 交互。本文仅描述启动步骤与注意事项，不含业务改造说明。

---

## 1. 仓库与目录

| 路径 | 说明 |
|------|------|
| `vPIN-main/` | Python 后端、前端 Tauri、vpin-client、权重与 MNIST |
| `vpin-platform/` | Rust `ahe-server` / `ahe-cli`（与 vPIN-main **同级目录**） |

示例根目录（路径因机器而异）：

```
<parent>/
├── vPIN-main/          # 本仓库
└── vpin-platform/      # 可选：旧版同级 Rust 仓库（脚本会自动探测）
```

> Rust 二进制优先使用 `vPIN-main/vpin-client` 与 `vPIN-main/vpin-backend` 内编译产物；若不存在则回退到同级 `vpin-platform/`。

---

## 3.5 一键启动（推荐）

在 **`vPIN-main` 仓库根目录** 执行（无需硬编码路径）：

| 场景 | 命令 |
|------|------|
| **三引擎 + Tauri**（各服务独立窗口） | `.\scripts\start-ahe-full.ps1` |
| Python + Tauri（当前终端阻塞） | `.\start-ahe.ps1` |
| 仅 Rust 引擎 | `.\scripts\start-rust-ahe.ps1 -Both -Detach` |
| 首次环境 | `.\scripts\setup.ps1` → `.\scripts\check-env.ps1` |

可选环境变量（一般不必设置，脚本自动探测）：

| 变量 | 作用 |
|------|------|
| `VPIN_REPO_ROOT` | 覆盖仓库根目录 |
| `VPIN_PLATFORM_ROOT` | 覆盖同级 `vpin-platform` 路径 |
| `VPIN_BSGS_TABLE` | 覆盖 Rust 用 `table.bin` 路径 |

---

## 2. 架构与端口（测试前必读）

### 主动 / 被动

| 层级 | 组件 | 角色 |
|------|------|------|
| **UI** | Tauri 桌面端 `/demo/ahe` | **被动**：监听 `ahe-progress` 事件，渲染时间线 |
| **Client** | Tauri 内 spawn 的 `vpin_client.cli` 或 `ahe-cli` | **主动**：WebSocket 驱动 P0–P3，私钥在本地 |
| **Server** | `vpin-backend` 或 `ahe-server` | **被动响应**：同态计算，返回 TruncateRequest |

浏览器 **不能** 跑 AHE 推理（无私钥）；测试推理必须用 **Tauri 桌面端**。

### 端口矩阵

| 推理引擎 | 预处理轨 | Server | 端口 |
|----------|----------|--------|------|
| Python 标准 · vpin-backend | **Python 预处理区**（REST :8000） | `vpin-backend` | **8000** |
| Rust 加速 · Arkworks | **Rust 预处理区**（本地 vpin_client） | `ahe-server` (ark) | **8001** |
| Rust 加速 · EC 曲线 | **Rust 预处理区**（本地 vpin_client） | `ahe-server` (ec) | **8002** |

Python 与 Rust **预处理画廊、时间线、选中样本相互独立**；切换推理引擎时 UI 自动切换到对应数据轨。

**REST 预处理 / 模型列表** 始终走 Python 后端 **:8000**（与推理引擎选择无关）。

---

## 3. 前置条件检查

在 `vPIN-main` 根目录执行：

```powershell
# Python 虚拟环境
Test-Path .venv\Scripts\python.exe

# BSGS 表（Rust 客户端必需；优先 fixtures）
Test-Path ..\vpin-platform\tests\fixtures\table.bin
# 或
Test-Path src\Pre_computed_table\table.bin

# 模型权重
Test-Path model_training\outputs\20260622_184254\*.npy

# Rust 二进制（测 Rust 引擎时需要）
Test-Path ..\vpin-platform\target\release\ahe-server.exe
Test-Path ..\vpin-platform\target\release\ahe-cli.exe
```

若 Rust 二进制不存在：

```powershell
cd ..\vpin-platform
cargo build --release -p ahe-server -p ahe-cli
```

若 Python 依赖缺失：

```powershell
cd vPIN-main
.\.venv\Scripts\pip.exe install -e vpin-client
.\.venv\Scripts\pip.exe install -r vpin-backend\requirements.txt
```

---

## 4. 各端启动命令（手动 / 调试）

以下在 **独立终端** 中运行；日常测试优先用 **§3.5 一键脚本**。手动启动时先在仓库根目录点源公共库：

```powershell
cd vPIN-main
. .\scripts\lib\vpin-env.ps1
$ROOT = Get-VpinRepoRoot
Set-VpinDefaultEnv -RepoRoot $ROOT
```

### 4.1 Python 后端（必选，端口 8000）

REST + Python 路线 WS 推理共用。

```powershell
Start-VpinPythonBackend -RepoRoot $ROOT -Detach
# 或前台：Start-VpinPythonBackend -RepoRoot $ROOT
```

健康检查：

```powershell
Invoke-WebRequest http://127.0.0.1:8000/api/v1/health -UseBasicParsing
# 期望 StatusCode 200
```

### 4.2 Rust AHE Server · Ark（端口 8001，测 Rust Ark 时启动）

```powershell
Start-VpinRustServer -RepoRoot $ROOT -Port 8001 -Detach
```

健康检查：

```powershell
Invoke-WebRequest http://127.0.0.1:8001/api/v1/health -UseBasicParsing
```

### 4.3 Rust AHE Server · EC（端口 8002，测 Rust EC 时启动）

```powershell
Start-VpinRustServer -RepoRoot $ROOT -Port 8002 -Detach
```

健康检查：

```powershell
Invoke-WebRequest http://127.0.0.1:8002/api/v1/health -UseBasicParsing
```

### 4.4 Tauri 桌面端（UI + Client 桥）

```powershell
cd (Get-VpinFrontendDir -RepoRoot $ROOT)
npm install   # 首次
npm run tauri dev
```

首次会编译 Rust 壳，耗时 1–3 分钟。

**测试页面**：应用内进入 **模型仓库 → AHE 推理**，或直接打开路由 **`/demo/ahe?model=cnn-mnist-trained`**。

---

## 5. 推荐启动顺序

**推荐**：直接运行 `.\scripts\start-ahe-full.ps1`（自动按序启动并做健康检查）。

手动顺序：

```
1. Python vpin-backend (:8000)     ← 始终需要（REST + Python 推理）
2. ahe-server (:8001 / :8002)      ← 按 UI 所选 Rust 引擎二选一或都启
3. npm run tauri dev               ← UI + 本地 Client 桥
```

测 **三引擎全矩阵** 时，可同时保持 8000 + 8001 + 8002 三个 Server 运行，在 UI 切换引擎即可。

---

## 6. UI 手工 / Agent 测试步骤

1. 确认 Tauri 窗口已打开，进入 `/demo/ahe`。
2. **推理引擎** 下拉选择：`Python` / `Rust Ark` / `Rust EC`。
3. 在对应预处理区选择样本：**官方 MNIST 序号 0–9999**；Python / Rust 均支持 **上传图**（Rust 走 `--image` 本地预处理）。
4. 模型选择：`cnn-mnist-trained`。
5. 点击 **运行 AHE 推理**。
6. 观察：
   - **推理流程时间线** 应随阶段 **动态追加**（非一次性刷出）。
   - **耗时分解** 面板在结束后显示 timing。
   - 预测结果与 label 一致（index 0 通常为 pred=7）。

### 批量推理（UI / CLI）

推理卡片切换 **单图 / 批量**：

| 模式 | 说明 |
|------|------|
| **序号范围** | `start`–`end`（0–9999），与 `--start` / `--limit` 等价 |
| **画廊多选** | 在当前预处理轨（Python/Rust）Ctrl/Shift 多选；上传图走 `image_path` / `upload_id` |

- **并发数**：客户端 asyncio/tokio 并发 WebSocket 会话数（与 server process pool 无关）；建议 ≤ 服务端 CPU 核数。
- **Trace**：`无 / 聚焦项 / 全部`；并发 > 1 时「全部」自动降为「聚焦项」。
- 进度：`stderr` NDJSON → Tauri `ahe-progress` → 批量时间线 + 完成报告。

CLI 冒烟（需 :8000 + Tauri 外可单独验证 Client）：

```powershell
cd vPIN-main
.\.venv\Scripts\python.exe -m vpin_client.cli eval-mnist-ahe --start 1000 --limit 5 --concurrency 2 --progress-ndjson --model cnn-mnist-trained
```

Rust 批量（需对应 ahe-server）：

```powershell
cd vPIN-main
. .\scripts\lib\vpin-env.ps1
$cli = Get-AheCliBin
& $cli eval-mnist-ahe --start 1000 --limit 5 --concurrency 2 --progress-ndjson --crypto-backend ec --model cnn-mnist-trained
```

UI 批量手测：Tauri `/demo/ahe` → 批量 → 范围 `1000–1004`、并发 2；或多选 3 张上传图 → 确认报告 accuracy 与 CLI 一致。

### 无 UI 的 CLI 冒烟（可选，验证 Client–Server）

Python 路线（需 :8000）：

```powershell
cd vPIN-main
.\.venv\Scripts\python.exe scripts\ahe_e2e_smoke.py --model cnn-mnist-trained --mnist-index 0 --json
```

Rust 三栈脚本（需对应 server）：

```powershell
cd vPIN-main
.\scripts\run_ahe_triple_test.ps1 -Limit 10
```

---

## 7. 环境变量汇总

| 变量 | 作用 | 典型值 |
|------|------|--------|
| `VPIN_REPO_ROOT` | 权重、MNIST、table 查找根 | 自动探测为 `vPIN-main` |
| `VPIN_PLATFORM_ROOT` | 同级旧版 Rust 仓库（可选） | 自动探测 `../vpin-platform` |
| `VPIN_BSGS_TABLE` | Rust 客户端 BSGS | 自动：`vpin-client/tests/fixtures/table.bin` 或同级 platform |
| `AHE_SERVER_PORT` | Rust server 监听端口 | `8001` / `8002` |
| `AHE_SERVER_HOST` | 绑定地址 | `127.0.0.1` |
| `PYTHONUNBUFFERED` | Tauri 子进程 progress 即时输出 | `1`（Tauri 已自动设置） |

> Rust 密码栈由 **`ahe-cli --crypto-backend ark|ec`** 指定，**不由** `ahe-server` 环境变量控制。

---

## 8. 注意事项与常见失败

### Python 引擎 UI 推理 `exit 1`（错误信息为空）

Tauri 中选用 **Python 引擎** 点击「运行 AHE 推理」后，若仅显示 `❌ inference failed (exit 1):` 且冒号后无文本，**不一定是同态计算失败**——CLI 同参数可能仍成功。

详见专项报告：**[ahe-python-ui-inference-exit1-错误报告.md](./ahe-python-ui-inference-exit1-错误报告.md)**（现象、后端 WebSocket 日志、CLI 对照命令、根因分层与验证步骤）。

### 端口占用

```powershell
netstat -ano | findstr "LISTENING" | findstr ":8000 :8001 :8002"
```

占用时需结束旧进程后再启。

### PowerShell 与 `cargo`

`cargo` 编译 warning 写入 stderr 时，PowerShell 可能显示红色但 **exit 0 仍表示成功**；以 `Finished` / 健康检查为准。

### BSGS 表

- Rust 路线 **必须** 使用有效的 `table.bin`。
- 推荐：`vpin-platform/tests/fixtures/table.bin`。
- 勿单独依赖 `vPIN-main/src/Pre_computed_table/table.bin`（若损坏会导致 `discrete log not found`）。

### Rust 引擎与数据集

- **官方 MNIST test**：`ahe-cli` 直接读取 `model_training/data/MNIST/raw/t10k-*`（0–9999）；若未下载，自动回退 vpin_client Python 加载。
- **上传图**：`ahe-cli infer --image <path>` 或 UI Rust 预处理区上传后推理。
- **批量评测**：`ahe-cli eval-mnist-ahe --start 0 --limit 100 --crypto-backend ec`（`start+limit ≤ 10000`）。
- Python 引擎支持 upload 样本。

### UI 不阻塞推理

- 推理在 Tauri **`spawn_blocking` 子进程** 中执行。
- UI 通过 **`ahe-progress` 事件** 被动更新；Agent **不要** 在 progress 回调里做长时间同步操作。
- 时间线使用 rAF 批量刷新，测试时以「阶段逐步出现」为通过标准。

### 浏览器模式

`npm run dev`（纯 Vite）仅可测 **预处理预览**；**AHE 推理按钮不可用**，须 `npm run tauri dev`。

### 停止服务

各终端 `Ctrl+C`；或：

```powershell
Get-Process ahe-server -ErrorAction SilentlyContinue | Stop-Process -Force
```

---

## 9. 测试 Agent 最小检查清单

| # | 检查项 | 命令 / 动作 |
|---|--------|-------------|
| 1 | Python 后端存活 | `GET :8000/api/v1/health` → 200 |
| 2 | Rust server（若测） | `GET :8001或8002/api/v1/health` → 200 |
| 3 | Tauri 已启动 | 窗口可见，`/demo/ahe` 可打开 |
| 4 | 单图推理 | 引擎 + index 0 → 时间线动态更新 + PASS |
| 5 | 引擎切换 | 三引擎各跑 1 次（需对应 server 已启） |
| 6 | 批量推理 | 范围 1000–1004、并发 2 → 进度表 + 报告 accuracy |

---

## 10. 相关文件索引

| 用途 | 路径 |
|------|------|
| UI 推理页 | `vpin_frontend/vpin-frontend/src/views/demo/AheDemoView.vue` |
| 引擎配置 | `vpin_frontend/vpin-frontend/src/services/aheClient.js` |
| Tauri 桥 | `vpin_frontend/vpin-frontend/src-tauri/src/lib.rs` |
| 三栈自动化脚本 | `vpin-platform/tools/run_ahe_triple_test.ps1` |
| Python 冒烟 | `vPIN-main/scripts/ahe_e2e_smoke.py` |
| 一键 Python 部署（不含 Rust server） | `vPIN-main/start-ahe.ps1` |

---

*文档版本：与三引擎 UI + 动态时间线实现同步。路径请按本机 `VPIN_REPO_ROOT` 替换。*
