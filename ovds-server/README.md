# OVDS Docker 环境

可复现的 **charm-crypto + PBC** 环境，替代手工 WSL `crypto-libs` 配置。

## 前置

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) 已启动

## 构建

```powershell
cd ovds-server
docker build -t vpin/ovds-reference:latest .
```

## 测试

### 1. Charm 烟雾测试（默认，约数秒）

```powershell
docker run --rm vpin/ovds-reference:latest
# 或
.\scripts\run_docker_tests.ps1
```

期望输出：`charm BN254 ok`

### 2. 完整 VADS 协议测试（含 RSA setup，约数分钟）

```powershell
docker run --rm vpin/ovds-reference:latest python src/test/test_all.py
# 或
.\scripts\run_docker_tests.ps1 -Protocol
```

## 镜像内容

| 层 | 说明 |
|----|------|
| PBC 0.5.14 | 从 Stanford 源码编译至 `/usr/local` |
| Charm | GitHub `JHUISI/charm` dev 分支源码编译（PyPI 仅 0.43） |
| OVDS | `src/`、`RSA-accumulator/`（Python 部分） |

## 与本地 `.venv` 的关系

根目录 `.venv` **不含 charm**；OVDS 协议开发与测试请使用本 Docker 镜像。
