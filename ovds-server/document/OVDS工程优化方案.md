# OVDS 工程优化方案

## 一、文档说明

本文档在 VADS 密码协议（`src/vads_lib.py`）之上，定义**大文件/批量文件**场景下的工程优化策略，包括并行 Append/Update、会话与版本管理、冲突消解、取消回退，以及大文件下载验证策略。

**相关文档**：

| 文档 | 内容 |
|------|------|
| `OVDS协议完整流程.md` | 密码层协议 |
| `OVDS实际应用多模态数据方案.md` | 多模态预处理与分块 |
| `OVDS数据托管服务器技术文档.md` | 托管服务架构、认证与 ACL |

---

## 二、设计目标

| 目标 | 说明 |
|------|------|
| **高吞吐上传** | 1GB 级文件分块并行 Append，避免 `cnt` 竞争 |
| **可控更新** | 批量/大文件 Update 保证一致初始状态与可追踪进度 |
| **可取消/可回退** | 用户取消或失败时不污染已提交版本 |
| **并发写安全** | 重复/同时提交按规则消解，同分片以权威版本为准 |
| **高效验证下载** | 优先聚合证明；不适合聚合时并行传输 + 本地验证 |

---

## 三、核心概念

### 3.1 两层状态

```
┌─────────────────────────────────────────┐
│  会话层（Session / Revision）            │  ← 工程优化主战场
│  草稿、进度、冲突、取消、回退              │
├─────────────────────────────────────────┤
│  VADS 层（DB / R / Acc_R / cnt）          │  ← vads_lib 协议状态
└─────────────────────────────────────────┘
```

- **会话层**：用户可见的「上传任务 / 修改任务」，可先写暂存区，再一次性提交 VADS。
- **VADS 层**：仅在**提交（Commit）**时修改；Append 不碰 `Acc_R`，Update 批量累计 `z*`。

### 3.2 标识体系

| 标识 | 说明 |
|------|------|
| `tenant_id` | 租户，对应一套 VADS 实例（`vk/sk/server_state`） |
| `file_id` | 逻辑文件 |
| `file_revision` | 文件单调递增版本号（整数，从 1 开始） |
| `chunk_index` | 文件内分片序号（0..N-1） |
| `vads_index` | VADS `DB` 键 `i` |
| `session_id` | 一次上传/修改任务 ID |
| `chunk_revision` | 分片级版本（随 `file_revision` 或独立递增） |

---

## 四、大文件与批量上传（并行 Append）

### 4.1 分块策略

| 文件大小 | 默认块大小 | 块数示例 |
|----------|-----------|----------|
| < 10 MB | 不分块 | 1 |
| 10 MB ~ 100 MB | 1 MB | 10 ~ 100 |
| > 100 MB | 1 ~ 4 MB | 1GB ≈ 256~1024 |

### 4.2 索引预分配（解决 `cnt` 并行）

**原则**：`i` 不必等于当前 `cnt`；`append_server` 只验签，不检查 `i == cnt`。

上传会话创建时，协调器**原子预占**索引区间：

```
total_chunks = N
index_base   = atomic_reserve_cnt(tenant_id, N)   # 原 cnt，预占后 cnt += N
chunk k 的 vads_index = index_base + k
```

各 Worker 并行：

```
Worker:
  1. 读取分配好的 vads_index（固定）
  2. sign_block(sk, i, s) → (σ_i, tag_i)    # 不调用会 cnt++ 的 append_client
  3. 上传 (i, s, σ_i, tag_i)

Commit 协调器:
  append_server(vk, state, i, s, σ_i, tag_i)   # 可并行调用，i 互不重复
```

**约束**：

- 同一会话内 `vads_index` 不重叠。
- 会话取消且未提交：释放预占区间（见 §6），或标记为空洞（`cnt` 不回退，允许空洞）。

### 4.3 批量多文件并行

```
批量上传 = 多个 session 并行
每个 file_id 独立 session、独立 index 区间预占
共享同一租户 VADS 实例（一个 Acc_R）
```

| 维度 | 策略 |
|------|------|
| 文件间 | 完全并行 |
| 文件内分片 | 并行 Append |
| `cnt` | 租户级原子发号器（Redis INCR / DB 行锁） |

### 4.4 上传会话状态机

```
CREATED → UPLOADING → READY → COMMITTING → COMMITTED
                ↓                    ↓
            CANCELLED            FAILED
```

| 状态 | VADS 是否写入 |
|------|---------------|
| UPLOADING | ❌ 仅暂存分片元数据 + 可选对象缓存 |
| COMMITTING | ✅ 批量 append_server |
| COMMITTED | ✅ 切换 file_index 指针 |
| CANCELLED | ❌ 不写 VADS |

---

## 五、大文件与批量更新（Update 优化）

### 5.1 两种更新路径

| 路径 | 适用 | VADS 操作 |
|------|------|-----------|
| **原地 Update** | 少量块变更（如 < 10%） | `update` / 批量 Update |
| **新版本 Append（COW）** | 大范围变更（> 50%） | 预占新索引区间，并行 Append，切换 `file_revision` |

