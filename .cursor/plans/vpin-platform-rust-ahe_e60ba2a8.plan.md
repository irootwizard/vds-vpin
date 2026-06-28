---
name: vpin-platform-rust-ahe
overview: 重写一份面向新仓 `vpin-platform` 的 AHE Rust 迁移计划：只以现有 Python AHE 为金标准，不沿用废弃的 `ahe_全量_rust_迁移` 计划主体；首期聚焦 Network A，同态推理结果以 bit-exact 和 batch acc 对齐验收。
todos:
  - id: capture-baseline
    content: 导出 Python 单图与批量 baseline fixtures，固定 Network A 权重和 MNIST 样本
    status: completed
  - id: init-vpin-platform
    content: 初始化 vpin-platform Rust workspace、配置、crate 骨架和 health check
    status: completed
  - id: convert-bsgs
    content: 实现 table.pickle 到 BSG1 table.bin 转换，处理 identity 并完成随机校验
    status: completed
  - id: spike-e2-arkworks
    content: 用 arkworks 定义 E2 曲线并验证点运算与 Python ecdsa parity
    status: completed
  - id: port-crypto-codec
    content: 迁移 ElGamal、fixed-point、BSGS giant-step 和同态基础算子
    status: completed
  - id: port-network-a
    content: 迁移 Network A conv/pool/fc、client_action 与 engine phase 状态机
    status: completed
  - id: implement-rust-e2e
    content: 实现 Rust WS 协议、ahe-server、ahe-client 和单图 bit-exact 推理
    status: completed
  - id: verify-batch-acc
    content: 实现批量 CLI 并完成逐样本 bit-exact 与 acc 对齐验收
    status: completed
isProject: true
---

# vpin-platform AHE Rust 迁移计划

## 范围与原则
- 新建独立仓库/目录 `vpin-platform`，不使用废弃计划中的 `vpin-ahe-platform` 命名。
- 不修改现有 `vPIN-main` 源码；旧仓只作为数据来源、Python 金标准和对照测试入口。
- 首期只迁移 `Network A (cnn-mnist-trained)` 的 AHE 同态推理链路；暂不做 compact、Network B、LeNet、CP-SNARK 和现有 Tauri 前端替换。
- 验收采用 bit-exact：同一 MNIST 输入下，Rust 与 Python 的 `prediction`、`logits`、逐样本 batch 结果完全一致。

## 证据前置规则
- 对 BSGS 表格式、E2 曲线库、wire 编码、模型权重契约等架构性问题，先做只读核对，再进入实现。
- 一手依据优先级：源码热路径、实际文件元数据、官方 crate 文档、运行输出。
- 每个已确认结论要沉淀到 `vpin-platform` 的 README、fixtures 或测试中，避免实现阶段重复猜测。

## Python 金标准来源
- AHE 客户端协议与本地解密/重加密：[`vpin-client/vpin_client/protocol/ws_ahe_client.py`](vpin-client/vpin_client/protocol/ws_ahe_client.py)
- E2 曲线、ElGamal、BSGS、定点编码：[`vpin-client/vpin_client/crypto/ahe/curve.py`](vpin-client/vpin_client/crypto/ahe/curve.py)、[`vpin-client/vpin_client/crypto/ahe/codec.py`](vpin-client/vpin_client/crypto/ahe/codec.py)
- 服务端 WS 与状态机：[`vpin-backend/vpin_backend/api/routes/session.py`](vpin-backend/vpin_backend/api/routes/session.py)、[`vpin-backend/vpin_backend/inference/ahe_engine.py`](vpin-backend/vpin_backend/inference/ahe_engine.py)
- Network A 同态算子：[`vpin-backend/vpin_backend/inference/homomorphic_network_a.py`](vpin-backend/vpin_backend/inference/homomorphic_network_a.py)
- topology 与截断：[`vpin-backend/vpin_backend/crypto/ahe/topology.py`](vpin-backend/vpin_backend/crypto/ahe/topology.py)
- batch acc 对照：[`vpin-client/vpin_client/pipeline/batch.py`](vpin-client/vpin_client/pipeline/batch.py)
- 回归入口：[`scripts/ahe_e2e_smoke.py`](scripts/ahe_e2e_smoke.py)

## 目标结构
```text
vpin-platform/
├── Cargo.toml
├── rust-toolchain.toml
├── README.md
├── config/
│   └── default.toml
├── crates/
│   ├── ahe-crypto-e2/        # E2 曲线、点运算、keygen
│   ├── ahe-codec/            # ElGamal、定点、BSGS、ciphertext tensor
│   ├── ahe-protocol/         # P0-P3 消息、ahe-v1 binary wire、chunk
│   ├── ahe-model-bundle/     # registry、npy 权重、Network A topology
│   ├── ahe-homomorphic/      # conv/pool/fc 密文算子
│   ├── ahe-engine/           # phase 状态机与 TruncateRequest
│   └── ahe-client/           # 本地解密、client_action、WS 会话
├── apps/
│   ├── ahe-server/           # axum WS server，默认 :8001
│   └── ahe-cli/              # 单图推理与 batch acc CLI
├── tools/
│   ├── bsgs-convert/         # table.pickle -> table.bin
│   └── parity-export/        # Python baseline fixtures
└── tests/
    └── fixtures/
```

