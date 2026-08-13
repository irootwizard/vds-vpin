# ZK Computation Proof Review

本文记录对 vPIN 论文与 `docs/cp-snark` 计算量证明文档的核查结论。

## 分类标准

本文只把上下文中无歧义、可由代数公式直接判定的问题标为“确定错误”。依赖协议时序、transcript 接线或实现细节的问题标为 warning。

## 确定错误 1：卷积 RLC 不能压缩 filter 下标

设卷积窗口输出为：

$$
a_r=\sum_{s=0}^{k^2-1} f_s C_{r,s}.
$$

验证方挑战 $\gamma$ 后，正确 RLC 是：

$$
\sum_r \gamma^r a_r
=
\sum_r \gamma^r \sum_s f_s C_{r,s}
=
\sum_s f_s\left(\sum_r \gamma^r C_{r,s}\right).
$$

因此 $\gamma$ 的幂作用在窗口编号 $r$，不是卷积核下标 $s$。

错误写法是：

$$
\sum_s \gamma^s f_s
$$

再拿它乘每个窗口点。该式一般不等价于论文式 (9)。

应改为：

$$
U_s=\sum_r \gamma^r C_{r,s},
\qquad
\sum_r \gamma^r a_r=\sum_s f_s U_s.
$$

## 确定错误 2：FC RLC 不能遗漏 bias

若：

$$
t_i=\sum_j W_{j,i}d_j+b_i,
$$

则：

$$
\sum_i \gamma^i t_i
=
\sum_j\left(\sum_i \gamma^i W_{j,i}\right)d_j
+
\sum_i \gamma^i b_i.
$$

任何只写前半项而不含 $\sum_i\gamma^i b_i$ 的式 (10) 都没有约束 bias。

## 确定错误 3：FC 压缩后的 PtMul 数量按输入维度计

FC RLC 后：

$$
\widetilde W_j=\sum_i \gamma^i W_{j,i}.
$$

每个输入维度 $j$ 需要一个聚合标量 $\widetilde W_j$，所以 PtMul 数量按输入维度 $h$ 计，不按输出维度 $g$ 计。

Network A:

$$
h_1=64,\qquad h_2=16.
$$

若 ElGamal 密文有两个 EC 分量，则压缩轨迹数量为：

$$
2(64+16)=160.
$$

不是：

$$
16+10=26.
$$

## 确定错误 4：Merkle 旧复杂度估计过低

旧文档使用：

$$
c_h=2\sim 30
$$

估计：

$$
178\times 10\times c_h.
$$

若 MerkleVerify 进入 R1CS，应区分哈希：

- SHA256：每层约 $2\times10^4$ 到 $3\times10^4$ 约束，不适合全路径进电路；
- Poseidon：每层约 $200$ 到 $400$ 约束。

Network A 若对 178 个访问路径做 Poseidon Merkle：

$$
178\times 11\times 300\approx 5.9\times 10^5.
$$

这接近当前 EC-only 基线：

$$
C_0\approx 6.38\times 10^5.
$$

因此不能继续写成 “+0.6% 到 +8%”。

## Warning：RLC soundness 的先固定输出/轨迹

“RLC soundness 需要先固定输出/轨迹，再给 $\gamma$”是重要安全提示，但不应标为当前文档的公式错误。

更准确表述：

```text
若 RLC 只是链外标量检查，则输出、轨迹或承诺应先于 gamma 固定。
若 RLC 作为公开输入进入完整 SNARK 关系，则安全性取决于 SNARK 语句是否完整绑定 witness、输出和 commitment。
```

## Warning：池化常数缩放

平均池化：

$$
B=c\sum A,\qquad c=\hat k^{-2}.
$$

若实现中实际执行了公开常数标量乘，则证明关系应包含该乘法；若常数因子被吸收到后续层权重或定点缩放流程，则文档应明确说明。

