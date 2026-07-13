# 2^30 规模数据 mmap 持久化方案设计

## 一、存储开销分析

### 1.1 实际测量结果
基于 `eva_data_size.py` 的测量：
- **数据值 s**: 1-4 字节（平均2字节）
- **tag_i**: 16 字节（128 bits）
- **BLS签名 sigma_i**: 46 字节（序列化）
- **序列化后（含字典key）**: 89 字节

### 1.2 2^30 次 append 开销
- **数据项总数**: 1,073,741,824 (约10.7亿条)
- **内存存储（Python字典）**: 100.00 GB
- **mmap持久化（固定记录）**: 72.00 GB
- **内存限制**: 8 GB
- **结论**: 必须使用 mmap 进行持久化

## 二、mmap 存储方案设计

### 2.1 文件结构

#### 2.1.1 主数据文件 (`db_mmap.dat`)
```
[文件头 1024 字节]
  - 魔数: 4 字节 ("VADS")
  - 版本号: 4 字节
  - 记录总数: 8 字节 (uint64)
  - 记录大小: 4 字节 (固定72字节)
  - 文件创建时间: 8 字节 (timestamp)
  - 最后更新时间: 8 字节 (timestamp)
  - 保留字段: 988 字节

[数据记录区]
  记录0: [索引4字节][数据值4字节][tag16字节][签名46字节][对齐2字节] = 72字节
  记录1: [索引4字节][数据值4字节][tag16字节][签名46字节][对齐2字节] = 72字节
  ...
  记录N-1: [索引4字节][数据值4字节][tag16字节][签名46字节][对齐2字节] = 72字节
```

**记录格式（72字节固定大小）**:
- **索引 i** (4字节, uint32): 数据项索引，最大支持 2^32-1
- **数据值 s** (4字节, int32): 数据值（支持负数，实际值通常较小）
- **tag_i** (16字节): 128位标签
- **BLS签名 sigma_i** (46字节): 序列化后的BLS签名
- **对齐填充** (2字节): 保证记录对齐到8字节边界

**文件大小计算**:
- 文件头: 1024 字节
- 数据区: 72 字节 × 1,073,741,824 = 77,309,411,328 字节
- **总大小**: 约 72.00 GB

#### 2.1.2 索引文件 (`db_index.dat`) - 可选优化
如果需要快速查找（按索引范围查询），可以创建稀疏索引：
- 每 1024 条记录一个索引项
- 索引项: [起始索引4字节][文件偏移8字节] = 12字节
- 索引项数: 1,073,741,824 / 1024 = 1,048,576 项
- 索引文件大小: 12 × 1,048,576 = 12.58 MB（可忽略）

#### 2.1.3 元数据文件 (`db_metadata.pkl`)
存储 server_state 的其他字段：
- `Acc_R`: RSA accumulator 值（384字节）
- `z_star`: 缓存的 z* 值（384字节）
- `R`: 已删除的 tag 集合（通常很小，可忽略）
- `vk`: 验证密钥（需要持久化，但通常很小）

### 2.2 访问模式

#### 2.2.1 随机访问（Query操作）
```python
# 通过索引 i 直接计算偏移量
offset = 1024 + (i * 72)  # 文件头 + 记录偏移
# 直接读取72字节记录，O(1)时间复杂度
```

#### 2.2.2 顺序访问（批量Query）
```python
# 批量读取连续记录
start_offset = 1024 + (start_i * 72)
end_offset = 1024 + ((end_i + 1) * 72)
# 一次性读取，利用操作系统页面缓存
```

#### 2.2.3 Append操作
```python
# 追加新记录到文件末尾
# 1. 更新文件头中的记录总数
# 2. 写入新记录（72字节）
# 3. 同步到磁盘（msync）
```

### 2.3 内存管理策略

#### 2.3.1 按需加载
- **不预加载**: 不将整个文件加载到内存
- **页面缓存**: 依赖操作系统的页面缓存机制
- **LRU缓存**: 在应用层维护最近访问记录的缓存（可选）

#### 2.3.2 内存映射模式
```python
# 使用 mmap 的访问模式
mmap.ACCESS_READ  # 只读模式（Query操作）
mmap.ACCESS_WRITE # 读写模式（Append操作）
mmap.ACCESS_COPY  # 写时复制（安全模式）
```

#### 2.3.3 内存占用估算
- **mmap映射**: 虚拟内存映射，不占用物理内存
- **实际占用**: 仅访问的页面会被加载到物理内存
- **页面大小**: 通常4KB，访问一条记录最多加载2个页面（8KB）
- **1000次随机查询**: 最多 8MB 物理内存（假设无缓存命中）

## 三、实现方案

### 3.1 核心接口设计

