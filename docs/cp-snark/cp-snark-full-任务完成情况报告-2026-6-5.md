# cp-snark-full 任务完成情况报告（2026-06-05）

> **⚠️ 设计已修订（2026-06-10）：** [`cp-snark-分层证明与RLC设计定稿.md`](./cp-snark-分层证明与RLC设计定稿.md) — π_mac 合并桩 **非目标**；按层 π、`mac_proof=None` 为预期。  
> **范围：** 路线图 A→D 工程交付快照  
> **架构：** [`cp-snark-full-架构草案.md`](./cp-snark-full-架构草案.md) v0.2  
> **前置：** [`任务完成清单2026-6-4.md`](./任务完成清单2026-6-4.md)

---

## 一、总体结论

| 维度 | 状态 |
|------|------|
| 代码实现（A→D，9 项 to-do） | ✅ 已交付 |
| 单元测试 | ✅ 17/17 通过 |
| 数据资产 | ⚠️ 占位数据；部分字段语义不一致 |
| 端到端 `prove A` → `verify A` | ❌ prove 在标量检查阶段失败 |
| 论文级最优（in-circuit RLC / L1 R1CS） | ❌ 仍为 MVP |

**一句话：** 协议管线与模块骨架已按计划落地，单元测试全部通过；**全链路验收未通过**，当前最大阻塞是 `pool_trace.json` 中 `output_flat` 与 Rust 标量检查（Eq.7）的字段语义不一致。既有 `artifacts/A/protocol.json` 为旧版产物，不含 `model_opening` 等新字段。

---

## 二、自检结果

### 2.1 自动化检查

| 检查项 | 命令 / 方法 | 结果 |
|--------|-------------|------|
| 库单元测试 | `cd src/cp-snark-full && cargo test --lib` | **17 passed, 0 failed** |
| W\* 维度 | 测试 `load_w_star_network_a_has_1219_weights` | ✅ 1219 维 |
| Pedersen opening | `pedersen_model_open_roundtrip` / `pedersen_input_open_roundtrip` | ✅ 往返一致 |
| L1 绑定 | `l1_bindings_network_a` | ✅ 18/178 路 PtMul 直接命中 W\* |
| Setup | `cargo run -- setup A` | ✅ `weights count: 1219` |
| 挑战采样 | `cargo run -- sample-challenge A` | ✅ 输出 γ / γ_add / γ_mult |
| 导出数据目录 | `model_exports/A/` | ✅ 7 个 JSON 齐全 |
| **全链路 Prove** | `cargo run -- prove A` | ❌ panic：pool 标量检查失败 |
| Verify-file（新产物） | `cargo run -- verify-file artifacts/A/protocol.json` | ⏸ 无新 protocol.json，未测 |
| R4 bridge | `vpin-backend` `bridge.py --phase r4` | ⏸ 代码已接线，未端到端实测 |
| 既有 artifacts | `artifacts/A/protocol.json` | ⚠️ 旧版（无 `model_opening` 等 v2 字段） |

### 2.2 Prove 失败根因（已定位）

```
ScalarCheck("EquationFailed { stage: AveragePooling, detail: \"window 0: sum != output_sums\" }")
```

**原因：** `pool_trace.json` 的 `output_flat` 存的是 **缩放后** 值（`sum × inv_k_squared_fp`），而 Rust 的 `verify_pool_eq7_per_cell`（`layer_proof/verify.rs`）期望 **缩放前同态求和**（论文 Eq.7，`JB = Σ JA[window]`）。

| window | 窗口求和 (raw) | `output_flat` | 关系 |
|--------|----------------|---------------|------|
| 0 | 140 | 35840 | 35840 = 140 × 256（缩放一致） |
| 0 检查 | 140 | 35840 | 按 raw sum 检查 → **失败** |

**责任边界：**

- 导出脚本 `python/export_pool_fc_trace_plaintext.py` 将 `output_flat` 写为 `ssum * inv_fp`。
- 加载器 `trace/pool.rs` 将 `output_flat` 直接映射为 `output_sums`。
- 层证明规范 `layer_proof/pool.rs` 明确 `output_sums` 为缩放前求和。

此为 **数据/接口语义不一致**，非核心算法实现错误；修复导出或加载逻辑后应可继续 prove。

### 2.3 单元测试清单（17 项）

