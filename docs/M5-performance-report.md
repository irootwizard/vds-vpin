# M5 / Phase Z 性能报告

> **覆盖范围**：vPIN Phase Z（Z.0–Z.9）证明阶段的测量结果。toy 网络数字为
> 单元/集成测试每次刷新到 `vpin-backend/tests/perf/Z-*.json`，Network A 的
> EC 证明数字来自 `VPIN_EC_REAL_PROVE=1` 的一次手动 `prove-with-challenge`
> 运行（见 §Z.9）。

| 指标定义 | 含义 |
|----------|------|
| `prove_ms` / `prove_layers_ms` | 证明侧总耗时 |
| `verify_ms` / `verify_total_ms` | 验证侧总耗时 |
| `proof_bytes` | 序列化 SubCircuitProof / SNARK 字节数（不含 cm_W、challenge） |
| `cm_w_*` | Spartan PC 多项式承诺度量（Z.5/Z.9） |

---

## Z.0–Z.4：toy 三层 R1CS + L1 绑定

| 任务 | prove_ms | verify_ms | proof_bytes | 备注 |
|------|----------|-----------|-------------|------|
| **Z-1** conv MAC 式(9) | 331 | 131 | 23 336 | `tests/perf/Z-1.json` |
| **Z-2** pool sum 式(7) | 80 | 40 | 9 400 | `tests/perf/Z-2.json` |
| **Z-3** fc MAC 式(10) + bias | 98 | 59 | 11 976 | `tests/perf/Z-3.json` |
| **Z-4** L1 绑定（三层串行） | 398 | 209 | 44 712 | `tests/perf/Z-4.json` |

---

## Z.5：`cps_comm_w_star` Spartan PC

| 任务 | 输入维度 | `prove_ms` | `commitment_bytes` | 输出形状 |
|------|----------|-----------|--------------------|----------|
| Z-5 toy（`|W*|=13`） | padded_len = 16 → ell=4 → L_size=4 | 3 | 128 | 4 × CompressedRistretto |

---

## Z.6：toy CPS.Ver E2E

| 任务 | prove_ms | verify_ms | proof_bytes | 备注 |
|------|----------|-----------|-------------|------|
| Z-6 | 579 | 228 | 44 712 | cm_W (128 B) 单独通过 `cm_w_bytes` 字段记录 |

---

## Z.7：vpin-client P0–P6（Python 端）

| 任务 | verify_ms | pi_total_bytes |
|------|-----------|----------------|
| Z-7 | <1 | 44 712 |

> Python 端只做 M1 RLC（eq9/eq7/eq10） + L1 binding + cm_W catalog
> 对比，单次会话开销低于 1 ms；SNARK 校验仍委托给 Rust。

---

## Z.8：EC + layer 统一 transcript

| 任务 | prove_ms | verify_ms | proof_bytes | transcript 绑定 |
|------|----------|-----------|-------------|----------------|
| Z-8 | 544 | 214 | 44 712 | `cps_cm_w → pedersen_cm_w → cm_x → challenge → sub_circuit` |

> Z.8 与 Z.6 相比，证明侧多了 cm_W (Spartan PC) 的额外 `append_message`
> 调用；本次 JSON 快照中 Z.8 prove 比 Z.6 少 35 ms，属于单次 dev build
> 测量波动，不能据此宣称优化。

---

## Z.9：Network A 迁移

### Z.9.A — cm_W (Spartan PC) over `W*`（1219 维）

| 指标 | 数值 |
|------|------|
| `num_weights` | 1 219 |
| `padded_len` | 2 048 (`ell = 11`) |
| `cm_w_ms` | **44 ms** |
| `poly_comm_count` | 32（L_size = 2^5） |
| `cm_w_hex` | `6c8706f65ba2cfd9f2759a7c5d9accef101ef590ce7c977da23bde0bb078c260` |

> `tests/perf/Z-9.json`；测试 `network_a_z9::z9_network_a_cps_comm_w_star_smoke_and_perf`。
> 该度量为**确定性**（`cps_comm_w_star` 内部 `random_tape: None`，多次运
> 行字节一致）。

### Z.9.B — EC SNARK（PtAdd 2144 + PtMul 178）

| 指标 | 数值 | 来源 |
|------|------|------|
| 调用 | `VPIN_EC_REAL_PROVE=1 vpin-server-crypto prove-with-challenge A artifacts/A/client_challenge.json artifacts/A/setup.json` | CLI |
| 总耗时（`prove_time_ms`） | **475 846 ms ≈ 7 m 55 s** | `artifacts/A/protocol.json:523967` |
| `prove_timing.check_scalar_ms` | 0 | 仅 EC 路径，无 client scalar check |
| `prove_timing.prove_mac_ms` | 0 | M5 in-circuit MAC 尚未启用 |
| `prove_timing.prove_ec_ms` | 0 | 当前 pipeline.rs 仅记录 `total_ms` |
| 输出 artifact `protocol.json` | 5.97 MB（含序列化 EC π） | `artifacts/A/protocol.json` |
| `proof_coverage` | `ec_gadget_only` | 因 M5 MAC π 暂未联通 |

> **诚实边界**：该耗时仅包含 PtAdd / PtMul Spartan SNARK 端到端；当前
> Network A pipeline 还未将 Phase Z 的 Spartan PC cm_W、layer π_conv /
> π_pool / π_fc、L1 binding 串入此 SNARK transcript。Z.11 的边界见
> `docs/cps-honesty-boundary.md`。
>
> **未触发停止条件**：耗时 7 m 55 s < 30 min 阈值（plan §0.6），故 Z.9
> 不写 issue 阻塞，继续推进 Z.10 / Z.11。

### Z.9.C — 待续工作

| 项 | 状态 | 跟进位置 |
|----|------|----------|
| `cps_comm_w_star` × Network A pipeline 接入 | **未接入**：`prove_with_challenge` 当前不调用 `cps_comm_w_star`，需要把 Z.6 的 `prove_toy_cps` 一般化 | `prove/pipeline.rs::prove_with_challenge` |
| layer π_conv/π_pool/π_fc × Network A | **未实现**：Network A 的 R1CS 层在 `vpin-server-crypto/src/circuit/layer/` 仅有 toy；Network A 的对齐版本待 M5.* | `circuit/layer/` |
| L1 binding × Network A | **未实现**：`bind_l1.rs::ToyWeightLayout` 是 toy 专用；Network A 需要 `j_to_wstar_index.json` 驱动的通用 layout | `circuit/bind_l1.rs` + `model_exports/A/j_to_wstar_index.json` |
| `proof_coverage` 推进到 `ec_plus_layer_pi_with_model_binding` | 仅 toy 可宣称；Network A 尚未统一 cm_W、layer π 与 L1 binding | `docs/cps-honesty-boundary.md` |

---

## 测量环境

| 项 | 值 |
|----|----|
| 平台 | win32 10.0.26200 |
| 工具链 | `cargo` dev build（含 `feature = multicore`：`cp-snark-full`；vpin-server-crypto 无 multicore） |
| 机器 | 单次手动测量，未做多次平均 |
| 日期 | 2026-06-10 |

---

## 更新日志

| 日期 | 变更 |
|------|------|
| 2026-06-10 | Z.11 刷新：按 `tests/perf/Z-*.json` 聚合 Z-1..Z-9，并链接 honesty boundary |
