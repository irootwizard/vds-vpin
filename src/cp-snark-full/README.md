# cp-snark-full

vPIN CP-SNARK 协议编排（[C] 路径）。

> **总路线图：** [`docs/综合未来工作路线图.md`](../../docs/综合未来工作路线图.md)（M1–M5、阶段排期）  
> **架构草案：** [`docs/cp-snark-full-架构草案.md`](../../docs/cp-snark-full-架构草案.md)  
> **式 (9)(10) 计算侧** 见 `cnn_networks/Server.py`（[A]）；**EC gadget 证明** 见 `vPIN_proof_generation`（[B]）。  
> **`circuit/mac_rlc`：** 桩已停用（`mac_proof=None`），勿作安全 π。

## 模块地图（已实现 M1）

| 目录 | 职责 |
|------|------|
| `commit/` | $\mathsf{cm}_W$、$\mathsf{cm}_x$、transcript（源在 `commitment.rs`） |
| `model/` | 静态 **W** + **`ModelStore`**（`model_store/` JSON 注册表） |
| `trace/` | 同态 JSON + `conv_trace.json` → `build_linear_stack` |
| `statement/` | 层 MAC/RLC **标量 check**（`check::*`；实现体在 `layer_proof/`） |
| `circuit/` | `ec/`（PtAdd/PtMul）、`mac_rlc/`（**已停用桩**，见设计定稿） |
| `prove/` | `prover_pipeline`、`prove_ec_batch` |
| `verify/` | `verifier_pipeline` |
| `protocol/` | `ProtocolArtifacts` v1/v2、`save/load` |

## 常用命令

```bash
cargo run -- full A
cargo run -- prove A
cargo run -- verify A
cargo test
```

## 导出文件

```text
model_store/index.json                    # task3 模型注册索引
model_store/models/{id}/model_export.json # 权重（简单 JSON 填充）
model_exports/{network}/conv_trace.json   # Python convertFormatForRust_conv
model_exports/{network}/model_export.json # 按 network 字母的快捷路径
artifacts/{network}/protocol.json         # version 2 含 prove_timing、scalar_check_ok
```

## 文档

- [`docs/cp-snark-full-任务完成情况报告-2026-6-5.md`](../../docs/cp-snark-full-任务完成情况报告-2026-6-5.md) — A→D 自检与差距
- [`src/layer_proof/README.md`](src/layer_proof/README.md)
- [`src/model/README.md`](src/model/README.md)
- [`docs/model-trace-接口与卷积windows方案.md`](../../docs/model-trace-接口与卷积windows方案.md)
