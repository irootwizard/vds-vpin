# script.bat -v -c -A 运行流程和详细输出

## 一、命令解析和执行流程

### 1. 命令参数解析
- `-v`: 设置 `QUIET_MODE=0`，启用详细输出模式
- `-c`: 执行 CNN 网络相关操作
- `-A`: 运行 CNN 网络 A（version=1, port=35000）

### 2. 执行流程

```
script.bat -v -c -A
  ↓
解析参数：QUIET_MODE=0, version=1, port=35000, network_label=A
  ↓
调用 :run_server_and_client 1 35000
  ↓
生成日志文件名：A_Run_YYYYMMDD-HHMMSS.log
  ↓
启动 Server.py (后台运行，显示输出)
  ↓
等待服务器监听端口 35000
  ↓
启动 Client.py (前台运行，显示输出)
  ↓
切换到 Rust 项目目录
  ↓
运行 cargo run -- A (输出重定向到日志文件)
```

---

## 二、详细输出内容

### 阶段 1: 脚本初始化输出

```batch
Running server.py and client.py for CNN network A on port 35000...
Starting Server...
```

### 阶段 2: Server.py 启动和初始化

**Server.py 输出：**

```
[STARTING] Server is starting
[LISTENING] Server is listening on 127.0.0.1:35000
[WAITING] Waiting for client connection...
```

**脚本输出（等待服务器就绪）：**

```batch
Server is ready.
```

**Server.py 继续输出（客户端连接后）：**

```
Server: [NEW CLIENT CONNECTION] ('127.0.0.1', xxxxx) connected.
```

### 阶段 3: Client.py 启动和连接

**Client.py 输出：**

```
**************************************************
Client: Connection established.

Client: Generating public-private keys...
Client: Encrypting data sample...
**************************************************
```

### 阶段 4: Server.py 执行 CNN 推理

**Server.py 输出（接收加密数据）：**

```
**************************************************
Server: Encrypted data sample received.
Server: Performing inference on encrypted data...
**************************************************
```

**Server.py 输出（第一层卷积）：**

```
**************************************************
Server: First conv. layer started!
Server: First conv. layer finished!
**************************************************
```

**Server.py 输出（第一层激活）：**

```
**************************************************
Server: First Activation layer started!
Server: First Activation layer finished!
**************************************************
```

**Server.py 输出（平均池化）：**

```
**************************************************
Server: First AvgPooling started!
Server: First AvgPooling finished!
**************************************************
```

**Server.py 输出（展平）：**

```
**************************************************
Server: Flattening started!
Server: Flattening finished!
**************************************************
```

**Server.py 输出（全连接层 FC1）：**

```
**************************************************
Server: FC1 started!
Server: FC1 finished!
**************************************************
```

**Server.py 输出（第二层激活）：**

```
**************************************************
Server: Second Activation layer started!
Server: Second Activation layer finished!
**************************************************
```

**Server.py 输出（全连接层 FC2）：**

```
**************************************************
Server: FC2 started!
Server: FC2 finished!
Server: Number of EC point multiplications: <数量>
Server: Number of EC point additions: <数量>
**************************************************
```

**Server.py 输出（保存见证数据）：**

```
Server: The witnesses are saved in a file for generating proof with Rust
```

### 阶段 5: 脚本切换到 Rust 目录

**脚本输出：**

```batch
Navigating to proof generation directory...
Generating Proof...
```

### 阶段 6: Rust 程序执行（输出到日志文件）

**main.rs 输出（保存到日志文件）：**

```
network: A
```

**proof_point_add.rs 输出：**

```
Proof size: <字节数> bytes
Proof generation time: <毫秒数> ms
Proof verification successful!
Proof verification time: <毫秒数> ms
```

**proof_point_mult.rs 输出（如果 network != "L2" 且 != "L4"）：**

```
Proof size: <字节数> bytes
Proof generation time: <毫秒数> ms
Proof verification successful!
Proof verification time: <毫秒数> ms
```

**main.rs 最终输出：**

```
====================================
Total proof size: <总字节数> bytes
Total proof generation time: <总毫秒数> ms
Total proof verification time: <总毫秒数> ms
====================================
```

---

## 三、完整输出示例（按时间顺序）

### 终端输出（Verbose 模式）

```
Running server.py and client.py for CNN network A on port 35000...
Starting Server...

[STARTING] Server is starting
[LISTENING] Server is listening on 127.0.0.1:35000
[WAITING] Waiting for client connection...
Server is ready.

**************************************************
Client: Connection established.

Client: Generating public-private keys...
Client: Encrypting data sample...
**************************************************

Server: [NEW CLIENT CONNECTION] ('127.0.0.1', 54321) connected.

**************************************************
Server: Encrypted data sample received.
Server: Performing inference on encrypted data...
**************************************************

**************************************************
Server: First conv. layer started!
Server: First conv. layer finished!
**************************************************

**************************************************
Server: First Activation layer started!
Server: First Activation layer finished!
**************************************************

**************************************************
Server: First AvgPooling started!
Server: First AvgPooling finished!
**************************************************

**************************************************
Server: Flattening started!
Server: Flattening finished!
**************************************************

**************************************************
Server: FC1 started!
Server: FC1 finished!
**************************************************

**************************************************
Server: Second Activation layer started!
Server: Second Activation layer finished!
**************************************************

**************************************************
Server: FC2 started!
Server: FC2 finished!
Server: Number of EC point multiplications: 1234
Server: Number of EC point additions: 5678
**************************************************

Server: The witnesses are saved in a file for generating proof with Rust

Navigating to proof generation directory...
Generating Proof...
```

