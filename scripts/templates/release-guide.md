# vPIN Console 运行指南

发布包目录：`release/{{BUNDLE_NAME}}/`（约 0.5 GB，**不含**仓库 `docs/` 文档）

## 系统要求（目标 Windows 设备）

| 依赖 | 说明 |
|------|------|
| Windows 10/11 **x64** | 不支持 32 位系统 |
| [WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/) | 桌面 UI 必需；Win11 通常已预装，白屏时需安装 Evergreen Bootstrapper |
| [VC++ 2015–2022 x64](https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist) | `ahe-cli` / `ahe-server` 依赖 `VCRUNTIME140.dll` |
| 磁盘空间 | ≥ 1 GB 可用空间 |
| 网络 | **离线可用**（推理、数据集、模型目录均内置，无需联网） |

## 目录结构

| 路径 | 说明 |
|------|------|
| `vpin-console.exe` | 桌面端主程序（须为 `npm run tauri build` 产物） |
| `start-vpin-console.ps1` | 推荐启动脚本（PowerShell，设置环境变量） |
| `start-vpin-console.bat` | 备用启动（双击，无需改执行策略） |
| `bin/ahe-cli.exe` | Rust AHE 客户端 |
| `bin/ahe-server.exe` | Rust AHE 服务端（桌面端可自动拉起 :8001） |
| `bin/cp-snark-full.exe` | 证明 CLI（可选，需 Python 后端配合） |
| `data/weights/cnn-mnist-trained/` | Network A 模型权重（4×npy + 配置） |
| `data/bsgs/table.bin` | Rust BSGS 表（~208 MB，必需） |
| `data/bsgs/table.pickle` | Python BSGS 表（可选） |
| `model_training/data/MNIST/raw/` | MNIST 训练 + 测试 IDX（8 个文件） |
| `config/models-registry.json` | 离线模型目录 |
| `config/datasets-catalog.json` | 离线数据集目录 |
| `config/release-baseline.manifest.json` | 发布包文件清单（校验用） |
| `installer/` | NSIS/MSI 安装包（完整构建后生成） |

## 部署到其他 Windows 设备

1. 将整个文件夹 `{{BUNDLE_NAME}}` 复制到目标机（U 盘、内网共享、zip 均可）。
2. **不要**只复制 `vpin-console.exe`——必须保持目录结构完整。
3. 目标机安装 WebView2（若尚未安装）和 VC++ x64 运行库（若 `ahe-cli` 无法启动）。
4. 启动方式（任选其一）：
   - 双击 `start-vpin-console.bat`
   - 或在 PowerShell 中：`.\start-vpin-console.ps1`
5. 首次启动后状态栏预期：
   - **Backend**：未启用（发布包不含 Python :8000，正常）
   - **ahe-server**：已连接（绿色）
   - **Bridge**：就绪（绿色）

## 启动脚本设置的环境变量

- `VPIN_REPO_ROOT` → 发布包根目录
- `VPIN_BSGS_TABLE` → `data\bsgs\table.bin`
- `VPIN_WEIGHTS_DIR` → `data\weights\cnn-mnist-trained`

> 若直接双击 `vpin-console.exe`（不用启动脚本），程序会尝试从 exe 旁 `data\bsgs\table.bin` 自动识别发布包根目录，但**仍推荐**使用启动脚本。

## 功能范围

| 功能 | 发布包内 | 说明 |
|------|----------|------|
| Rust AHE 推理（MNIST 序号 / 上传图片） | 支持 | 无需 Python |
| 模型仓库（cnn-mnist-trained） | 支持 | 读取 `config/models-registry.json` |
| 数据集目录（MNIST / 本地上传） | 支持 | 读取 `config/datasets-catalog.json` |
| 桌面 UI + 自动启动 ahe-server | 支持 | |
| Python 后端 :8000 | **不含** | 证明 API 等需开发环境 |
| CP-SNARK 证明全流程 | **部分** | 含 `cp-snark-full.exe` 时需 Python 后端 |

## 重新打包（开发者）

在仓库根目录执行：

```powershell
.\scripts\build-release.ps1
```

输出至 `release/vpin-console_0.1.0_win64/`。打包结束会自动运行 `check-release.ps1`。

## 校验发布包

```powershell
.\scripts\check-release.ps1
```

校验项包括：清单内全部必需文件、MNIST 训练/测试集、权重、BSGS `table.bin` 哈希、无文档泄漏、冒烟测试（preprocess + infer）。

## 常见问题

**白屏**：安装 [WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/)。

**ahe-cli / ahe-server 无法启动**：安装 [VC++ Redistributable x64](https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist)。

**无法访问 localhost:1420**：`vpin-console.exe` 不是完整 Tauri 构建产物，请重新执行 `build-release.ps1`。

**BSGS / 权重找不到**：用 `start-vpin-console.ps1` 或 `.bat` 启动，或手动设置上述三个环境变量。

**MNIST 推理失败**：确认 `model_training\data\MNIST\raw\` 下 8 个 idx 文件完整（已随包分发）。

**端口 8001 占用**：任务管理器结束其他 `ahe-server.exe` 后重试。

**Backend 显示未启用**：正常现象，发布包独立运行不依赖 Python 后端。
