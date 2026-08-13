import { aheWsUrlForEngine } from "@/communication/endpoints";
import { fetchBackendJson } from "@/services/backendApi";
import { backendApiBase } from "@/config/endpoints";

export interface SecurityTransport {
  tls_enabled: boolean;
  http_scheme: string;
  ws_scheme: string;
  api_base: string;
  session_ws: string;
  payload_encryption?: string;
}

export interface InferenceMetrics {
  total_inferences: number;
  delta_7d: number;
  delta_1d: number;
  usage: {
    pt_add_total: number;
    pt_mult_total: number;
    by_day: { date: string; inferences: number; pt_add: number; pt_mult: number }[];
  };
}

export interface ComputationProof {
  status: string;
  last_verified_at: string | null;
  coverage: number | null;
  message?: string;
}

export async function fetchSecurityTransport(): Promise<SecurityTransport> {
  const data = await fetchBackendJson<SecurityTransport>("/security/transport");
  return (
    data ?? {
      tls_enabled: false,
      http_scheme: "http",
      ws_scheme: "ws",
      api_base: backendApiBase(),
      session_ws: aheWsUrlForEngine("rust-ark"),
      payload_encryption: "ahe_ciphertext",
    }
  );
}

export async function fetchInferenceMetrics(): Promise<InferenceMetrics | null> {
  return fetchBackendJson<InferenceMetrics>("/security/inference-metrics");
}

export async function fetchComputationProof(): Promise<ComputationProof | null> {
  return fetchBackendJson<ComputationProof>("/security/computation-proof");
}