| 模块 | 测试名 |
|------|--------|
| `curve` | `embed_matches_witness_network_a_weight_json` 等 |
| `model::load` | `load_w_star_network_a_has_1219_weights`、`load_model_params_a_has_conv_and_pool`、`network_a_conv_matches_server_inline` |
| `model::store` | `default_store_lists_vpin_network_a` |
| `commitment` | `pedersen_model_open_roundtrip`、`pedersen_input_open_roundtrip` |
| `circuit::bind_l1` | `l1_bindings_network_a`、`merkle_root_nonempty` |
| `statement::topology` | `topology_a_has_four_layers` |
| `layer_proof::fc` | `fc_eq8_eq10_toy` |
| `trace::ec` | `load_ec_trace_a_if_present` |

---

## 三、各阶段交付对照

### 阶段 A — 完整 W\* + L1 + Pedersen

| 子项 | 交付物 | 状态 | 说明 |
|------|--------|------|------|
| A.1 | `python/export_full_weights.py` → `full_weights.json`（1219） | ✅ | 无 `.npy` 时用确定性占位 FC；Rust `load_w_star()` + 单元测试 |
| A.2 | `commitment.rs` Pedersen verify + opening | ✅ MVP | `verify_pedersen_open_model/input`；`ProtocolArtifacts` 含 `model_opening` / `input_opening`；verify 优先 opening，无则回退 `weight.json` |
| A.3 | `circuit/bind_l1.rs` + `j_to_wstar_index.json` | ⚠️ 部分 | **prover 标量检查 + Merkle 根**；**未**将 `w_i = witness_para_i` 注入 `point_mult` R1CS |

**L1 索引：** `j_to_wstar_index.json` — 178 路 PtMul 中 **18 路** 直接命中 W\*。

### 阶段 B — 轨迹 + 标量进协议

| 子项 | 交付物 | 状态 | 说明 |
|------|--------|------|------|
| B.1 | `conv_trace.json`（windows + outputs） | ✅ | `Server.py` 录制 + CI 占位 `export_conv_trace_plaintext.py`（16 cells，自洽 MAC） |
| B.2 | `pool_trace.json` / `fc_trace.json` + `trace/build.rs` 全层 | ⚠️ | pool 字段语义错误；`fc_trace.json` 的 `layers` 为空 |
| B.3 | `check_all_scalar` 强制进 prove | ✅ 已实现 | `scalar_check_ok` / `proof_coverage` 升级；当前因 pool 数据触发 abort |

### 阶段 C — π_mac R1CS（MVP）— **已由设计定稿废止合并方案**

> **2026-06-10：** 见 [`cp-snark-分层证明与RLC设计定稿.md`](./cp-snark-分层证明与RLC设计定稿.md)。`mac_rlc` 桩 **不接入**；目标改为 **按层** `π_conv`/`π_pool`/`π_fc`。

| 子项 | 交付物 | 状态 | 说明 |
|------|--------|------|------|
| C.1 | `circuit/mac_rlc/` | ⛔ 停用 | 历史 MVP；`mac_proof=None` |
| — | 按层 in-circuit RLC | ❌ 目标 | 替代合并 `mac_rlc` |
| — | 式 (9) 计算 | ✅ [A] | 已在 `Server.py` `rLCL`/`rLCR` |

**标量层：** `layer_proof` 仅 prover 预检；客户端 **只验 eq9/eq10**（非 eq5+eq9 双检）。

**`rlc_binding_hex`：** 定稿标明 **不作为安全依据**。

### 阶段 D — R4 跨进程 + cm_x

| 子项 | 交付物 | 状态 | 说明 |
|------|--------|------|------|
| D.1 | `protocol/cross_process.rs` + CLI | ✅ 代码就绪 | `sample-challenge`、`prove-with-challenge`、`verify-file`；`verify-file` 要求 `model_opening` |
| D.2 | `input_binding.json` + `public_inputs_for_network` | ✅ | cm_x 绑定真实输入 digest |
| — | `vpin-backend/.../bridge.py` r4 阶段 | ✅ 已接线 | 未端到端实测 |

### 阶段 E — task3 产品化

| 项 | 状态 |
|----|------|
| 模型 HTTPS 接入、截断算法、前端/后端产品化 | ⏸ 按计划后置，本次未做 |

---

## 四、与计划验收的差距

