export interface MockComputeReceipt {
  session_id: string;
  model_id: string;
  model_label: string;
  cm_W: string;
  cm_trace: string;
  decode_policy_hash: string;
  sampling_seed: string;
  token_count: number;
  audit_space_N: number;
  sampled_units: { layer: number; token: number; coord: number }[];
  created_at: string;
}

export interface MockVerifyResult {
  pass: boolean;
  p_hit: number;
  checks: { id: string; label: string; ok: boolean; detail: string }[];
  verifier_ms: number;
}

async function sha256Hex(text: string): Promise<string> {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(buf)]
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

function trunc(hex: string, n = 16): string {
  return `0x${hex.slice(0, n)}…${hex.slice(-8)}`;
}

function pseudoInt(hex: string, mod: number): number {
  return parseInt(hex.slice(0, 8), 16) % mod;
}

export async function buildMockComputeReceipt(
  prompt: string,
  answer: string,
): Promise<MockComputeReceipt> {
  const base = await sha256Hex(`vpin-mock-v1|${prompt}|${answer}`);
  const cmW = await sha256Hex(`cm_W|${base}`);
  const cmTrace = await sha256Hex(`cm_trace|${base}`);
  const policy = await sha256Hex(`decode|temperature=0.7|top_p=0.9|${base}`);
  const seed = await sha256Hex(`vrf|${base}`);

  const tokenCount = Math.max(1, Math.ceil(answer.length / 4));
  const auditN = 32 * tokenCount * 4096;

  const sampled_units = Array.from({ length: 5 }, (_, i) => ({
    layer: pseudoInt(seed, 32) + i * 3,
    token: pseudoInt(seed.slice(i * 4), tokenCount),
    coord: pseudoInt(seed.slice(8 + i * 2), 4096),
  }));

  return {
    session_id: `sess-${base.slice(0, 12)}`,
    model_id: "deepseek-chat",
    model_label: "DeepSeek Chat",
    cm_W: trunc(cmW, 20),
    cm_trace: trunc(cmTrace, 20),
    decode_policy_hash: trunc(policy, 12),
    sampling_seed: trunc(seed, 12),
    token_count: tokenCount,
    audit_space_N: auditN,
    sampled_units,
    created_at: new Date().toISOString(),
  };
}

export async function mockVerifyComputeReceipt(
  receipt: MockComputeReceipt,
  onStep?: (step: string) => void,
): Promise<MockVerifyResult> {
  const steps = [
    "初始化 VRF 挑战",
    "打开 cm_W Merkle 路径",
    "打开 cm_trace 抽样单元",
    "Freivalds 线性层指纹",
    "decode path 重放一致性",
    "博弈均衡 p(P+L)>G 检查",
  ];
  const t0 = performance.now();
  for (const s of steps) {
    onStep?.(s);
    await new Promise((r) => setTimeout(r, 280 + Math.random() * 120));
  }
  const t = Math.round(performance.now() - t0);
  const p_hit = 0.41;

  return {
    pass: true,
    p_hit,
    verifier_ms: t,
    checks: [
      { id: "open_w", label: "权重承诺打开", ok: true, detail: `${receipt.sampled_units.length} 叶子已绑定` },
      { id: "open_trace", label: "轨迹承诺打开", ok: true, detail: "hidden @ L7/L23 已对齐" },
      { id: "freivalds", label: "Freivalds 抽检", ok: true, detail: "rᵀy = rᵀWx (Fp)" },
      { id: "decode", label: "Decode 绑定", ok: true, detail: receipt.decode_policy_hash },
      { id: "game", label: "理性安全", ok: true, detail: `p_hit≈${p_hit}，stake 满足 P>G/p` },
    ],
  };
}
