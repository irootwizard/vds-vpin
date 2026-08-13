import { appendEventLog } from "@/bridge/eventBus";
import type { StartupOptimizerResult } from "@/bridge/types";
import {
  ensureLocalAheServer,
  pingAheServerForEngine,
  waitForAheServer,
} from "@/communication/aheChannel";
import { pingBackend } from "@/communication/backendChannel";
import {
  aheApiBase,
  aheDisplayLabel,
  backendApiBase,
  shouldSkipLocalAheServer,
} from "@/communication/endpoints";
import { loadCommunicationProfile, isTauriRuntime } from "@/communication/runtimeConfig";
import type { LinkStatus } from "@/communication/types";
import { DEFAULT_NETWORK_A_ENGINE, networkAEnginePort } from "@/config/networkAEngine";
import { ensureRuntimeArtifacts } from "@/services/aheClient";
import { detectPortableStandalone } from "@/services/releaseMode";

export interface ConnectionSessionState {
  backendStatus: LinkStatus;
  backendStandalone: boolean;
  aheStatus: LinkStatus;
  bootstrapResult: StartupOptimizerResult | null;
}

export async function bootstrapCommunication(
  bridge: {
    bridgeBootstrapDetect: (force?: boolean) => Promise<{ ok: boolean; data?: StartupOptimizerResult }>;
    bridgeCustodyGetCapabilities: () => Promise<unknown>;
  },
): Promise<ConnectionSessionState> {
  await loadCommunicationProfile();

  appendEventLog("bridge://client", "Client Bridge 连接中…");
  appendEventLog("bridge://client", `backend → ${backendApiBase()}`);
  appendEventLog("bridge://client", `ahe-server → ${aheApiBase()}`);
  if (shouldSkipLocalAheServer()) {
    appendEventLog(
      "bridge://ahe-server",
      `远程推理模式（VPIN_SKIP_LOCAL_AHE）→ ${aheDisplayLabel(networkAEnginePort(DEFAULT_NETWORK_A_ENGINE))}`,
      "info",
    );
  }

  if (isTauriRuntime()) {
    try {
      const artifacts = await ensureRuntimeArtifacts();
      const remote = artifacts.remote as Record<string, unknown> | undefined;
      if (remote?.skipped) {
        appendEventLog(
          "bridge://artifacts",
          `BSGS 表未拉取（${remote.reason ?? "本地已有或未配置 CDN"}）`,
          "info",
        );
      } else if (Array.isArray(remote?.pulled) && (remote.pulled as string[]).length > 0) {
        appendEventLog(
          "bridge://artifacts",
          `已拉取运行时资源: ${(remote.pulled as string[]).join(", ")}`,
          "success",
        );
      } else if (artifacts.bsgs_present) {
        appendEventLog("bridge://artifacts", "BSGS table.bin 已就绪", "success");
      }

      const port = networkAEnginePort(DEFAULT_NETWORK_A_ENGINE);
      const bootServer = await ensureLocalAheServer(port);
      if (bootServer.skipLocal) {
        appendEventLog(
          "bridge://ahe-server",
          `远程 ahe-server 已就绪 ${aheDisplayLabel(port)}`,
          "success",
        );
      } else {
        appendEventLog(
          "bridge://ahe-server",
          bootServer.started
            ? `Rust Ark ahe-server 已自动启动 ${aheDisplayLabel(port)}`
            : `Rust Ark ahe-server 已在运行 ${aheDisplayLabel(port)}`,
          "success",
        );
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      appendEventLog("bridge://ahe-server", `AHE 连接失败: ${msg}`, "error");
    }
  }

  const boot = await bridge.bridgeBootstrapDetect(true);
  const bootstrapResult = boot.ok && boot.data ? boot.data : null;
  await bridge.bridgeCustodyGetCapabilities();
  appendEventLog("bridge://client", "Client Bridge 已就绪", "success");

  const be = await pingBackend();
  let backendStatus: LinkStatus;
  let backendStandalone = false;
  if (be.ok) {
    backendStatus = "connected";
    appendEventLog(
      "bridge://backend",
      `Python backend 已连接 (${be.body?.status ?? "ok"})`,
      "success",
    );
  } else if (isTauriRuntime() && (await detectPortableStandalone())) {
    backendStatus = "standalone";
    backendStandalone = true;
    appendEventLog(
      "bridge://backend",
      "便携发布包：无需 Python :8000（推理/证明走 Rust + 内置 witness）",
      "success",
    );
  } else {
    backendStatus = "disconnected";
    appendEventLog(
      "bridge://backend",
      isTauriRuntime()
        ? "Python backend 未连接（可选；开发环境可启动 vpin-backend）"
        : "Python backend 未连接",
      "info",
    );
  }

  const port = networkAEnginePort(DEFAULT_NETWORK_A_ENGINE);
  let ahe = await pingAheServerForEngine(DEFAULT_NETWORK_A_ENGINE);
  if (!ahe.ok && isTauriRuntime() && !shouldSkipLocalAheServer()) {
    try {
      await ensureLocalAheServer(port);
    } catch {
      /* logged above */
    }
    ahe = await waitForAheServer(port);
  }
  const aheStatus: LinkStatus = ahe.ok ? "connected" : "disconnected";
  appendEventLog(
    "bridge://ahe-server",
    ahe.ok
      ? `Rust ahe-server 已连接 (${ahe.runtime ?? "ok"} @ ${aheDisplayLabel(ahe.port ?? port)})`
      : `Rust ahe-server 未连接（检查 ${aheDisplayLabel(port)} 或 start 脚本）`,
    ahe.ok ? "success" : "error",
  );

  return { backendStatus, backendStandalone, aheStatus, bootstrapResult };
}
