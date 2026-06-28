# AHE Python 侧推理失败 — 错误报告

**报告时间**：2026-06-28  
**场景**：Tauri UI · 推理引擎 Python · 模型 `cnn-mnist-trained` · MNIST 序号 **1000**  
**UI 表现**：`❌ inference failed (exit 1):`（冒号后无详细错误文本）  
**说明**：本报告仅基于现有日志与复现测试记录，不含代码修改。

相关启动文档：[ahe-ui-client-server-test-startup.md](./ahe-ui-client-server-test-startup.md)

---

## 1. 现象摘要

| 项目 | 内容 |
|------|------|
| 预处理 | 正常（REST `:8000`，样本 #1000 · label 9 已显示） |
| 推理 | 失败，UI 仅显示 `inference failed (exit 1):` |
| 引擎 | Python 标准 · vpin-backend :8000 |
| 模型 | CNN MNIST Network A (trained) |

预处理走 REST，推理走 Tauri 子进程 + WebSocket；**失败发生在推理链路，而非预处理**。

---

## 2. 后端日志（主要证据）

**日志来源**：Python 后端终端（`python -m vpin_backend.main`，端口 8000）

### 2.1 与用户 UI 操作一致的错误模式（出现 2 次）

```
INFO: WebSocket /api/v1/session/ws [accepted]
INFO: connection open
→ 在 session_ws 发送 ModelSelectAck 时：
   websockets.exceptions.ConnectionClosedOK: received 1000 (OK); then sent 1000 (OK)
   uvicorn.protocols.utils.ClientDisconnected
   starlette.websockets.WebSocketDisconnect
→ 异常处理再次 send Error 帧时：
   RuntimeError: Cannot call "send" once a close message has been sent.
INFO: connection closed
```

**解读**：

1. WebSocket 已建立（P0 前后）。
2. 客户端在服务端返回 **ModelSelectAck（P1）之前或发送过程中** 主动关闭连接（close code 1000 = 正常关闭）。
3. 服务端在已断开的连接上继续 `send` → 抛出 `WebSocketDisconnect`。
4. `session.py` 的 `except` 再次 `_asend(ws, "Error", ...)` → 二次异常 `RuntimeError`（**日志噪音**，会掩盖真实根因）。

**代码位置**（便于对照）：

- `vpin-backend/vpin_backend/api/routes/session.py`：`session_ws` → `_asend(ws, "ModelSelectAck", ...)`
- `vpin_frontend/vpin-frontend/src-tauri/src/lib.rs`：`run_subprocess_with_progress` → `inference failed (exit {})`

### 2.2 同期其他 WebSocket 行为

日志末尾多次出现：

```
WebSocket [accepted] → connection open → connection closed
```

无完整 P0–P3 交互记录，多为**极短连接**（可能为 UI 重试、CLI 探测或并发会话）。

### 2.3 预处理 API 正常

```
GET /api/v1/data/official/test/1000 HTTP/1.1" 200 OK
```

说明 **MNIST #1000 加载与 REST 预处理无问题**。

---

## 3. 对照复现（同环境、未改代码）

| 测试方式 | 命令/路径 | 结果 |
|----------|-----------|------|
| CLI 基础 | `vpin_client ahe-infer --mnist-index 1000` | **成功** `prediction=9 label=9`，约 15–18s |
| CLI 模拟 Tauri | 加 `--timing --trace --progress-ndjson --infer-engine python` | **成功** `exit=0`，stdout 含完整 JSON |
| UI（用户截图） | Tauri → Python 引擎 → #1000 | **失败** `exit 1`，无 stderr 详情 |

**CLI 等价命令**（与 Tauri `build_python_infer` 一致）：

```powershell
cd vPIN-main
.\.venv\Scripts\python.exe -m vpin_client.cli ahe-infer `
  --backend ws://127.0.0.1:8000/api/v1/session/ws `
  --model cnn-mnist-trained `
  --mnist-index 1000 `
  --timing --trace --progress-ndjson --infer-engine python `
  1>stdout.txt 2>stderr.txt
echo exit=$LASTEXITCODE
```

**结论**：同机、同后端、同模型、同序号 **1000** 下，**Python 同态推理链路本身可用**；UI 失败更符合 **Tauri 子进程 / WebSocket 会话层** 问题，而非 Network A 权重或 MNIST 样本错误。

---

## 4. 根因分析（分层）

### 4.1 直接原因（客户端 / 会话层）

后端日志表明：**WebSocket 客户端在 P1（ModelSelectAck）完成前断开**。

可能触发因素（按可能性排序，需进一步人工确认）：

