# UI 设计参考图（隐语云）

本目录为 **隐语云大模型密算平台** 截图，用于 vPIN 前端 **视觉 + 交互逻辑** 对照。

## 已实现对照（功能逻辑）

| 文件 | 隐语云场景 | vPIN 路由 / 组件 |
|------|-----------|------------------|
| `image2.png` | 服务须知 | `ServiceNoticeModal.vue` |
| `image3.png` | 样板间欢迎、三步流程 | `/demo` `DemoWelcomeView.vue` |
| `image4.png` | 部署 Demo、选模型 | `/demo/deploy` `DemoDeployView.vue` |
| `image5.png` | 排队、对话区、右侧状态 | `/demo/session/:id` `DemoSessionView.vue` |
| `image10.png` | 隐私模式、密文抽屉 | `PrivacyEffectDrawer.vue` |
| `image.png` | 登录 | 未实现（桌面应用免登录） |
| `image (1).png` | 任务列表 | `/tasks` |
| `image (5)/(6).png` | 任务详情 Tab | `/tasks/:id` |

## 完整体验路径

```text
/demo → 立即执行 → [服务须知] → /demo/deploy → 立即部署
  → /demo/session/:id（排队）→ 样例图像 → 发送 → 眼睛图标查看密文
```

## 不包含（勿照搬）

- 模型训练、模型优化、在线服务（侧栏不出现）
- ChatGLM/Qwen 大模型对话（改为 **CNN/LeNet 图像密态推理**）
- KMS/TEE 大模型解密链（改为 **AHE 密文 Mock**）

详细说明：[docs/vpin-frontend-模板对照实现说明.md](../../docs/vpin-frontend-模板对照实现说明.md)
