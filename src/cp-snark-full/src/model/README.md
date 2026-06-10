# `model` — 静态模型参数 **W** + 注册存储

与 `trace/`（同态计算轨迹）、`load_data`（178 维 PtMul witness）分离。

## 为什么要单独模块？

| 对象 | 含义 | 来源 |
|------|------|------|
| **ModelParams** | 论文 $\mathbf{W}^*$（卷积核、FC、bias、池化公开超参） | `model_export.json` / 内置表 |
| **ModelRecord** | 存储索引行（名称、时间、承诺槽、截断计划槽） | `model_store/.../record.json` |
| **weight.json** | PtMul 轨迹标量 $a_j$（178） | Python `convertFormatForRust_pointMult` |

## 加载方式（二选一）

| API | 场景 |
|-----|------|
| `load_model_params("A")` | 按 vPIN 网络字母，读 `model_exports/A/` 或内置 |
| `JsonFileModelStore::open_default().load_params("vpin-network-a")` | 按 **model_id**，task3 注册表 |

```rust
let store = JsonFileModelStore::open_default();
let params = store.load_params("vpin-network-a")?;
let manifest = store.load_manifest("vpin-network-a")?;
```

承诺回写（task3c 钩子）：

```rust
attach_commitment_to_record(&mut record, &point_hex, &digest_hex, "2026-06-04T12:00:00Z");
store.save_record(&record)?;
```

## 文件

| 文件 | 作用 |
|------|------|
| `params.rs` | `ModelParams`, `ConvParams`, `FcParams`, `PoolHyper` |
| `manifest.rs` | `ModelSource`（VpinNpy / ExportedJson / HuggingFace） |
| `record.rs` | `ModelRecord`, `ModelCommitmentSlot`, `TruncationPlanSlot` |
| `store.rs` | `ModelStore` trait + `JsonFileModelStore` |
| `load.rs` | `load_from_export_path`, `load_model_params` |

## 目录

```text
model_store/                          # 注册表（示例已含 vpin-network-a）
  index.json
  models/{model_id}/record.json
  models/{model_id}/manifest.json
  models/{model_id}/model_export.json

model_exports/{network}/              # 按字母名的快捷路径（可选）
  model_export.json
  conv_trace.json
```

## 设计文档

[`docs/task3-模型接入解析与存储方案.md`](../../../../docs/task3-模型接入解析与存储方案.md) — task3 接入、HTTPS、DB、截断算法、承诺。

## Hugging Face（未实现）

流程：`snapshot_download` → 脚本写 `model_export.json` → `store.register(record)`；客户端用 `weights_digest_hex` 对账。