| 可能原因 | 说明 |
|----------|------|
| Tauri 子进程提前退出 | `lib.rs` 在 `exit != 0` 时向 UI 报 `inference failed (exit N): {stderr}`；若 stderr 为空则 UI 只显示 `exit 1:` |
| 推理被中断 | 重复点击「运行」、切换样本/引擎、关闭窗口等 |
| 子进程环境异常 | 历史上 `.venv` 损坏、`gmpy2` 缺失曾导致 exit 1；若 Tauri 未重启可能仍用旧进程状态 |
| WebSocket 竞态 | 短时间多次建连（日志中多次 open/close），前一会话断开可能影响 UI 侧状态 |

### 4.2 次要原因（服务端日志放大）

`session.py` 在捕获 `WebSocketDisconnect` 后仍向已关闭连接发送 `Error` 帧 → `RuntimeError`。

这**不是推理算法失败**，但会：

- 在终端打出长栈
- 使 ASGI 报 `Exception in ASGI application`
- 干扰判断「真正失败点在哪一步」

### 4.3 已排除项

| 假设 | 排除依据 |
|------|----------|
| MNIST #1000 数据错误 | REST 200；CLI 同 index 成功 |
| 模型权重缺失/错误 | CLI `cnn-mnist-trained` 成功 |
| Python 后端未启动 | health 200；有 WS accept 记录 |
| 纯计算路径 bug | CLI 完整 P0–P3 约 12–18s 成功 |

---

## 5. UI 错误信息为何为空

Tauri 桥接逻辑（`src-tauri/src/lib.rs` → `run_subprocess_with_progress`）：

- 子进程 **exit != 0** 时，错误文本优先取 **stderr**；
- stderr 为空则 fallback 到 **stdout**；
- 若两者均无有效文本 → UI 显示 **`inference failed (exit 1):`** 且冒号后为空。

progress 事件走 **stderr**（NDJSON），最终结果 JSON 走 **stdout**；若子进程在 WS 握手早期异常退出，常无 stderr 错误行。

---

## 6. 时间线（推断）

```
[UI] 预处理 #1000 OK（REST :8000）
[UI] 点击「运行 AHE 推理」→ Tauri spawn vpin_client.cli（含 --progress-ndjson）
[Client] WebSocket 连接 :8000/api/v1/session/ws
[Client] 发送 SessionStart / ModelSelect（推断）
[Client] 在 ModelSelectAck 到达前关闭 WS（close 1000）  ← 后端日志锚点
[Server] ModelSelectAck send 失败 → WebSocketDisconnect
[Server] 异常处理再次 send → RuntimeError（日志噪音）
[Tauri] 子进程 exit 1 → UI 显示 inference failed (exit 1):
```

---

## 7. 建议验证步骤（手工）

1. **重启 Tauri 窗口**（确保加载修复后的 `.venv` 与 `gmpy2`）。
2. 先用 **MNIST index 0** 跑通 Python 引擎，再试 **1000**。
3. 推理约 **15–70s** 内不要重复点击、不要切换引擎/样本。
4. 若仍失败，执行上文 §3 CLI 等价命令：
   - `exit=0` → 问题在 **Tauri/UI 层**
   - `exit=1` → 查看 `stderr.txt` 全文
5. 同时观察 **后端终端**：是否再次出现 `ClientDisconnected` @ `ModelSelectAck`。

---

## 8. 结论

| 维度 | 结论 |
|------|------|
| **是否 Python 同态计算失败** | **否**（CLI 同参数已成功） |
| **是否 MNIST #1000 / 模型问题** | **否** |
| **UI 失败直接关联的后端现象** | **WebSocket 客户端在 P1 前/中提前断开** |
| **后端日志额外问题** | 断连后仍 send Error → `RuntimeError`（日志干扰项） |
| **UI 错误信息为空** | Tauri 子进程 exit 1 且 stderr 无内容 |

**综合判断**：当前 UI 报错属于 **Tauri 客户端子进程 / WebSocket 会话生命周期问题**，而非 Python AHE 计算或 MNIST #1000 数据问题。

---

## 9. 后续修复方向（记录用，本文未实施）

| 优先级 | 方向 | 说明 |
|--------|------|------|
| P1 | `session.py` 断连处理 | `WebSocketDisconnect` 时不再向已关闭连接 `_asend` |
| P2 | Tauri 错误回传 | 子进程失败时合并 stdout 尾部或 exit code 说明 |
| P3 | UI 防重复提交 | 推理进行中禁用「运行」按钮 |

---

## 10. 相关文件索引

| 用途 | 路径 |
|------|------|
| 启动与测试指南 | `docs/ahe-ui-client-server-test-startup.md` |
| WebSocket 会话 | `vpin-backend/vpin_backend/api/routes/session.py` |
| Tauri 推理桥 | `vpin_frontend/vpin-frontend/src-tauri/src/lib.rs` |
| 客户端 CLI | `vpin-client/vpin_client/cli.py` |
| Python 冒烟 | `scripts/ahe_e2e_smoke.py` |