### 日志文件输出（A_Run_YYYYMMDD-HHMMSS.log）

```
network: A

Proof size: 123456 bytes
Proof generation time: 1234 ms
Proof verification successful!
Proof verification time: 56 ms

Proof size: 234567 bytes
Proof generation time: 2345 ms
Proof verification successful!
Proof verification time: 78 ms

====================================
Total proof size: 358023 bytes
Total proof generation time: 3579 ms
Total proof verification time: 134 ms
====================================
```

---

## 四、关键文件和数据流

### 1. Python 文件执行顺序
- **Server.py**: 启动 → 监听 → 接收参数 → 执行推理 → 保存见证数据
- **Client.py**: 连接 → 生成密钥 → 加密数据 → 发送/接收 → 解密结果

### 2. 数据文件生成
- **JSON 文件**（由 Server.py 生成）：
  - `src/proof_generation/vPIN_proof_generation/src/rust_files/A/pointMult/weight.json`
  - `src/proof_generation/vPIN_proof_generation/src/rust_files/A/pointMult/point_mult_px_byte.json`
  - `src/proof_generation/vPIN_proof_generation/src/rust_files/A/pointMult/point_mult_py_byte.json`
  - `src/proof_generation/vPIN_proof_generation/src/rust_files/A/pointAdd/point_add_px_byte.json`
  - `src/proof_generation/vPIN_proof_generation/src/rust_files/A/pointAdd/point_add_py_byte.json`
  - `src/proof_generation/vPIN_proof_generation/src/rust_files/A/pointAdd/point_add_rx_byte.json`
  - `src/proof_generation/vPIN_proof_generation/src/rust_files/A/pointAdd/point_add_ry_byte.json`
  - `src/proof_generation/vPIN_proof_generation/src/rust_files/A/pointAdd/point_add_rz_byte.json`

### 3. Rust 程序执行
- **main.rs**: 解析参数 → 调用 proof_point_add → 调用 proof_point_mult → 输出总计
- **proof_point_add.rs**: 加载数据 → 生成证明 → 验证证明 → 返回结果
- **proof_point_mult.rs**: 加载数据 → 生成证明 → 验证证明 → 返回结果

---

## 五、错误处理

### 常见错误情况

1. **端口被占用**：
   ```
   Alert: Port 35000 is busy. Please select a different port.
   ```

2. **服务器启动失败**：
   ```
   [ERROR] Server failed to start: <错误信息>
   [ERROR] Address: ('127.0.0.1', 35000)
   ```

3. **客户端连接失败**：
   ```
   ConnectionRefusedError: [WinError 10061] 无法连接，因为目标计算机积极拒绝连接。
   ```

4. **Rust 编译错误**：
   - 输出到日志文件
   - 检查 `rust-toolchain.toml` 配置

---

## 六、验证正确运行的标志

### 成功标志：

1. ✅ Server 输出：`[LISTENING] Server is listening on 127.0.0.1:35000`
2. ✅ Client 输出：`Client: Connection established.`
3. ✅ Server 输出：`Server: [NEW CLIENT CONNECTION] ... connected.`
4. ✅ Server 完成所有层：所有 `**************************************************` 分隔的输出块都出现
5. ✅ Server 输出：`Server: The witnesses are saved in a file for generating proof with Rust`
6. ✅ 日志文件包含：`Proof verification successful!`（两次）
7. ✅ 日志文件包含：`Total proof size: ... bytes`

### 失败标志：

1. ❌ 端口被占用警告
2. ❌ 服务器启动错误
3. ❌ 连接被拒绝
4. ❌ Rust 编译错误
5. ❌ 证明验证失败

---

## 七、时间线总结

```
T0: 脚本启动，解析参数
T1: Server.py 启动，绑定端口
T2: Server 开始监听
T3: Client.py 启动，连接服务器
T4: 密钥生成和加密
T5-T10: CNN 推理过程（卷积、激活、池化、展平、FC1、激活、FC2）
T11: 保存见证数据
T12: 切换到 Rust 目录
T13: 编译 Rust 程序（首次运行）
T14: 执行证明生成和验证
T15: 输出最终结果到日志文件
```

---

## 八、注意事项

1. **Verbose 模式** (`-v`)：
   - Server.py 和 Client.py 的输出直接显示在终端
   - Rust 程序的输出重定向到日志文件

2. **端口检查**：
   - 脚本会检查端口是否可用
   - 如果端口被占用，会显示警告但继续尝试

3. **服务器等待**：
   - 脚本会等待最多 10 秒让服务器启动
   - 每秒检查一次端口状态

4. **日志文件位置**：
   - 日志文件保存在 `logs/` 目录
   - 文件名格式：`A_Run_YYYYMMDD-HHMMSS.log`

