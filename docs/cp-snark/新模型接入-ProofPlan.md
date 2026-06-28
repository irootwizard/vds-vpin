# 新模型接入 — ProofPlan 清单

在 B′ + paper_proof 主路径下，接入新 CNN/拓扑**不必修改** Spartan EC gadget 或 CPS 核心；只需提供 run 目录产物并注册 `ProofPlan`。

## 1. 实现拓扑与 schedule

1. 在 `vpin_backend/crypto/ahe/topology.py`（或等价模块）定义 `NetworkTopology`：层数、k、pool、padding、ElGamal 分支等。
2. 实现 `derive_ec_schedule(topology, mode) -> EcWitnessSchedule`：每层 `pt_mul` / `pt_add` 及全局 `total_*`、层区间 `[pt_mul_start, pt_mul_end)`。
3. 参考 Network A：[`model_training/network_a/ec_witness_schedule.py`](../../model_training/network_a/ec_witness_schedule.py)。

## 2. 导出 proof_artifacts

一次训练 run 目录下应包含：

```text
{run_dir}/proof_artifacts/
  ec_witness_schedule.json
  ec_witness/
    pointMult/weight.json
    pointMult/point_mult_px_byte.json
    pointMult/point_mult_py_byte.json
    pointAdd/point_add_*.json
    manifest.json
  conv_trace.json
  pool_trace.json
  fc_trace.json
  full_weights.json
```

推荐从同态推理采集 EC 坐标（Network A 目标：`homomorphic_network_a`）。迁移期可用 `export_proof_artifacts.py --from-legacy` **仅作调试**，不可作为生产验收。

γ/γ′ 对齐：导出后对 FC 段 PtMul 乘数调用 `RlcChallengeAdapter`（[`vpin_backend/proof/rlc_adapter.py`](../../vpin-backend/vpin_backend/proof/rlc_adapter.py)）。

## 3. 注册 ProofPlan

Python（服务端 prove API）：

```python
from pathlib import Path
from vpin_backend.proof.registry import register_proof_plan, load_proof_plan

register_proof_plan("my-model-id", Path("model_training/outputs/my_run"), "paper_proof")
plan = load_proof_plan("my-model-id")
plan.activate_witness()  # 设置 VPIN_RUN_DIR / VPIN_EC_WITNESS_ROOT
```

Rust prove 侧等价：`ProofPlan::from_run_dir(run_dir, model_id, "paper_proof")` + `plan.activate_witness()`。

## 4. L1 绑定布局

在 `ProofPlan.binding_layout`（或 `ptmul_scalar_sources.json` 镜像）中声明：

- 直接叶槽（conv 权重索引 → W* 下标）
- RLC 列槽（FC 层：γ′ 下 W* 线性组合，见 [`模型参数绑定计算轨迹-数学推导.md`](模型参数绑定计算轨迹-数学推导.md)）

`bind_l1.rs` 槽位数必须等于 `schedule.total_pt_mul`。

## 5. 验收

```powershell
$env:VPIN_RUN_DIR = "D:\...\model_training\outputs\my_run"
cd src/cp-snark-full
cargo run --release -- full <network_id_letter_if_mapped>
```

或通过 backend：`ProveRequest { model_id, run_dir, challenge }` → Rust `prover_pipeline_with_plan`。

期望：

- `proof_coverage` 含 `layer_proofs_plus_cps` 或至少 `EcPlusL1Binding`
- Client verification PASSED
- 篡改 `full_weights.json` 或 ec_witness → verify 失败

## 6. 不必改动的模块

- `circuit_prove.rs` / `point_mult.rs` / `point_addition.rs`（gadget 通用）
- `commit/cps.rs`（Spartan PC cm_W）
- `layer_proof/rlc.rs`（标量 fold 算法）

仅需新模型提供 **witness 数据** 与 **binding_layout**，而非 fork gadget 代码。
