# vpin-backend

vPIN 产品化后端（Task2）：在**不修改** `src/cnn_networks` 等实验代码的前提下，提供 HTTP API、AHE 密码学模块与 CP-SNARK 桥接。

## 架构文档

- **RLC / 按层 π / γ 定稿：** [docs/cp-snark-分层证明与RLC设计定稿.md](../docs/cp-snark-分层证明与RLC设计定稿.md)
- 后端架构：[docs/vpin-backend-客户端服务器架构设计.md](../docs/vpin-backend-客户端服务器架构设计.md)

## 快速开始

```bash
# 在仓库根目录
pip install -r vpin-backend/requirements.txt

# 开发模式（HTTP）
cd vpin-backend
python -m vpin_backend.main

# 或
uvicorn vpin_backend.api.app:create_app --factory --reload --host 127.0.0.1 --port 8000
```

- 健康检查：<http://127.0.0.1:8000/api/v1/health>
- AHE 曲线自检：<http://127.0.0.1:8000/api/v1/crypto/ahe/self-test>
- CP-SNARK 状态：<http://127.0.0.1:8000/api/v1/crypto/cp-snark/status>

## 服务端 CLI（注册预训练模型）

```bash
python -m vpin_backend.cli.server_admin register --network A --name "CNN MNIST A"
python -m vpin_backend.cli.server_admin list
```

## CP-SNARK

需已安装 Rust nightly（见根目录 README）。桥接调用 `src/cp-snark-full`：

```bash
python -m vpin_backend.crypto.cp_snark.bridge --network A --phase full
```

## 环境变量

| 变量 | 默认 |
|------|------|
| `VPIN_REPO_ROOT` | 自动探测（含 `src/cnn_networks` 的目录） |
| `VPIN_BSGS_TABLE` | `{repo}/src/Pre_computed_table/table.pickle` |
| `VPIN_DATA_DIR` | `{repo}/vpin-backend/data` |
