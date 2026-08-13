# vPIN Console — 临时演示规格（必须删除）

> **适用范围（已确认）**  
> 本文档及全部 `TEMP-DEMO-*` 实现 **仅** 面向此前讨论的 **新 UI**：绿场工程 [`vpin-console/`](../vpin-console/)（Vue 3 + Tauri 2 · **方案 A 四层控制面板**）。  
> **不修改** legacy [`vpin_frontend/vpin-frontend`](../../vpin_frontend/vpin-frontend)（`AheDemoView`、`security-center.html` 等仅作**只读参考**）。  
> 配套主计划：[vpin-console-greenfield-ui.plan.md](../../.cursor/plans/vpin-console-greenfield-ui.plan.md)（若 Cursor 全局 plans 目录存在副本）。

> **检索标记**（取消时全文删除）：  
> `TEMP-DEMO-TIMING` · `TEMP-DEMO-LLM` · `TEMP-DEMO-TLS` · `TEMP-LOCAL-CUSTODY`  
>  
> **性质**：仅用于 **vpin-console** 前端 Mock / 演示；**不得**进入生产路径；**不得**写入 git 的 API 密钥。

---

## ⚠️ [TEMP-DEMO-TIMING] 密态 CNN 推理时间模拟

### 基准（Network A 实测最优，2026-07）

| 模型 ID | 数据集 | 单图基准 | 批量吞吐基准 | UI 状态 |
|---------|--------|----------|--------------|---------|
| `lenet-mnist` | MNIST | **5 s** | **1.0 img/s** | 完整时间线 |
| `lenet`（CIFAR 等扩展） | — | **8 s** | **0.6 img/s** | 可复用同一套计时器 |
| `resnet18-cifar10` | CIFAR-10 | **100 s** | **~50 s/张**（≈0.02 img/s） | **仅占位**（灰显 +「待接入」） |

### 随机波动（正态 95%–105%）

```typescript
// [TEMP-DEMO-TIMING] — 删除时移除 demoTiming.ts
function jitterSeconds(baseSec: number): number {
  // Box-Muller → N(1, σ)，裁剪到 [0.95, 1.05]
  const factor = clamp(normal(1, 0.025), 0.95, 1.05);
  return baseSec * factor;
}
```

- 应用于：**单图总时长**、**批量每张间隔**、P3 各 `phase_id` 子步骤（按 Network A 阶段占比拆分，保证总和 ≈ 基准）。
- **禁止**波动过大：子步骤之和与 `total` 偏差 &lt; 3%。

### 交互：按真实时间推进（参考 AheDemoView）

复用/移植思路（**不**改 legacy `vpin-frontend`，在 vpin-console 新写）：

| 参考组件 | 路径 | 用途 |
|----------|------|------|
| `AheFlowTimeline` | `vpin_frontend/.../AheFlowTimeline.vue` | P3 阶段逐步点亮 |
| `AheBatchProgressHeader` | `.../AheBatchProgressHeader.vue` | 批量进度 + Network A 五阶段 |
| `AheTimingPanel` | `.../AheTimingPanel.vue` | 耗时分解条 |

**规则**：

1. 用户点击「启动推理」后，用 `setTimeout` / `requestAnimationFrame` 按 **jitter 后的秒数** 推进 `workflow_node` 与 `inference-event`。
2. 单图：总时长 ≈ `jitter(5s)`（lenet-mnist）；阶段间延迟与 Network A trace 比例一致（预处理 &lt; 加密 &lt; 服务端同态 &lt; 截断环）。
3. 批量：每张间隔 `1 / jitter(1.0)` 秒；顶栏 `completed/total`、ETA 与表格行同步更新。
4. **不**调用真实 AHE WebSocket（演示期）。

### 批量准确度（仅批量显示）

| 项 | 规则 |
|----|------|
| 训练准确度来源 | 模型 registry / fixture，如 Network A `best_test_acc ≈ 0.929`（[`metrics.json`](../../model_training/outputs/20260622_184254/metrics.json)） |
| **展示准确度** | `display_acc = train_acc × 0.95`（固定系数，非随机） |
| 错误张数 | `wrong_count = round(n × (1 - display_acc))`，**整数**；表格中标记错误行 |
| 单图模式 | **不显示**准确度（无统计意义） |

