# OVDS / VADS 文档索引

> **更新**：2026-07-12  
> **代码根目录**：[`ovds-server/`](../../ovds-server/)（从 `experiment-reproduction/ovds` 提取的 Python 参考实现）  
> **新手环境**：Docker 见 [`开发环境完整配置指南.md`](../开发环境完整配置指南.md) §4 OVDS

本目录收录 vPIN 平台集成 OVDS 所需的**迁移方案、架构对照与实施指引**。协议密码语义以 `ovds-server` 内文档为准；托管服务 HTTP/JWT 契约以 vPIN 架构文档为准。

---

## 文档列表

| 文档 | 内容 |
|------|------|
| [OVDS-Python到Rust迁移方案](./OVDS-Python到Rust迁移方案.md) | **主方案**：分层设计、密码学库选型、分阶段迁移、测试与集成 |
| [OVDS-逐日迭代实施计划](./OVDS-逐日迭代实施计划.md) | **执行计划**：28 天 × 1 人/天粒度，含文件清单、命令、验收清单 |
| [OVDS-密码学库调研](./OVDS-密码学库调研.md) | Rust 生态库对比、与 Python 依赖映射、风险与备选 |

---

## 关联文档（仓库内）

| 文档 | 路径 |
|------|------|
| VADS 密码协议完整流程 | [`ovds-server/OVDS协议完整流程.md`](../../ovds-server/OVDS协议完整流程.md) |
| 托管服务器技术规格（抽象） | [`ovds-server/document/OVDS数据托管服务器技术文档.md`](../../ovds-server/document/OVDS数据托管服务器技术文档.md) |
| 工程优化（并行上传/验证） | [`ovds-server/document/OVDS工程优化方案.md`](../../ovds-server/document/OVDS工程优化方案.md) |
| mmap 大规模持久化 | [`ovds-server/mmap_design.md`](../../ovds-server/mmap_design.md) |
| vPIN 托管服务器软件架构 | [`docs/architecture/vpin-custody-server-软件架构.md`](../architecture/vpin-custody-server-软件架构.md) |
| vPIN 托管服务器接口规格 | [`docs/architecture/vpin-custody-server-接口规格.md`](../architecture/vpin-custody-server-接口规格.md) |
| 客户端 bridge 契约 | [`docs/api/vpin-client-bridge.md`](../api/vpin-client-bridge.md) |
| 通信端点配置示例 | [`config/client-endpoints.example.json`](../../config/client-endpoints.example.json) |

---

## 当前状态摘要

| 项 | 状态 |
|----|------|
| Python 参考实现 | 已复制至 `ovds-server/`（45 个核心文件） |
| Python 依赖 | `charm-crypto`（BN254）、自研 `RSA-accumulator/` |
| Rust 实现 | **未开始**；`vpin-custody-server` workspace 尚未落地 |
| vpin-console 集成 | `LocalCustodyShim` 占位；`:8003` 端点已配置 |
| 里程碑 | **DataOnly**（`capability_mode = data_only`） |

---

## 决策待办（评审用）

1. **曲线**：保持 BN254（与 Python 一致）还是迁移到 BLS12-381？
2. **Rust workspace 位置**：`ovds-server/crates/` 还是独立 `vpin-custody-server/` + path 依赖？
3. **阶段 0**：是否立即导出 Python 测试向量 fixtures？
4. **AVDS 子系统**：`src/additional/avds_lib.py` 明确不在托管主路径，是否归档忽略？
