/** 通信层共享类型 */

export type LinkStatus = "checking" | "connected" | "disconnected" | "standalone";

export interface HttpEndpointConfig {
  httpBase: string;
}

export interface AheEndpointConfig {
  host: string;
  port: number;
  httpBase: string;
  wsSession: string;
  skipLocalServer: boolean;
}

export interface CommunicationProfile {
  backend: HttpEndpointConfig;
  ahe: AheEndpointConfig;
  ovds?: HttpEndpointConfig;
}

export interface AheHealthResult {
  ok: boolean;
  runtime?: string;
  host?: string;
  port?: number;
}

export interface AheBootResult {
  started: boolean;
  port: number;
  host?: string;
  status: string;
  skipLocal?: boolean;
}

/** Rust serde 使用 snake_case；前端统一 camelCase */
export function normalizeCommunicationProfile(raw: Record<string, unknown>): CommunicationProfile {
  const backend = (raw.backend ?? {}) as Record<string, unknown>;
  const ahe = (raw.ahe ?? {}) as Record<string, unknown>;
  const ovdsRaw = raw.ovds as Record<string, unknown> | undefined;
  const host = String(ahe.host ?? "127.0.0.1");
  const port = Number(ahe.port ?? 8001);
  const httpBase = String(
    ahe.httpBase ?? ahe.http_base ?? `http://${host}:${port}/api/v1`,
  ).replace(/\/$/, "");
  const wsSession = String(
    ahe.wsSession ?? ahe.ws_session ?? `ws://${host}:${port}/api/v1/session/ws`,
  );
  return {
    backend: {
      httpBase: String(backend.httpBase ?? backend.http_base ?? "http://127.0.0.1:8000/api/v1").replace(
        /\/$/,
        "",
      ),
    },
    ahe: {
      host,
      port,
      httpBase,
      wsSession,
      skipLocalServer: Boolean(ahe.skipLocalServer ?? ahe.skip_local_server ?? false),
    },
    ovds: ovdsRaw
      ? {
          httpBase: String(ovdsRaw.httpBase ?? ovdsRaw.http_base ?? "").replace(/\/$/, ""),
        }
      : undefined,
  };
}
