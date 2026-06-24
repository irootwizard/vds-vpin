# vpin-frontend

vPIN 产品化前端（**Tauri + Vue 3 + Vite + Naive UI**），桌面窗口标题为 **VDS-VPIN 工作台**。

## 技术栈

| 类别 | 库 |
|------|-----|
| 框架 | Vue 3、Vue Router 4 |
| UI 组件 | [Naive UI](https://www.naiveui.com/) |
| 图标 | [@vicons/ionicons5](https://www.xicons.org/) |
| 构建 | Vite 6 |
| 桌面壳 | Tauri 2 |

子页面（模型中心、任务配置等）暂以 iframe 嵌入静态 HTML，并通过 `theme.css` 统一视觉风格；首页已迁移为 Vue + Naive UI 组件。

**UI 参考**：`templates/` 隐语云截图 → 见 [模板对照实现说明](../../docs/vpin-frontend-模板对照实现说明.md)。

## 主要页面

| 路径 | 说明 |
|------|------|
| `/` | 工作台（Setup + 三步流程引导） |
| `/models` | 模型仓库（**无**训练/优化/在线服务） |
| `/tasks` | 推理任务列表 |
| `/tasks/vpin-demo-001` | 任务详情：效果指标 / **日志** / **密态流程**（后两者占位） |
| `/tasks/new` | 新建任务（静态页 embed，待 Vue 向导化） |
| `/demo` | **隐私样板间**欢迎页（服务须知 → 部署 → 体验） |
| `/demo/session/:id` | 图像密态推理 + 密文抽屉（Mock） |

## 前置要求

- **Node.js** 18+（含 npm）
- **Rust** 与 **Cargo**（仅桌面端 `tauri dev` / `tauri build` 需要）
  - Windows：从 [rustup.rs](https://rustup.rs/) 安装
  - 验证：`rustc --version`、`cargo --version`

## 安装依赖

```bash
cd vpin_frontend/vpin-frontend
npm install
```

## 启动开发环境

### 方式一：浏览器（仅 Web）

```bash
npm run dev
```

- 访问：<http://localhost:1420>
- Vite 开发服务器固定端口 **1420**（见 `vite.config.js`）

### 方式二：桌面应用（Tauri，推荐）

```bash
npm run tauri dev
```

- 自动启动 Vite（`npm run dev`）并打开桌面窗口
- 开发地址：<http://localhost:1420>

## 构建

```bash
# 仅构建 Web 静态资源（输出到 dist/）
npm run build

# 构建桌面安装包
npm run tauri build
```

## 常用脚本

| 命令 | 说明 |
|------|------|
| `npm run dev` | Vite 开发服务器 |
| `npm run build` | 生产环境 Web 构建 |
| `npm run preview` | 预览 build 产物 |
| `npm run tauri dev` | Tauri 桌面开发模式 |
| `npm run tauri build` | Tauri 桌面打包 |

## 推荐 IDE

- [VS Code](https://code.visualstudio.com/) + [Vue - Official](https://marketplace.visualstudio.com/items?itemName=Vue.volar) + [Tauri](https://marketplace.visualstudio.com/items?itemName=tauri-apps.tauri-vscode) + [rust-analyzer](https://marketplace.visualstudio.com/items?itemName=rust-lang.rust-analyzer)

## 常见问题：首次 `tauri dev` 启动很慢

`npm run tauri dev` 会同时启动 **Vite** 与 **Cargo 编译 Rust 桌面壳**。日志里若出现：

- `Updating crates.io index`
- `spurious network error` / `Failed to connect to index.crates.io`
- `Fetch [...] 49 com...`

说明 **前端已就绪**（Vite 通常几百毫秒），慢在 **首次下载并编译 Tauri 依赖**（约数十个 crate + 完整编译，国内直连 crates.io 常超时重试）。

### 快速绕过（仅调试页面）

不需要桌面窗口时，直接用浏览器模式，无需 Cargo：

```bash
npm run dev
```

浏览器打开 <http://localhost:1420>，界面与 Tauri 内 iframe 一致。

### 加速 Cargo 下载（推荐，国内网络）

在用户目录创建 `%USERPROFILE%\.cargo\config.toml`（当前环境尚未配置）：

```toml
[source.crates-io]
replace-with = "rsproxy-sparse"

[source.rsproxy-sparse]
registry = "sparse+https://rsproxy.cn/index/"
```

保存后重新执行 `npm run tauri dev`。首次仍须完整编译（约数分钟），**之后**依赖缓存命中，启动会明显加快。

### 首次编译完成后

`src-tauri/target/` 与本地 Cargo 缓存就绪后，再次 `tauri dev` 一般只需增量编译，不再长时间 `Fetch`。