COW 不动 `Acc_R` 的撤销链更简单，大改版**优先 COW**；小范围用批量 Update。

### 5.2 批量 Update 与 `z*` 累计

对**不同 `vads_index`**、**同一会话内每个索引只改一次**：

```
阶段 1（并行）:
  对每个 i: 读 DB[i]、验旧签名、算 (s', σ', tag')

阶段 2（原子提交）:
  for each i: DB[i] ← 新三元组
  R ← R ∪ {所有旧 tag}
  z* ← z* · ∏ HPrime(旧 tag)     # 一次累计
  Acc_R ← h^z* mod n              # 只算一次
```

**禁止**：同一会话、同一 `i` 两条并行 Update 都基于同一旧 tag 累计（会双乘 `HPrime(tag_旧)`）。

**同索引连续改两次**（合法但有序）：

```
第 1 次: 废 tag_A → tag_X
第 2 次: 废 tag_X → tag_Y
z* 累计: HPrime(tag_A) · HPrime(tag_X)   # 链式，非重复乘 tag_A
```

### 5.3 初始值与进度（会话一致性）

每个修改会话携带：

```json
{
  "session_id": "sess-uuid",
  "file_id": "f-001",
  "base_file_revision": 3,
  "base_manifest_hash": "sha256(...)",
  "op": "update",
  "chunks": [
    {
      "chunk_index": 5,
      "base_vads_index": 105,
      "base_tag_fingerprint": "h(tag)",
      "expected_chunk_revision": 3
    }
  ]
}
```

**提交前校验（OCC 乐观并发控制）**：

1. `file_index.revision == base_file_revision`
2. 每个 `base_vads_index` 仍对应当前 manifest
3. 可选：DB 中 `tag` 指纹与 `base_tag_fingerprint` 一致

不满足 → **409 Conflict**，客户端刷新后重试。

比纯客户端时间戳更可靠；时间戳仅作辅助排序（见 §5.4）。

### 5.4 并发重复提交与冲突消解

**问题**：同一文件/分片被多次、同时提交修改。

**推荐方案：服务器分配 `commit_seq` + 分片级 LWW**

| 步骤 | 说明 |
|------|------|
| 1 | 客户端带 `client_ts`（毫秒）和 `idempotency_key` |
| 2 | 提交进入租户级**提交队列**（按 `file_id` 分片） |
| 3 | 服务器分配单调 `commit_seq`（权威顺序） |
| 4 | **同一 `chunk_index`**：仅 `commit_seq` 最大者生效 |
| 5 | 同 `commit_seq` 冲突（极少）：`client_ts` 大者优先；再 Tie-break `session_id` 字典序 |

**优于纯时间戳的原因**：客户端时钟不可信；`commit_seq` 由服务端生成，顺序确定。

**幂等**：相同 `idempotency_key` 重复 POST 返回同一 `commit_result`，不二次写 VADS。

### 5.5 修改进度模型

```json
{
  "session_id": "sess-uuid",
  "progress": {
    "total_chunks": 1024,
    "uploaded_chunks": 800,
    "committed_chunks": 0,
    "failed_chunks": [812, 813],
    "phase": "UPLOADING"
  }
}
```

| 阶段 | 进度含义 |
|------|----------|
| UPLOADING | 分片到达暂存区 |
| COMMITTING | 写入 VADS（`committed_chunks` 递增） |
| COMMITTED | `file_revision++`，manifest 切换 |

支持**断点续传**：已上传分片带 `chunk_upload_token`，跳过已 READY 块。

---

## 六、取消与回退

### 6.1 取消（Cancel）

| 会话状态 | 取消行为 |
|----------|----------|
| UPLOADING / READY | 删暂存，释放预占索引（若实现回收）或留空洞；**不写 VADS** |
| COMMITTING | 若未完成：Abort 会话，已写入块记为 orphan（后台清理）；**不切换 manifest** |
| COMMITTED | 不可 Cancel，只能新版本回退 |

用户侧：API `DELETE /sessions/{session_id}` → 状态 `CANCELLED`。

### 6.2 回退（Rollback）

**不删除 VADS 历史数据**（Append-only 友好），采用 **manifest 指针回退**：

```
file_index:
  current_revision: 4
  revisions:
    3: { manifest_hash, chunk_map, created_at }
    4: { ... }   # 当前

回退到 revision 3:
  current_revision ← 3
  查询时用 revision 3 的 chunk_map
```

| 方式 | 说明 |
|------|------|
| **Manifest 回退** | 推荐，O(1) 切换 |
| **VADS 层回滚** | 不推荐，需逆向 Update，破坏 `R`/`Acc_R` |

### 6.3 失败恢复

```
COMMITTING 中断:
  - 记录 committed_chunks 位图
  - 重试会话：仅提交未完成块
  - 全部完成后统一累计 z*（Update 路径）或一次性切换 manifest（Append 路径）
```

