# vPIN 双端框架

## 项目结构

```
apps/
├── vpin-server/       # Rust axum 服务端
│   ├── src/
│   │   └── main.rs    # API 服务器实现
│   └── Cargo.toml
│
└── vpin-client/       # Tauri 客户端
    ├── src-tauri/
    │   ├── src/
    │   │   ├── lib.rs  # Tauri 命令实现
    │   │   └── main.rs # 入口
    │   ├── tauri.conf.json
    │   └── Cargo.toml
    ├── ui/
    │   └── index.html # 前端界面
    └── package.json
```

## 运行方式

### 服务端

```bash
cd apps/vpin-server
cargo run
```

访问 http://127.0.0.1:8000/api/v1/health 进行健康检查

### 客户端

```bash
cd apps/vpin-client
npm run tauri dev
```

## API 接口

- GET /api/v1/health - 健康检查
- GET /api/v1/models - 模型列表

## Tauri 命令

- health_check() - 检查服务端健康状态
- set_server_url(url) - 设置服务端地址
- get_server_url() - 获取当前服务端地址