## 密码学库选型
- Python 当前热路径使用 `ecdsa.ellipticcurve.CurveFp/Point` 做自定义 E2 曲线点加、标量乘和指数 ElGamal，不使用 ECDSA 签名。
- Rust 首选 `ark-ff + ark-ec`：用 `MontConfig` 定义 `Fq/Fr`，用 `CurveConfig + SWCurveConfig` 定义 E2 的 `a/b/G/order`。
- `elliptic-curve` 本身有 `Curve`、`PrimeCurve`、`CurveArithmetic` 等抽象，但它是 trait 基座，不是动态传入 `p/a/b/G/order` 即可运行的库。
- RustCrypto 方向的备选是 `primeorder + elliptic-curve`，仅当 `arkworks` spike 遇到不可接受阻塞时启用。
- `num-bigint` 或 `rug` 只用于 spike/fixtures 对照，不进入最终热路径。

## BSGS 迁移结论
- 已确认本机 `src/Pre_computed_table/table.pickle` 存在，约 `239,706,967` bytes。
- pickle 内容是 `dict`，条目数 `3,200,000`，格式为 `(x, y) -> j`，可直接转换为 Rust 使用的二进制表。
- 第 0 项是 Python `ecdsa` 的无穷远点表示：`(None, None) -> 0`。转换器必须显式编码 identity，例如写为 `x=0, y=0, j=0`，Rust 读取时按 identity 处理，并测试 `(0,0)` 不与合法 E2 点冲突。
- `table.bin` 建议格式：magic `BSG1`、`m=3200000`、`entry_count`，随后按 `j` 升序写 `x[32] BE`、`y[32] BE`、`j u32 LE`。

## 分阶段实施
1. **Phase 0：基线与脚手架**
   - 初始化 `vpin-platform` workspace、配置、空 crate 和 `ahe-server` health check。
   - 导出 Python baseline fixtures：固定 MNIST index、输入定点、中间 phase、最终 logits/prediction、batch 统计。
   - 实现 `bsgs-convert`，完成 identity 特例和 1k 随机回读校验。
   - 完成 `arkworks` E2 spike：`G*0`、`G*1`、`sk*G`、点加/点乘与 Python 向量一致。
2. **Phase 1：密码学内核**
   - 实现 `ahe-crypto-e2` 与 `ahe-codec`：keygen、encrypt/decrypt、homomorphic add/scalar mul、fixed-point、BSGS giant-step 双分支。
   - 验收：ElGamal roundtrip、负数 BSGS、固定向量 parity 全部通过。
3. **Phase 2：Network A 算子与状态机**
   - 实现 conv、pool、flatten、fc1、fc2 密文算子。
   - 实现 client-side `relu`、`shift`、`relu_then_shift`、`relu_only`，严格对齐 26/32 位截断语义。
   - 验收：不走 WS 的本地 engine 对齐 Python phase 输出。
4. **Phase 3：协议与服务**
   - 实现 `ahe-protocol` P0-P3 消息和 `ahe-v1` binary wire。
   - 实现 `apps/ahe-server` 和 `ahe-client`，完成 Rust client/server 单图闭环。
   - 验收：单图 `logit_max_diff=0`，prediction 一致。
5. **Phase 4：批量 acc 验证**
   - 实现 `ahe-cli infer` 与 `ahe-cli eval-mnist-ahe --limit --concurrency`。
   - 生成 Rust batch report，结构对齐 Python `reports/batch_*.json`。
   - 验收：固定样本逐图 bit-exact，整批 acc 与 Python 完全一致。

## 风险控制
- 曲线库选型风险：Phase 0 先用小向量验证 `arkworks`，失败才切换 `primeorder`，不在后期重写。
- BSGS 风险：优先完成转换器、identity 处理、负数 giant-step 和随机回读测试。
- 定点风险：把 `shift_bits=26/32`、`relu_then_shift`、`floor_divide` 行为写成独立测试。
- wire 风险：Rust 内部优先使用 `ahe-v1`；Python pickle wire 只作为 golden/transcode 调试来源，不强制 Rust 生产路径解析 pickle。

## 验收出口
- `cargo test --workspace` 通过。
- `ahe-cli infer --model cnn-mnist-trained --mnist-index 0` 与 Python baseline bit-exact。
- `ahe-cli eval-mnist-ahe --limit 10 --concurrency 4` 与 Python batch acc 和逐样本结果一致。
- `vPIN-main` 源码无改动，所有新实现与报告保留在 `vpin-platform`。