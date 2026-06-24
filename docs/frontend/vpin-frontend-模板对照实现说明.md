# vPIN 前端 · 隐语云模板对照实现说明

> **参考素材**：`vpin_frontend/vpin-frontend/templates/`（隐语云大模型密算平台截图）  
> **实现日期**：2026-06-10（D3.5 + **隐私样板间 Demo 完整流程**）  
> **关联文档**：[UI 设计规范](./vpin-frontend-UI设计规范.md)

---

## 1. 参考图与 vPIN 映射（含功能逻辑）

| 模板图 | 隐语云内容 | vPIN 实现 | 状态 |
|--------|-----------|-----------|------|
| `image.png` | 登录页 | **未做**（Tauri 本地启动；服务须知替代登录后协议） | — |
| `image2.png` | 服务须知弹窗 | `ServiceNoticeModal.vue`（首次「立即执行」前） | ✅ |
| `image3.png` | 样板间欢迎 + 三步 + CTA | `/demo` `DemoWelcomeView.vue` | ✅ |
| `image4.png` | 部署 Demo（选模型、有效期） | `/demo/deploy` `DemoDeployView.vue`（CNN/LeNet） | ✅ |
| `image5.png` | 排队 + 对话区 + 右侧信息栏 | `/demo/session/:id` `DemoSessionView.vue` | ✅ |
| `image10.png` | 隐私模式 + 眼睛 + 密文抽屉 | `PrivacyEffectDrawer.vue`（切换明文/密文） | ✅ Mock |
| `image (1).png` | 测评任务列表 | `/tasks` `TaskListView.vue` | ✅ |
| `image (5)/(6).png` | 任务详情 Tab | `/tasks/:id` 日志/密态流程/指标 | ⏳ 占位 |
| 侧栏 | 模型训练/优化/在线服务 | **不实现** | — |
| 侧栏 | 样板间 | **隐私样板间** `/demo` | ✅ |

---

## 2. 隐私样板间：完整功能逻辑

对照隐语云「部署 → 排队 → 对话 → 查看密态效果」，vPIN 适配为 **图像密态推理**（非 ChatGLM 大模型对话）：

```text
/demo 欢迎页
  → [未同意] 服务须知 Modal（image2）
  → /demo/deploy 填写服务名、选 CNN A / LeNet、有效期
  → /demo/session/:id
       ├─ status=queuing  排队 UI（约 3–10s 自动就绪）
       ├─ status=ready    对话 + 图像推理
       │    ├─ 文字提问 → Mock 助手（解释 AHE/Verify）
       │    ├─ 上传图像 / 样例图像 → Mock 密态推理
       │    └─ 回答带 🔐隐私模式 + 眼睛 → PrivacyEffectDrawer
       │         ├─ 输入图像密文张量（Mock）
       │         ├─ 输出 logits 密文（Mock）
       │         └─ 「切换明文」显示原图 + 预测类别
       └─ 右侧栏：状态 / 模型 / 到期 / 删除服务
```

### 与隐语云的差异（刻意）

| 隐语云 | vPIN 样板间 |
|--------|-------------|
| ChatGLM / Qwen 对话 | **28×28 图像隐私推理** + 流程说明对话 |
| KMS/TEE 解密步骤 | **AHE 密文张量 + logits**（Mock） |
| 真实 LLM 回答 | `demoCrypto.js` Mock 推理与密文 |

---

## 3. 刻意不做的功能

- 模型训练、模型优化、在线商用服务  
- 真实大模型权重部署与 KMS 鉴权链  
- 多方联邦、机构项目  

见 `src/constants/nav.js` → `EXCLUDED_FEATURES`。

---

## 4. 代码结构

```
src/
├── composables/
│   ├── useDemoStore.js       # 演示会话、服务须知、消息列表
│   └── useProtocolSession.js # 工作台 Setup（与 demo 独立）
├── utils/demoCrypto.js       # Mock 密文、推理、样例图、对话回复
├── components/demo/
│   ├── ServiceNoticeModal.vue
│   └── PrivacyEffectDrawer.vue
└── views/demo/
    ├── DemoWelcomeView.vue
    ├── DemoDeployView.vue
    └── DemoSessionView.vue
```

### 路由

| 路径 | 说明 |
|------|------|
| `/demo` | 欢迎 + 立即执行 |
| `/demo/deploy` | 部署演示服务 |
| `/demo/session/:id` | 排队 / 推理 / 密态展示 |
| `/` | 工作台 Setup |
| `/models` | 模型仓库 |
| `/tasks` | 实验任务列表（研发向） |
| `/tasks/:id` | 任务详情 Tab（日志/密态流程占位） |

---

## 5. 占位与后续对接

| 模块 | 现状 | 后续 |
|------|------|------|
| 样板间推理 | `demoCrypto.js` Mock | `vpin-backend` 同态推理 API + WSS |
| 密文展示 | 确定性伪随机串 | 真实 AHE 密文或截断预览 |
| 对话回复 | 规则 Mock | 可选接入说明型 LLM（非必须） |
| 任务详情日志/密态 Tab | 静态 Mock | 与会话 API 统一 |

---

## 6. 验证路径

```bash
cd vpin_frontend/vpin-frontend && npm run dev
```

**样板间完整走一遍：**

1. 侧栏 **隐私样板间** → `/demo`  
2. 点击 **立即执行** → 同意服务须知  
3. 选 **CNN Network A** → **立即部署**  
4. 等待排队结束 → **样例图像** → **发送**  
5. 点击回答旁 **眼睛** → **切换明文/密文**  

**研发向：**

- `/tasks/vpin-demo-001` — 任务详情三 Tab  
- `/` — AHE Setup  

---

## 7. 路线图更新

| 阶段 | 内容 | 状态 |
|------|------|------|
| D3.5 | 隐语云风格壳层 + 任务列表/详情 | ✅ |
| **D3.6** | **隐私样板间完整流程 + 密态抽屉** | ✅ |
| D4 | 新建任务 Vue 向导 | 待做 |
| D5 | 样板间/任务对接 backend 真实推理 | 待做 |

---

**维护**：变更 demo 流程时请同步更新本文与 `templates/README.md`。
