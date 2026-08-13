/** Demo fallback when /api/v1/security/* is unavailable (Tauri offline, backend not started). */

function daysAgo(n) {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
}

const API_BASE = import.meta.env.VITE_VPIN_API || "/api/v1";

export const mockTransport = {
  tls_enabled: false,
  http_scheme: "http",
  ws_scheme: "ws",
  api_base: API_BASE.startsWith("/")
    ? "http://127.0.0.1:8000/api/v1"
    : API_BASE,
  session_ws: "ws://127.0.0.1:8000/api/v1/session/ws",
  certificate: null,
  forward_secrecy: false,
  payload_encryption: "ahe_ciphertext",
};

const byDay = Array.from({ length: 7 }, (_, i) => {
  const day = 6 - i;
  const inferences = 12 + day * 3 + (i % 2) * 2;
  return {
    date: daysAgo(day),
    pt_add: 2144 * inferences,
    pt_mult: 178 * inferences,
    inferences,
  };
});

export const mockInferenceMetrics = {
  total_inferences: byDay.reduce((s, d) => s + d.inferences, 0),
  delta_7d: byDay.reduce((s, d) => s + d.inferences, 0),
  delta_1d: byDay[byDay.length - 1].inferences,
  usage: {
    pt_add_total: byDay.reduce((s, d) => s + d.pt_add, 0),
    pt_mult_total: byDay.reduce((s, d) => s + d.pt_mult, 0),
    by_day: byDay,
  },
  proof_overhead: {
    prove_ms_avg: 1180,
    verify_ms_avg: 42,
    overhead_ratio: 1.75,
    by_day: byDay.map((d) => ({
      date: d.date,
      prove_ms: 900 + d.inferences * 18,
      verify_ms: 35 + (d.inferences % 5) * 2,
    })),
  },
};

export const mockComputationProof = {
  status: "pending",
  last_verified_at: null,
  coverage: null,
  message: "计算量证明校验待接入",
};
