# VDS-VPIN Tauri客户端

基于Tauri的vPIN隐私计算桌面应用程序，支持与Python后端集成。

## 功能特性

- **隐私保护前端**：基于Tauri的桌面应用，私钥安全存储在本地
- **模型管理**：支持多种深度学习模型的选择和管理
- **任务监控**：实时监控推理任务状态和系统资源
- **数据配置**：支持数据上传和预处理配置
- **Python集成**：通过子进程调用Python后端进行推理计算
- **安全通信**：支持TLS加密通信

## 系统要求

### Windows
- Windows 10 或更高版本
- Node.js 16+
- Rust 1.70+ (含Cargo)
- Python 3.8+ (可选，用于后端推理)
- WebView2 运行时 (通常Windows 10+已内置)

### 开发环境
```bash
# 检查Node.js
node --version

# 检查Rust
rustc --version
cargo --version

# 检查Python (可选)
python --version
```

## 安装依赖

```bash
# 安装Node.js依赖
npm install

# 或使用yarn
yarn install
```

## 开发模式运行

```bash
# 启动开发服务器
npm run dev

# 或使用yarn
yarn dev
```

这将启动Tauri开发模式，支持热重载和调试工具。

## 构建生产版本

```bash
# 构建Windows可执行文件
npm run build

# 构建结果位于 src-tauri/target/release/bundle/
```

## 使用说明

### 1. 连接服务器
- 首次运行时，在首页设置服务器地址 (默认: `http://127.0.0.1:8000`)
- 点击"健康检查"验证连接状态

### 2. 选择模型
- 进入"模型中心"查看可用模型
- 选择适合的模型进行推理任务

### 3. 上传数据
- 在"数据配置"页面上传推理数据
- 支持图像(CSV, PNG, JPG)和表格数据

### 4. 创建任务
- 在工作台点击"新建任务"
- 选择模型和数据，配置任务参数
- 任务创建后将自动开始推理

### 5. 监控任务
- 在"任务监控"页面查看任务状态
- 实时查看CPU、内存、网络使用情况

## Python后端集成

如果需要启用Python后端推理：

### 1. 安装vPIN后端
```bash
# 在项目根目录
cd vpin-backend
pip install -r requirements.txt
```

### 2. 配置Python路径
Tauri应用会自动检测系统中的Python环境。

### 3. 验证Python集成
- 在应用中可以通过`检查Python后端`功能验证集成状态
- 确保`vpin-backend`目录在正确的位置

## 项目结构

```
apps/vpin-client/
├── ui/                          # 前端资源
│   ├── css/                     # 样式文件
│   ├── assets/                  # 静态资源(图标等)
│   ├── components/              # 组件模板
│   ├── js/                      # JavaScript模块
│   ├── index.html              # 首页
│   ├── task-dashboard.html     # 任务监控页面
│   ├── model-center.html       # 模型中心页面
│   └── data-config.html        # 数据配置页面
├── src-tauri/                   # Tauri Rust后端
│   ├── src/                     # Rust源码
│   │   └── lib.rs              # 主要逻辑
│   ├── icons/                   # 应用图标
│   └── tauri.conf.json         # Tauri配置
└── package.json                 # Node.js配置
```

## API命令

### 基础命令
- `health_check` - 健康检查
- `get_server_url` - 获取服务器地址
- `set_server_url` - 设置服务器地址

### 模型和任务管理
- `get_models` - 获取模型列表
- `refresh_models` - 从服务器刷新模型列表
- `get_tasks` - 获取任务列表
- `create_task` - 创建新任务

### Python集成
- `check_python_backend` - 检查Python后端状态
- `python_inference` - 调用Python推理
- `check_model_available` - 检查模型是否可用
- `get_python_models` - 获取Python后端模型列表

### 系统状态
- `get_system_status` - 获取系统资源状态
- `get_security_status` - 获取安全状态
- `upload_data` - 上传数据文件

## 故障排除

### 连接失败
1. 检查服务器地址是否正确
2. 确保服务器正在运行
3. 检查防火墙设置

### Python集成失败
1. 确认Python已正确安装
2. 检查vpin-backend依赖是否安装完整
3. 查看应用日志获取详细错误信息

### 构建失败
1. 确保Rust和Node.js版本符合要求
2. 清理缓存: `cargo clean` 和 `rm -rf node_modules`
3. 重新安装依赖

## 开发工具

- **Tauri DevTools**: 开发模式下按F12打开
- **日志查看**: 在Tauri控制台查看详细日志
- **热重载**: 修改前端文件会自动重载

## 安全说明

- 私钥仅在本地Tauri环境中存储和处理
- 所有数据传输使用TLS加密
- 不支持从非信任来源加载代码
- 建议仅从官方渠道下载模型文件

## 贡献指南

1. Fork项目
2. 创建功能分支
3. 提交更改
4. 发起Pull Request

## 许可证

根据项目根目录的LICENSE文件确定。

## 联系方式

如有问题或建议，请联系开发团队。