| 计划验收项 | 实际状态 |
|------------|----------|
| A.3 L1 **R1CS** 绑定 `w_i = witness_para_i` | 仅标量检查 + Merkle，非电路级 |
| C.1 式 (9)+(10) **in R1CS** | 式 (9) 桩（1 约束）；无式 (10) |
| A.2 弱化 / 删除 `rlc_binding_hex` | **未做**，仍用于 prove/verify |
| `cargo run -- prove/verify A` 全链路 | **prove 失败**（pool trace） |
| 真实 Server 推理导出 trace | CI 占位脚本 |
| W\* 来自真实 `.npy` | 占位权重（无 `Pre_trained_model`） |
| Pedersen NIZK opening | MVP 明文 opening |
| 阶段 E（task3） | 未启动 |

---

## 五、关键文件索引

```text
src/cp-snark-full/
  python/
    export_full_weights.py
    export_ptmul_wstar_map.py
    export_conv_trace_plaintext.py
    export_pool_fc_trace_plaintext.py   # ← pool 语义问题来源
    export_input_binding.py
  model_exports/A/
    full_weights.json          # 1219 维 W*
    conv_trace.json
    pool_trace.json            # ← 需修复 output_flat 语义
    fc_trace.json
    j_to_wstar_index.json
    input_binding.json
  src/
    commitment.rs              # Pedersen + opening
    circuit/bind_l1.rs         # L1 标量检查
    circuit/mac_rlc/           # π_mac MVP
    prove/pipeline.rs          # 主编排
    verify/pipeline.rs         # 验证（opening 优先）
    protocol/cross_process.rs
    trace/pool.rs              # output_flat → output_sums 映射
    main.rs                    # R4 CLI
  artifacts/{network}/protocol.json

vpin-backend/vpin_backend/crypto/cp_snark/bridge.py   # --phase r4
src/cnn_networks/Server.py                              # 轨迹录制
```

---

## 六、常用验证命令

```bash
cd src/cp-snark-full

# 单元测试
cargo test --lib

# Setup（W* 1219 维 + cm_W / cm_x）
cargo run -- setup A

# 客户端挑战（R4 第一步）
cargo run -- sample-challenge A

# 证明（当前因 pool trace 阻塞）
cargo run -- prove A

# 验证（需含 model_opening 的新 protocol.json）
cargo run -- verify-file artifacts/A/protocol.json

# 重导占位 trace（修 pool 后重跑）
python python/export_pool_fc_trace_plaintext.py --network A
python python/export_conv_trace_plaintext.py --network A
```

---

## 七、建议后续优先事项

1. **修 `pool_trace` 语义**（解除 prove 阻塞）
   - 方案 A：`export_pool_fc_trace_plaintext.py` 的 `output_flat` 改为 raw sum；
   - 方案 B：`trace/pool.rs` 加载时除以 `inv_k_squared_fp` 再填入 `output_sums`。
2. **跑通** `prove A` → `verify` / R4；`proof_coverage` 预期 `ec_plus_scalar_check`（**非** `ec_plus_mac_rlc`）。
3. **按层 π**（设计定稿 §5）：`π_conv` in-circuit 式 (9)；**勿**强化合并 `mac_rlc/build.rs`。
4. **补 FC trace** 与真实 Server 推理导出；有 `.npy` 后重跑 `export_full_weights.py`。
5. **可选增强：** L1 注入 `point_mult` R1CS；Pedersen NIZK opening；删除 `rlc_binding_hex`。

---

## 八、To-do 状态（实现侧）

| ID | 内容 | 标记 |
|----|------|------|
| a1 | W\* 1219 维导出 + `load_w_star` | completed |
| a2 | Pedersen verify + opening | completed |
| a3 | L1 绑定 + j→W\* 映射 | completed（电路级为部分） |
| b1 | conv_trace 导出 | completed |
| b2 | pool/fc trace + build_stack | completed（pool 数据待修） |
| b3 | scalar 强制进 prove | completed |
| c1 | mac_rlc MVP + 接线 | superseded（定稿废止；`mac_proof=None`） |
| d1 | R4 跨进程 γ/prove/verify | completed（未 E2E 实测） |
| d2 | cm_x 输入绑定 | completed |

---

## 九、修订记录

| 日期 | 说明 |
|------|------|
| 2026-06-05 | 初版：A→D 实现自检 + prove 阻塞根因 + 差距表 |
