# LLM 可验证推理：EC gadget 与模型承诺的替换成本建模

> 目标：把「模型替换 / 降精度 / 跳层 / 伪造 trace」这类作弊行为，转成可估算的算力成本、验证成本与收益模型。建模优先参考仓库当前实现：
> - 模型承诺： [src/cp-snark-full/src/commitment.rs](../../src/cp-snark-full/src/commitment.rs)
> - L1 绑定： [src/cp-snark-full/src/circuit/bind_l1.rs](../../src/cp-snark-full/src/circuit/bind_l1.rs)
> - EC gadget 证明/验证： [src/cp-snark-full/src/prove/ec.rs](../../src/cp-snark-full/src/prove/ec.rs)、[src/cp-snark-full/src/verify/ec.rs](../../src/cp-snark-full/src/verify/ec.rs)

---

## 1. 建模目标

对一个声称为 $M$ 的推理服务，攻击者可能替换为更小的模型 $M'$，或者用更低精度/更少算子/更少 token 伪造推理结果。我们需要把这类作弊的“收益”和“代价”建模为下面三类量：

1. 模型替换收益 $G$：攻击者节省的算力、显存、带宽或延迟收益。
2. 替换算力成本 $C_{
m replace}$：攻击者为了伪造一份看似正确的证明，需要额外付出的计算成本。
3. 验证成本 $C_{
m verify}$：验证者为了检测替换，需要付出的打开、重算与审计成本。

最终目标是建立一个可执行的“威慑条件”：

$$
p_{
m eff}(P+L) + C_{
m audit	ext{-}forge} > G_{
m replace}
$$

其中：
- $p_{
m eff}$ 是被抽中并检查的有效概率；
- $P$ 是押金或惩罚；
- $L$ 是声誉损失；
- $C_{
m audit	ext{-}forge}$ 是攻击者为对抗审计而必须额外支付的伪造成本。

---

## 2. 先对齐仓库中的代码语义

### 2.1 模型承诺：绑定权重向量

仓库里的模型承诺逻辑在 [src/cp-snark-full/src/commitment.rs](../../src/cp-snark-full/src/commitment.rs) 中：

- `commit_model(weights)` 将权重向量 $\mathbf W^*$ 变成一组标量，然后做 Pedersen 承诺；
- `verify_pedersen_open_model` 用 opening 重新算 commitment 并检查是否一致；
- 这一步把“模型权重是否被替换”绑定到了一个全局承诺值 $\mathrm{cm}_W$。

这意味着一个替换模型 $M'$ 的攻击者，至少要面对两种可能：

- 直接伪造 $\mathrm{cm}_W$：需要知道对应 weight 序列，或者至少能构造一个能通过 opening 检查的替代向量；
- 只伪造推理输出而不改权重：则后续 L1/EC 绑定会暴露不一致。

### 2.2 L1 绑定：PtMul 乘子与权重叶子绑定

仓库里的 L1 绑定在 [src/cp-snark-full/src/circuit/bind_l1.rs](../../src/cp-snark-full/src/circuit/bind_l1.rs) 中：

- 对 Conv 的 PtMul 槽，乘子直接来自某个权重叶子；
- 对 FC1/FC2 的 PtMul 槽，乘子来自一个由 $\gamma'$ 线性组合得到的 RLC 列。

对应公式可抽象为：