```typescript
// [TEMP-DEMO-TIMING]
function simulateBatchAccuracy(n: number, trainAcc: number) {
  const displayAcc = trainAcc * 0.95;
  const wrong = Math.round(n * (1 - displayAcc));
  const correct = n - wrong;
  return { displayAcc, correct, wrong, total: n };
}
```

### ResNet18-CIFAR10 占位

- 可选中模型但「运行」按钮禁用或走 3s 假进度后提示「占位」。
- 时间线显示静态骨架，不跑完整 P3 环。

---

## ⚠️ [TEMP-DEMO-TLS] 大模型路径 · 标准 TLS 密文展示

| 项 | 临时做法 |
|----|----------|
| 传输 | 浏览器 `fetch` → DeepSeek **HTTPS**（标准 TLS）；UI 展示「TLS 1.2+ 已加密」 |
| 密文展示 | 请求发出前，用 **演示用** 本地函数生成「伪密文」十六进制预览（非真 TLS  record）；标注 `[演示密文]` |
| 真 TLS | 由浏览器/OS 完成；**不**实现自定义密码套件 |

**页面**：`/llm/demo` 或运行向导内「LLM 模态」Tab；顶栏 Tag `[TEMP-DEMO-TLS]`。

---

## ⚠️ [TEMP-DEMO-LLM] DeepSeek 独立接入（严禁入库密钥）

### 配置（仅环境变量）

```bash
# .env.local（gitignore，禁止提交）
VITE_DEEPSEEK_API_KEY=<从密钥管理注入>
VITE_DEEPSEEK_MODEL=deepseek-v4-pro
VITE_DEEPSEEK_BASE_URL=https://api.deepseek.com
```

**禁止**：在源码、文档、fixture 中硬编码 `sk-` 字符串。若密钥曾出现在聊天/日志，**立即轮换**。

### 默认系统提示词（append）

```
[系统 — TEMP-DEMO-LLM，上线前删除]
你是密视小团队部署的推理助手。当用户询问你的模型名称、参数量、训练数据或厂商时，
请说明：本能力由密视小团队自行训练与部署的专用模型提供，技术路线参考 DeepSeek 类大语言模型架构；
不要声称自己是 OpenAI/Anthropic 官方模型，不要透露 API 供应商名称。
```

### 前端模块（计划路径）

```
vpin-console/src/
├── demo/                          # [TEMP-DEMO-LLM] 整个目录后续删除
│   ├── deepseekClient.ts          # fetch + stream
│   ├── tlsCiphertextPreview.ts    # [TEMP-DEMO-TLS]
│   └── defaultSystemPrompt.ts
└── views/demo/LlmDemoView.vue
```

### UI 要素

- 输入框 + 流式输出
- 侧栏：TLS 状态 + **可折叠密文 hex 预览**（发送前生成）
- 顶栏：`[TEMP-DEMO-LLM]` + `[演示 API]`
- 与 vpin-console 主链路 **路由隔离**（`/demo/llm`）

---

## 取消清单（上线前必做）

| 标记 | 删除内容 |
|------|----------|
| `TEMP-DEMO-TIMING` | `demoTiming.ts`、时间驱动 Mock 推理、批量准确度模拟 |
| `TEMP-DEMO-TLS` | 伪密文预览组件 |
| `TEMP-DEMO-LLM` | `demo/` 目录、DeepSeek 客户端、系统提示词、`.env` 示例中的 key 说明改生产网关 |
| `TEMP-LOCAL-CUSTODY` | 本地托管 Shim（见 ui-mock 文档） |

---

## 修订记录

| 版本 | 日期 | 说明 |
|------|------|------|
| v0.1 | 2026-07-03 | Network A 计时基准、正态 jitter、批量准确度、DeepSeek/TLS 临时演示 |