---

## 七、大文件下载与 Verify 策略

### 7.1 验证层次

```
1. VADS 层：每分片完整性（BLS + 非成员证明）
2. 应用层：重组后 SHA-256 == manifest.file_hash
```

**不能**只做整文件哈希而跳过 VADS 验证。

### 7.2 策略选择（聚合 vs 并行单片）

| 条件 | 策略 |
|------|------|
| 批大小 ≤ 64 且网络 RTT 高 | **`query_star` + `verify_star`（聚合）** |
| 批大小很大 / 聚合超时 / 移动端弱 CPU | **并行单片 `query` + 本地 `verify`** |
| 千兆内网、多核客户端 | **多批并行 `query_star`** + 每批 `verify_star` |

**默认推荐**（1GB / 1024 块）：

```
batch_size = 32
批次数 = 32
每批: query_star(J) → verify_star
批间: 4~8 路 HTTP 并行下载
本地: 4 路并行 verify_star（CPU 允许时）
重组 → SHA-256
```

### 7.3 决策伪代码

```python
def choose_verify_strategy(chunk_count, rtt_ms, cpu_cores, agg_timeout_ms):
    if chunk_count <= 8:
        return "single_verify"           # 少量块直接逐片
  batch = min(64, max(16, chunk_count // cpu_cores))
    if rtt_ms > 50 and batch <= 64:
        return "aggregate", batch        # 聚合省 RTT
    if cpu_cores >= 4 and chunk_count > 256:
        return "parallel_single", 8      # 多连接单片流式
    return "aggregate", 32               # 默认
```

### 7.4 性能参考（密码层粗算，小整数 s）

| 1GB 场景 | 串行逐片 verify | 32 块/批 verify_star |
|----------|----------------|----------------------|
| 密码耗时 | ~24 s | ~3~8 s |
| 证明大小 | 小但请求多 | 中等，请求少 |

聚合证明大小随批大小亚线性增长；批过大时改并行单片或拆批。

### 7.5 增量下载

仅 `file_revision` 变更的分片加入 `J`；未变块可跳过 VADS 查询（客户端缓存 manifest）。

---

## 八、批量提交 API 约定（工程层）

### 8.1 创建上传会话

```
POST /v1/tenants/{tid}/files/upload-sessions
Body: { file_name, file_size, chunk_size, file_hash, client_ts }
→ { session_id, index_base, total_chunks, chunk_upload_urls[] }
```

### 8.2 提交分片

```
PUT .../sessions/{sid}/chunks/{chunk_index}
Headers: Idempotency-Key, X-Chunk-Hash
Body: 二进制 或 { s, sigma, tag } 由服务端代签
```

### 8.3 提交会话

```
POST .../sessions/{sid}/commit
Body: { base_file_revision?, idempotency_key }
→ { file_id, file_revision, manifest_hash }
```

### 8.4 批量修改

```
POST /v1/tenants/{tid}/files/{fid}/update-sessions
Body: { base_file_revision, chunks: [{chunk_index, ...}], client_ts }
→ 同上传会话模型，commit 时走 Update 批量或 COW Append
```

---

## 九、实现模块划分

```
upload-coordinator     # 索引预占、会话状态、commit_seq
chunk-staging          # 暂存区（取消不写 VADS）
vads-writer            # append_server / batch_update
manifest-service       # file_revision、chunk_map、回退
verify-orchestrator    # 下载批调度、聚合/并行策略
conflict-resolver      # OCC + LWW + 幂等
```

### 9.1 待扩展 `vads_lib` 封装

| 函数 | 用途 |
|------|------|
| `sign_block(sk, i, s)` | 显式 `i` 签名，不修改 `cnt` |
| `batch_append_server(...)` | 并行安全批量入库 |
| `batch_update_server(...)` | 累计 `z*` 的一次性 Update |

---

## 十、风险与约束

| 风险 | 缓解 |
|------|------|
| 预占索引空洞 | 定期压缩或接受稀疏 `DB` |
| 同索引并发双写 | OCC + `commit_seq` LWW |
| `z*` 双计 | 批量 Update 去重 `i`；同 `i` 链式有序 |
| 大整数 `s` 签名慢 | 监控 P99；考虑块大小上限或哈希入签 |
| COMMITTING 中断 | 位图断点续提 |

---

## 十一、总结

| 场景 | 方案要点 |
|------|----------|
| **大文件 Append** | 预占 `index_base..index_base+N-1`，并行 `append_server` |
| **批量文件** | 每文件独立 session，共享租户 VADS |
| **小改 Update** | 并行算签名 + 批量累计 `z*` 一次提交 |
| **大改** | COW 新索引 Append + manifest 切换 |
| **并发冲突** | `base_revision` OCC + 服务端 `commit_seq` LWW |
| **取消** | 未 COMMITTED 不写 VADS |
| **回退** | manifest 指针回退，不逆向 VADS |
| **下载验证** | 默认 `verify_star` 分批；必要时并行单片 |
