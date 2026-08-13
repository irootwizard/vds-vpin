# vPIN Console

绿场 Vue 3 + Tauri 2 客户端（方案 A 四层控制面板）。

## 开发

```powershell
cd vpin-console
copy .env.example .env.local   # 配置 VITE_DEEPSEEK_API_KEY（可选，勿提交）
npm install
npm run dev                    # 浏览器 Mock（默认 VITE_BRIDGE_MODE=mock）
npm run tauri dev              # Tauri 桌面
```

## 临时标记（上线前删除）

- `TEMP-DEMO-TIMING` — 推理耗时模拟
- `TEMP-DEMO-LLM` / `TEMP-DEMO-TLS` — DeepSeek 演示页
- `TEMP-LOCAL-CUSTODY` — 本地托管 Shim

## Legacy

旧 UI 见 [`vpin_frontend/vpin-frontend`](../vpin_frontend/vpin-frontend/README.md)（已弃用为默认入口）。