```python
class MmapDB:
    """基于mmap的数据库存储"""
    
    def __init__(self, db_path):
        """初始化mmap数据库"""
        # 打开或创建mmap文件
        # 映射文件到内存
        pass
    
    def append(self, i, s, tag_i, sigma_i_bytes):
        """追加新记录"""
        # 1. 计算偏移量
        # 2. 写入记录
        # 3. 更新文件头
        # 4. 同步到磁盘
        pass
    
    def get(self, i):
        """获取记录（O(1)随机访问）"""
        # 1. 计算偏移量
        # 2. 从mmap读取72字节
        # 3. 解析记录
        # 4. 返回 (s, tag_i, sigma_i_bytes)
        pass
    
    def get_batch(self, indices):
        """批量获取记录"""
        # 优化：按偏移量排序，减少页面跳跃
        pass
    
    def close(self):
        """关闭mmap文件"""
        # 同步并关闭
        pass
```

### 3.2 与现有代码集成

**重要原则**: **不修改 `append` 和 `query` 函数**，在调用前通过 mmap 准备好数据。

#### 3.2.1 使用方式

**方案A：Append时写入mmap，Query前从mmap加载到内存**

```python
# 1. Append阶段：同时写入mmap文件（不修改append函数）
for i in range(dataset_size):
    result = append(sk, s, server_state)  # 原有函数不变
    # 在append后，将数据写入mmap文件
    if result:
        i, s, sigma_i, tag_i = result
        sigma_bytes = vk['group'].serialize(sigma_i)
        mmap_db.append(i, s, tag_i, sigma_bytes)

# 2. Query前：从mmap加载数据到server_state['DB']（预热）
# 在测试query性能前，从mmap文件加载数据到内存
def load_from_mmap_to_memory(mmap_db, server_state, vk, indices):
    """从mmap文件加载数据到server_state['DB']，确保数据在内存中"""
    for i in indices:
        if i not in server_state['DB']:  # 如果内存中没有，从mmap加载
            s, tag_i, sigma_i_bytes = mmap_db.get(i)
            sigma_i = vk['group'].deserialize(sigma_i_bytes)
            server_state['DB'][i] = (s, sigma_i, tag_i)

# 3. Query阶段：直接使用server_state['DB']（不修改query函数）
# 此时数据已在内存中，query函数正常工作
query_result = query(vk, server_state, idx)  # 原有函数不变
```

**方案B：完全从mmap加载到内存后测试**

```python
# 1. Append阶段：只写入mmap，不写入server_state['DB']
# 或者使用轻量级的server_state['DB']（只存储索引）

# 2. 测试前：从mmap完整加载数据到server_state['DB']
def load_all_from_mmap(mmap_db, server_state, vk):
    """从mmap文件加载所有数据到server_state['DB']"""
    total_records = mmap_db.get_total_records()
    for i in range(total_records):
        s, tag_i, sigma_i_bytes = mmap_db.get(i)
        sigma_i = vk['group'].deserialize(sigma_i_bytes)
        server_state['DB'][i] = (s, sigma_i, tag_i)

# 3. Query阶段：使用已加载的server_state['DB']
query_result = query(vk, server_state, idx)  # 原有函数不变
```

#### 3.2.2 预热机制（Warmup）

在测试query性能前，确保数据已从mmap加载到内存：

```python
def warmup_for_query(mmap_db, server_state, vk, test_indices):
    """
    预热：从mmap加载测试数据到server_state['DB']
    确保在测量query时间时，数据已在内存中
    """
    print("  从mmap加载测试数据到内存...")
    for idx in test_indices:
        if idx not in server_state['DB']:
            s, tag_i, sigma_i_bytes = mmap_db.get(idx)
            sigma_i = vk['group'].deserialize(sigma_i_bytes)
            server_state['DB'][idx] = (s, sigma_i, tag_i)
    print("  预热完成，数据已在内存中")
```

#### 3.2.3 关键优势

- **不修改核心函数**: `append` 和 `query` 函数保持原样
- **透明集成**: mmap 作为数据持久化和加载层
- **准确测量**: query 时间只测量算法执行，不包括 mmap I/O
- **灵活性**: 可以选择完全加载或按需加载

### 3.3 性能优化

#### 3.3.1 批量操作优化
- **批量Query**: 按偏移量排序，减少页面跳跃
- **批量Append**: 缓冲区批量写入，减少系统调用

#### 3.3.2 缓存策略
- **LRU缓存**: 缓存最近访问的N条记录（如1000条）
- **预取**: 顺序访问时预取下一页

#### 3.3.3 并发控制
- **读写锁**: 支持多读单写
- **原子操作**: Append操作使用文件锁保证原子性

## 四、测试方案

### 4.1 功能测试
1. **Append测试**: 执行2^30次append，验证数据完整性
2. **Query测试**: 随机查询1000条记录，验证正确性
3. **批量Query测试**: 批量查询，验证性能
4. **持久化测试**: 重启后重新打开mmap文件，验证数据恢复

### 4.2 性能测试

