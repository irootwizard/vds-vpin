# `statement` — 层计算量陈述（标量 check）

> **定稿：** [`docs/cp-snark-分层证明与RLC设计定稿.md`](../../../../docs/cp-snark-分层证明与RLC设计定稿.md) — 仅 prover 预检；客户端验**按层 π**。

架构草案中的 `statement/`；实现体暂与 `layer_proof/` 共享源文件，本模块提供：

- `layer_id`、`topology`、`ProofCoverageV2`
- `check::*`（原 `layer_proof::verify::*`）
- `ServerLinearProofStack::check_all_scalar`

**SNARK 证明生成/验证：** `prove/`、`verify/`（勿与本目录 `check` 混淆）。

迁移计划：将 `layer_proof/*.rs` 物理迁入本目录并将 `*ProofSpec` 重命名为 `*Witness`。