$$
 a_j =
 \begin{cases}
 W^*_{j \bmod 9}, & j \in [0,18) \\
 \sum_{i=0}^{15} (\gamma')^i W^*_{9+p\cdot 16 + i}, & j \in [18,146) \\
 \sum_{i=0}^{9} (\gamma')^i W^*_{1049+p\cdot 10 + i}, & j \in [146,178)
 \end{cases}
$$

这说明：如果服务器把权重替换成 $\mathbf W' \ne \mathbf W^*$，那么它必须让这些 PtMul witness 仍然与新权重的某个有效映射一致。否则 L1 绑定失败。

### 2.3 EC gadget：证明/验证成本集中在 PtMul / PtAdd

仓库里的 EC proof 路径在 [src/cp-snark-full/src/prove/ec.rs](../../src/cp-snark-full/src/prove/ec.rs) 和 [src/cp-snark-full/src/verify/ec.rs](../../src/cp-snark-full/src/verify/ec.rs) 中：

- `prove_ec_batch` 把工作拆成点加和点乘子电路；
- 证明成本随 `num_ptmul` 与 `num_ptadd` 增长；
- 验证成本同样以子电路为单位。

因此，建模时把 EC gadget 的成本看成：

$$
C_{
m EC}^{
m prove} = n_{
m ptmul} \cdot c_{
m ptmul} + n_{
m ptadd} \cdot c_{
m ptadd}
$$

$$
C_{
m EC}^{
m verify} = n_{
m ptmul}^{(a)} \cdot c_{
m ptmul}^{(v)} + n_{
m ptadd}^{(a)} \cdot c_{
m ptadd}^{(v)}
$$

其中 $c_{
m ptmul}$ 和 $c_{
m ptadd}$ 是“单位 gadget 成本”。

---

## 3. 基础变量定义

### 3.1 模型与推理变量

- $M$：声称使用的模型；
- $M'$：替代模型；
- $N_W$：声称模型参数量；
- $N_W'$：替代模型参数量；
- $C_{
m infer}(M)$：诚实推理一次的算力/费用；
- $C_{
m infer}(M')$：替代模型推理一次的算力/费用；
- $G_{
m replace}$：模型替换收益。

### 3.2 承诺与绑定变量

- $C_{
m comm}(N_W)$：全模型承诺成本；
- $C_{
m open}(k)$：审计中打开 $k$ 个权重/trace 叶子的成本；
- $C_{
m replay}(u)$：重算一个审计单元 $u$ 的成本；
- $C_{
m audit	ext{-}forge}$：伪造审计结果的额外成本。

### 3.3 验证变量

- $k$：每轮抽样的审计单元数；
- $N$：总审计单元数；
- $t$：被替换/作弊的单元数；
- $\rho$：审计频率；
- $p_{
m hit}$：抽中作弊单元的概率；
- $p_{
m eff}=\rho \cdot p_{
m hit}$：有效检测概率。

---

## 4. 模型替换收益建模

### 4.1 直接收益

最简单的替换收益是“算力节省”：

$$
G_{
m replace}^{
m comp} = C_{
m infer}(M) - C_{
m infer}(M')
$$

如果攻击者使用更小模型、更低精度或跳层，通常有：

$$
C_{
m infer}(M') \ll C_{
m infer}(M)
$$

### 4.2 额外收益

对于 LLM 场景，还应该加上：

- 显存节省；
- 带宽节省；
- 延迟降低；
- 小模型可同时服务更多并发。

可写成：

$$
G_{
m replace} = G_{
m replace}^{
m comp} + G_{
m mem} + G_{
m bw} + G_{
m latency}
$$

### 4.3 经验化近似

在工程建模里可以先取：

- 70B → 7B：$G \approx 0.8 \sim 0.95 \cdot C_{
m infer}(M)$；
- FP16 → INT4：$G \approx 0.5 \sim 0.75 \cdot C_{
m infer}(M)$；
- 跳过部分层：$G \approx \frac{k}{n_{\ell}} \cdot C_{
m infer}(M)$。

---

## 5. 替换算力成本建模

### 5.1 诚实执行成本

诚实服务端需要支付：

$$
C_{
m honest} = C_{
m infer}(M) + C_{
m commit}(N_W) + C_{
m EC}^{
m prove} + C_{
m trace}
$$

其中：
- $C_{
m infer}(M)$ 是实际推理成本；
- $C_{
m commit}(N_W)$ 是模型承诺成本；
- $C_{
m EC}^{
m prove}$ 是 EC gadget 证明成本；
- $C_{
m trace}$ 是 trace / activation / decode 记录成本。

### 5.2 作弊方的伪造成本

替换模型后，作弊方若想让证明“看起来”通过，必须至少支付：

$$
C_{
m replace}^{
m attack} = C_{
m infer}(M') + C_{
m forge	ext{-}commit} + C_{
m forge	ext{-}trace} + C_{
m forge	ext{-}EC}
$$

其中：

1. $C_{
m infer}(M')$：用小模型做实际推理；
2. $C_{
m forge	ext{-}commit}$：伪造模型承诺或 opening；
3. $C_{
m forge	ext{-}trace}$：伪造中间激活/trace；
4. $C_{
m forge	ext{-}EC}$：为 EC 子电路构造可以通过验证的 witness。

对于“严格绑定”设计，$C_{
m forge	ext{-}commit}$ 和 $C_{
m forge	ext{-}EC}$ 不应低于审计抽样的重算成本：

$$
C_{
m audit	ext{-}forge} \approx C_{
m open}(k) + C_{
m replay}(k) + C_{
m EC}^{
m verify}(k)
$$

这是因为一旦审计点落在被替换的权重/trace 上，攻击者必须重算对应 leaf 或子电路，才能让 opening 与 witness 通过检查。

### 5.3 关键结论

- 如果只是“输出替换”而不改 commitment 与 witness，则很容易被 L1 绑定打穿；
- 如果攻击者真的想通过审计，必须付出接近“局部重算”的成本；
- 这正是模型承诺 + L1 绑定 + 抽样审计的价值所在。

---

## 6. 验证成本建模

### 6.1 单次审计成本

每次审计只检查 $k$ 个单位，则验证成本可建模为：

$$
C_{
m verify}^{(1)} = C_{
m open}(k) + C_{
m replay}(k) + C_{
m EC}^{
m verify}(k)
$$

其中：

- $C_{
m open}(k) = k \cdot c_{
m open}$；
- $C_{
m replay}(k) = k \cdot c_{
m unit}$；
- $C_{
m EC}^{
m verify}(k) = k_{
m mult} \cdot c_{
m ptmul}^{(v)} + k_{
m add} \cdot c_{
m ptadd}^{(v)}$。

### 6.2 多轮审计成本

若每轮审计概率是 $\rho$，总验证成本是：

$$
C_{
m verify}^{
m total} = \rho \cdot C_{
m verify}^{(1)}
$$

如果按“每次请求都审计一小部分”建模，则：

$$
C_{
m verify}^{
m total} = n_{
m req} \cdot \rho \cdot C_{
m verify}^{(1)}
$$

### 6.3 检测概率

如果作弊涉及 $t$ 个审计单元，总单元数为 $N$，抽样 $k$ 个，则抽中概率：

$$
p_{
m hit} = 1 - \frac{\binom{N-t}{k}}{\binom{N}{k}}
$$

当 $t \ll N$ 时，可近似为：

$$
p_{
m hit} \approx \frac{k t}{N}
$$

于是有效检测概率是：

$$
p_{
m eff} = \rho \cdot p_{
m hit}
$$

---

## 7. 经济均衡条件

攻击者的预期收益与成本满足：

$$
U_{
m cheat} = R - C_{
m infer}(M') - C_{
m forge} - p_{
m eff}(P+L)
$$

诚实方的收益是：

$$
U_{
m honest} = R - C_{
m honest}
$$

要让诚实成为均衡策略，需要：

$$
U_{
m honest} > U_{
m cheat}
$$

即：

$$
p_{
m eff}(P+L) + C_{
m audit	ext{-}forge} > G_{
m replace}
$$

这就是最终要用的“经济威慑公式”。

---

## 8. 对 LLM 场景的具体落地建议

### 8.1 先从“模型替换”这一条开始建模

对 LLM，建议先把攻击行为拆成三个子模型：

1. 小模型替换：$M \to M'$；
2. 降精度替换：FP16 → INT4；
3. 跳层 / 省略部分算子：只做部分层/部分 token。

对每一种子模型，分别定义：

$$
G_{\rm sub} = C_{
m infer}(M) - C_{
m infer}(M'_{
m sub})
$$

再配上对应的审计成本：

$$
C_{
m audit	ext{-}forge}^{
m sub} = C_{
m open}(k_{
m sub}) + C_{
m replay}(k_{
m sub})
$$

### 8.2 审计单元不必是“整模型”

对于 LLM，建议把审计单元取为：

- 关键层输出；
- decode step；
- attention 输出；
- MoE 路由与 expert 选择；
- top-k token 生成路径。

这样 $N$ 不再是全模型参数数，而是“可审计轨迹单元数”。

### 8.3 用“局部重算”替代“全量重算”

这正是仓库里 L1 绑定和 EC gadget 的价值：

- 不需要对整模型做全量 SNARK；
- 只在被抽中的单元上打开权重/trace 并重算；
- 这使得 $C_{
m replay}(k)$ 可控，远低于全量证明。

---

## 9. 建议的工程化参数化方式

建议把模型做成下面这种参数表：

```text
ModelCostParams:
  N_W              # 参数总量
  C_infer_full     # 完整模型每次推理成本
  C_infer_small    # 替代模型每次推理成本
  C_commit         # 模型提交/承诺成本
  C_trace          # trace 记录成本
  C_ptmul          # 单个 PtMul gadget 成本
  C_ptadd          # 单个 PtAdd gadget 成本
  C_open           # 单个 opening 成本
  C_replay         # 单个局部重算成本
  k                # 抽样数
  N                # 总审计单元数
  rho              # 审计频率
  P                # 押金/罚没
  L                # 声誉损失
```

然后每次计算：

```text
G_replace = C_infer_full - C_infer_small
p_hit     = 1 - C(N-t, k)/C(N, k)
p_eff     = rho * p_hit
C_verify  = C_open(k) + C_replay(k) + C_EC_verify(k)
condition = p_eff * (P + L) + C_audit_forge > G_replace
```

---

## 10. 结论

对 EC gadget 与模型承诺的建模，最关键不是“证明多么复杂”，而是把以下三件事放进同一个经济模型：

1. 模型替换能省下多少算力收益 $G_{
m replace}$；
2. 为了通过审计，攻击者必须额外付出多少伪造成本 $C_{
m audit	ext{-}forge}$；
3. 验证者以多大概率和成本发现替换 $p_{
m eff}, C_{
m verify}$。

这条路径与仓库当前实现是对齐的：

- 模型承诺负责绑定 `W*`；
- L1 绑定负责把 PtMul 轨迹与 committed 权重叶子/ RLC 列绑定；
- EC gadget 负责把点加/点乘的代数轨迹压成可验证子电路；
- 抽样审计把“全量证明”变成“局部重算 + 经济威慑”。

因此，LLM 场景下的正确建模应当是：

$$
\boxed{
\text{LLM 验证成本} \approx \text{承诺成本} + \text{局部打开成本} + \text{抽样重算成本} + \text{EC 子电路验证成本}
}
$$

而替换收益则是：

$$
\boxed{
G_{
m replace} \approx \text{小模型/低精度/跳层带来的算力与显存节省}
}
$$

只要这两个量之间形成足够大的差距，协议就能在“理性服务器”意义上起到威慑作用。