#### 4.2.1 重要：mmap页面加载时间不计入query时间
**关键原则**: mmap内存映射的读写时间（页面加载）不应该计算在query的时间开销内。

**原因**:
- mmap首次访问某个页面时会发生页面错误（page fault），需要从磁盘加载页面到内存
- 这个磁盘I/O时间不应该计入query算法的计算时间
- query时间应该只测量算法本身的执行时间（数据已在内存中）

**实现方法**:
1. **预热（Warmup）**: 在测量query时间前，先访问所有要测试的记录，确保页面已加载到内存
2. **页面缓存**: 依赖操作系统的页面缓存，确保数据在内存中
3. **时间测量**: 只测量query函数本身的执行时间，不包括mmap的页面加载

#### 4.2.2 测试流程
1. **内存占用**: 监控实际物理内存使用
2. **预热阶段**: 
   - 打开mmap文件
   - 访问所有测试记录（确保页面加载到内存）
   - 等待页面缓存稳定
3. **查询延迟测量**: 
   - 在预热后测量单次和批量查询的延迟
   - 确保测量时数据已在内存中（页面缓存命中）
4. **Append吞吐**: 测量append操作的吞吐量
5. **磁盘I/O**: 监控磁盘读写量（区分预热阶段和查询阶段）

#### 4.2.3 修改测试代码示例
在 `src/main.py` 的 `run_trials` 函数中，在调用 query 前先准备好数据：

```python
def run_trials(dataset_size, vk, sk, server_state, num_trials=50, mmap_db=None):
    # ... append阶段 ...
    # 注意：append时可以选择同时写入mmap_db，但不修改append函数本身
    # 在append循环后：
    #   for result in append_results:
    #       if mmap_db:
    #           i, s, sigma_i, tag_i = result
    #           sigma_bytes = vk['group'].serialize(sigma_i)
    #           mmap_db.append(i, s, tag_i, sigma_bytes)
    
    # 准备测试索引
    if mmap_db:
        # 如果使用mmap，需要从mmap加载数据到server_state['DB']
        indices = list(range(dataset_size))  # 或从mmap_db获取
        # 预热：从mmap加载测试数据到内存
        test_indices = random.sample(indices, min(len(indices), num_trials * 2))
        warmup_for_query(mmap_db, server_state, vk, test_indices)
    else:
        indices = list(server_state['DB'].keys())
    
    # 现在开始测量query时间（数据已在内存中，不修改query函数）
    for _ in range(num_trials):
        idx = random.choice(indices)
        
        start = time.perf_counter()
        query_result = query(vk, server_state, idx)  # 原有函数，不修改
        end = time.perf_counter()
        # 此时测量的时间不包括mmap页面加载时间
        # 因为数据已经通过预热加载到server_state['DB']中了
        results['query_times'].append((end - start) * 1000)
        # ... 后续逻辑 ...
```

**关键点**:
- **不修改 `append` 和 `query` 函数**：保持原有函数不变
- **预热在测量前完成**：从mmap加载数据到 `server_state['DB']`
- **query时间测量时数据已在内存**：通过 `server_state['DB']` 访问，不涉及mmap I/O
- **测量的时间只包括算法执行时间**：不包括磁盘I/O和mmap页面加载

### 4.3 压力测试
1. **大文件测试**: 验证72GB文件的mmap映射
2. **并发测试**: 多线程并发查询
3. **内存限制测试**: 在8GB内存限制下运行

## 五、实施步骤

### 5.1 第一阶段：基础实现
1. 实现 `MmapDB` 类的基本功能
2. 实现固定大小记录格式（72字节）
3. 实现文件头和记录读写
4. 集成到 `append` 和 `query` 函数

### 5.2 第二阶段：优化
1. 实现批量操作优化
2. 添加LRU缓存
3. 实现并发控制

### 5.3 第三阶段：测试和验证
1. 功能测试
2. 性能测试
3. 2^30规模完整测试

## 六、注意事项

### 6.1 文件大小限制
- **32位系统**: 最大2GB（mmap限制）
- **64位系统**: 无限制（支持72GB文件）
- **文件系统**: 确保文件系统支持大文件（如ext4、NTFS）

### 6.2 数据一致性
- **Append原子性**: 使用文件锁或事务日志
- **崩溃恢复**: 文件头包含校验和，用于检测损坏
- **备份策略**: 定期备份元数据文件

### 6.3 性能考虑
- **页面大小**: 利用4KB页面大小，一次加载多条记录
- **预分配**: 预先分配文件空间，避免动态扩展
- **同步策略**: 根据需求选择同步或异步写入

### 6.4 测试时间测量规范
- **预热阶段**: 在测量query时间前，必须先预热mmap文件
- **时间测量**: query时间只测量算法执行时间，不包括mmap页面加载
- **页面缓存**: 确保测试时数据已在内存中（通过预热）
- **多次测量**: 预热后多次测量取平均值，排除首次访问的影响

