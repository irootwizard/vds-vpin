# 模型参数与卷积 windows：接口分工与解决路径

> **设计定稿：** [`cp-snark-分层证明与RLC设计定稿.md`](./cp-snark-分层证明与RLC设计定稿.md) — windows 供式 (9) **验证**；**计算**已在 `Server.py` `rLCR`。  
> 代码：`src/cp-snark-full/src/model/`、`trace/`  
> 架构：[`cp-snark-full-架构草案.md`](./cp-snark-full-架构草案.md)

---

## 1. 要不要先写「模型解析模块」？

**要，但范围要窄。**

| 模块 | 先做什么 | 不做什么（第一阶段） |
|------|----------|----------------------|
| **`model/`** | 定义 `ModelParams`、`ModelManifest`、加载优先级 | Rust 内直接读 `.npy` / HF `safetensors` |
| **`trace/`** | 读现有 EC JSON；定义 `ConvWitnessSource` | 从 178 路 PtMul 反推 windows |
| **Python 导出** | `conv_trace.json`（`Server.py::convertFormatForRust_conv`，已写 filter_flat；windows 待补）、`model_export.json` | — |

原因：

- **W**（卷积核、FC）与 **轨迹**（178 权重、点坐标）是两种数据；混在 `weight.json` 里无法做式 (9)。
- 不在 Rust 里解析 HF/npy，可避免新依赖；用 **JSON 导出层** 对接 HF 客户端下载的模型。
- 卷积 **windows** 已定案：**现有 JSON 没有** → 必须 **新导出** 或 **明文重算**（实验），不能阻塞 `model/` 接口先落地。

---

## 2. 数据流（目标）

```text
[Hugging Face / .npy]  ──脚本──►  model_export.json     ──►  model::load_model_params
                                      │
[Server inference]   ──脚本──►  conv_trace.json        ──►  trace::load_conv_trace
                                      │
[convertFormat Rust] ──已有──►  pointMult/*.json       ──►  trace::load_ec_trace
                                      │
                                      └──── trace::build_linear_stack ──► layer_proof::check
```

---

## 3. 卷积 windows 三种来源（`ConvWitnessSource`）

| 来源 | 适用 | 状态 |
|------|------|------|
| **`TraceJson`** | 生产：Python 在 `myConv2d` 后写 `model_exports/{net}/conv_trace.json` | **待加 Python** |
| **`RecomputePlaintext`** | 单元测试 / 明文对照 | ✅ `ConvLayerProofSpec::from_plaintext_conv` |
| **`Missing`** | 仅 EC SNARK、暂不验卷积 MAC | 默认（无 conv_trace 文件时） |

**不要**从 `weight.json` 178 项反推 windows（rLCR 压缩轨迹，不是每格 $k^2$ 窗口）。

---

## 4. 建议实施顺序

1. ✅ **Rust `model/` + `trace/` 接口**（本批）  
2. **Python** `export_conv_trace.py`：在 `inferenceCNN` 末尾写 `conv_trace.json`（与 `convertFormatForRust_pointMult` 并列）  
3. **Python** `export_model_params.py`：`.npy` → `model_export.json`（FC 权重 + 与 Server 一致的 conv 核）  
4. **`prover_run`**：可选调用 `build_stack_for_network` → `stack.check_all_scalar`  
5. 将来：HF `safetensors` 只增加导出脚本，不改 `ModelParams` 形状  

---

## 5. `model_export.json` / `conv_trace.json` 路径

```text
src/cp-snark-full/model_exports/{network}/
  model_export.json   # 可选；有则 FC 从文件加载
  conv_trace.json     # 可选；有则卷积 MAC/RLC 可验
```

---

## 6. 与客户端 Hugging Face 下载的关系

客户端本地：`snapshot_download` → 脚本生成 **同一份** `model_export.json` + digest。  
服务器会话：只交换 $\mathsf{cm}_W$ + 证明，不传 safetensors。  
`ModelSource::HuggingFace { repo_id, revision, weights_digest_hex, ... }` 已在 `manifest.rs` 预留。

---

## 7. 修订

| 日期 | 说明 |
|------|------|
| 2026-06-04 | 初版；对应 `model/`、`trace/` 模块骨架 |
