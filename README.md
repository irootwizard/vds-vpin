# 隐私保护的可验证神经网络推理服务

本仓库包含 [**vPIN** 论文](https://arxiv.org/pdf/2411.07468)（已被 [ACSAC 2024](https://www.acsac.org/2024/) 接收）的完整实现。

### 开发与路线图

**所有阶段排期、计划与改动请以 **[`docs/综合未来工作路线图.md`](docs/综合未来工作路线图.md)** 为准**（含 CP-SNARK M1–M5、设计定稿、Plan A→D 状态）。

CP-SNARK 三线分工摘要：

- **[A]** `Server.py` `rLCL`/`rLCR`：式 (9)(10) **计算侧**（原论文实现路径）
- **[B]** `vPIN_proof_generation`：PtAdd/PtMul EC gadget SNARK（整批）
- **[C]** `cp-snark-full`：协议编排、客户端 γ、按层 π（演进中；`mac_rlc` 桩已停用）

## 代码结构
- **src/cnn_networks/Pre_computed_table/**: 包含用于生成预计算表的 `baby-step-giant-step.py`。
- **src/cnn_networks/**: 包含用于生成图 2 结果的五个不同 CNN 网络的 `Server.py` 和 `Client.py` 文件。
- **src/convolution/**: 包含用于生成图 3 结果的具有不同过滤器大小和输入大小的卷积层的 `Server.py` 和 `Client.py` 文件。
- **src/LeNet/**: 包含用于生成表 2 结果的 LeNet 模型的 `Server.py` 和 `Client.py` 文件。
- **src/proof_generation/vPIN_proof_generation/src/**: 点加/点乘 Spartan 证明（路径 [B]）。
- **src/cp-snark-full/**: CP-SNARK 协议编排（路径 [C]）；设计见上节定稿文档。
- **src/accuracy/**: 包含用于评估准确率的 `train_test_lenet5.py`。

## 前置要求

在运行脚本之前，请确保已安装以下内容：

- **Python 3.8+**
- **Rust** (rustc 1.72.0-nightly)
- **Cargo** (用于 Rust 包管理)
- **必需的 Python 包**：
  - torch: 2.4.0
  - torchvision: 0.19.0
  - torchmetrics: 1.4.1
  - ecdsa: 0.19.0
  - numpy: 2.0.1

## 安装

### 安装 Python：

#### Linux/macOS:

1. **更新包列表并安装 Python 和 pip**：
   ```bash
   sudo apt-get update
   sudo apt-get install -y python3 python3-pip
   ```

2. **安装所需的 Python 包**：
   ```bash
   pip3 install -r requirements.txt
   ```

#### Windows:

1. **下载并安装 Python**：
   - 访问 [python.org](https://www.python.org/downloads/) 下载 Python 3.8 或更高版本
   - 安装时勾选 "Add Python to PATH" 选项

2. **安装所需的 Python 包**：
   ```bash
   pip install -r requirements.txt
   ```

### 安装 Rust 和 Cargo

#### Linux/macOS:

1. **安装 Rust 和 Cargo**：
   ```bash
   curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
   . "$HOME/.cargo/env"
   rustup toolchain install nightly-2023-06-26
   rustup default nightly-2023-06-26  # 全局设置此版本
   rustc --version  # 验证 Rust 编译器版本
   cargo --version  # 验证 Cargo 版本
   ```

#### Windows:

1. **安装 Rust 和 Cargo**：
   - 访问 [rustup.rs](https://rustup.rs/) 下载并运行 rustup-init.exe
   - 按照安装向导完成安装
   - 打开新的命令提示符或 PowerShell，运行：
   ```bash
   rustup toolchain install nightly-2023-06-26
   rustup default nightly-2023-06-26  # 全局设置此版本
   rustc --version  # 验证 Rust 编译器版本
   cargo --version  # 验证 Cargo 版本
   ```

## 配置

### 端口配置

- 默认端口：
  - 35000–35006: 用于单独测试
  - 36000–36004: 用于批量 CNN 实验
  - 37000–37011: 用于批量卷积实验
- **Linux/macOS**: 修改 `script.sh` 的第 29–39 行以自定义这些端口。
- **Windows**: 修改 `script.bat` 的第 12–22 行以自定义这些端口。

### 输出配置

- `QUIET_MODE` 控制脚本的输出详细程度：
  - **QUIET_MODE=1** (默认): 抑制终端输出，将所有输出定向到日志文件。
  - **QUIET_MODE=0**: 启用详细终端输出以进行详细的实时监控。
- **Linux/macOS**: 修改 `script.sh` 第 46 行中的 `QUIET_MODE`。
- **Windows**: 修改 `script.bat` 第 26 行中的 `QUIET_MODE`。

## 如何运行

### 1. 生成预计算表

     *注意：如果您已有预计算表，可以跳过此步骤。*

   要生成表，请运行以下命令：

   **Linux/macOS**:
   ```bash
   ./script.sh -b
   ```

   **Windows**:
   ```bash
   script.bat -b
   ```

   - **资源要求和持续时间**：
     - **RAM**: 约 **3 GB**
     - **时间**: 约 **50 分钟**
     - **存储**: 约 **230 MB**

### 2. 运行实验并生成证明

   选择运行 CNN 网络、LeNet 模型或卷积层。每个脚本在 `vPIN/src/rust_files` 目录中生成见证数据，执行 Rust 代码生成证明，并输出证明时间、验证时间和证明大小。

   - **运行 CNN 网络**：

     **Linux/macOS**:
     ```bash
     ./script.sh -c -A  # 运行 CNN 网络 A 并生成证明 (默认端口: 35000)
     ./script.sh -c -B  # 运行 CNN 网络 B 并生成证明 (默认端口: 35001)
     ./script.sh -c -C  # 运行 CNN 网络 C 并生成证明 (默认端口: 35002)
     ./script.sh -c -D  # 运行 CNN 网络 D 并生成证明 (默认端口: 35003)
     ./script.sh -c -E  # 运行 CNN 网络 E 并生成证明 (默认端口: 35004)

     # 顺序运行所有 CNN 网络：
     ./script.sh -c -t  # 顺序运行所有 CNN 网络并生成证明 (默认端口: 36000-36004)
     ```

     **Windows**:
     ```bash
     script.bat -c -A  # 运行 CNN 网络 A 并生成证明 (默认端口: 35000)
     script.bat -c -B  # 运行 CNN 网络 B 并生成证明 (默认端口: 35001)
     script.bat -c -C  # 运行 CNN 网络 C 并生成证明 (默认端口: 35002)
     script.bat -c -D  # 运行 CNN 网络 D 并生成证明 (默认端口: 35003)
     script.bat -c -E  # 运行 CNN 网络 E 并生成证明 (默认端口: 35004)

     # 顺序运行所有 CNN 网络：
     script.bat -c -t  # 顺序运行所有 CNN 网络并生成证明 (默认端口: 36000-36004)
     ```

     - **资源要求和持续时间**：
       - **RAM**: **3 到 16 GB**，取决于网络类型
       - **时间**: **6 到 75 分钟**，取决于网络类型

   - **运行 LeNet**：

     **Linux/macOS**:
     ```bash
     ./script.sh -l  # 运行 LeNet 模型并生成证明 (默认端口: 35005)
     ```

     **Windows**:
     ```bash
     script.bat -l  # 运行 LeNet 模型并生成证明 (默认端口: 35005)
     ```

     - **资源要求和持续时间**：
       - **RAM**: ~**230 GB**
       - **时间**: ~**4 小时**

   - **运行卷积层**：

     **Linux/macOS**:
     ```bash
     ./script.sh -d < filter_size: 3|5|7 > < input_size: 32|64|128|256 > | -d -t

     # 顺序运行所有卷积实验：
     ./script.sh -d -t  # 顺序运行所有卷积实验并生成证明 (默认端口: 37000-37011)
     ```

     **Windows**:
     ```bash
     script.bat -d < filter_size: 3|5|7 > < input_size: 32|64|128|256 > | -d -t

     # 顺序运行所有卷积实验：
     script.bat -d -t  # 顺序运行所有卷积实验并生成证明 (默认端口: 37000-37011)
     ```

     例如：
     ```bash
     # Linux/macOS
     ./script.sh -d 3 32  # 示例：过滤器大小 3，输入大小 32x32 (默认端口: 35006)
     ./script.sh -d 5 64  # 示例：过滤器大小 5，输入大小 64x64 (默认端口: 35006)

     # Windows
     script.bat -d 3 32  # 示例：过滤器大小 3，输入大小 32x32 (默认端口: 35006)
     script.bat -d 5 64  # 示例：过滤器大小 5，输入大小 64x64 (默认端口: 35006)
     ```

     - **资源要求和持续时间**：
       - **RAM**: **2 到 5 GB**，取决于输入大小和过滤器大小
       - **时间**: **2 分钟到 4 小时**，取决于输入大小和过滤器大小

### 3. 检查准确率

   要评估准确率，可以运行：

   **Linux/macOS**:
   ```bash
   ./script.sh -a
   ```

   **Windows**:
   ```bash
   script.bat -a
   ```

   - **资源要求和持续时间**：
     - **RAM**: < **1GB**
     - **时间**: ~**50 分钟**

### 详细输出模式

   要查看详细的实时输出，可以使用 `-v` 或 `--verbose` 参数：

   **Linux/macOS**:
   ```bash
   ./script.sh -v -c -A
   ```

   **Windows**:
   ```bash
   script.bat -v -c -A
   ```

## 平台支持

本项目支持以下平台：

- ✅ **Linux** (使用 `script.sh`)
- ✅ **macOS** (使用 `script.sh`)
- ✅ **Windows** (使用 `script.bat`)

所有核心功能在三个平台上均可正常工作。代码已针对 Windows 进行了兼容性处理（例如，在 `Server.py` 中处理了 Windows 的 localhost 绑定问题）。

## 工件文档

有关如何复现论文中呈现结果的详细说明，请参阅我们的 [工件文档](/Documents/ACSAC_2024_Artifact_Documentation_Privacy-Preserving_Verifiable_Neural_Network_Inference_Service.pdf)。

## 致谢

本项目使用位于 `src/proof_generation/spartan/` 目录中的 [Spartan 仓库](https://github.com/microsoft/Spartan) 作为库来为我们的见证数据生成证明。我们已修改了 Spartan 仓库中的某些文件以将其与 vPIN 框架集成。我们向 Spartan 项目的贡献者表示诚挚的感谢，他们为我们构建证明生成系统提供了坚实的基础。

此外，我们感谢 [ezDPS 实现](https://github.com/vt-asaplab/ezDPS) 提供了位于 `src/proof_generation/vPIN_proof_generation/src/` 的 `commitment_test.rs` 文件。该文件对于在我们的项目中创建辅助见证数据的承诺至关重要。

## 引用

如果您使用本仓库或基于我们的工作构建，我们感谢您使用以下 BibTeX 条目引用我们的论文：

```bibtex
@inproceedings{vPIN2024,
  title={Privacy-Preserving Verifiable Neural Network Inference Service},
  author={Riasi, Arman and Guajardo, Jorge and Hoang, Thang},
  booktitle={2024 Annual Computer Security Applications Conference (ACSAC)},
  pages={683--698},
  year={2024},
  organization={IEEE}
}
```

