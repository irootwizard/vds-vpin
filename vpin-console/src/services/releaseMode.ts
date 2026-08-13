import { isTauri } from "@/services/aheClient";

/** 发布便携包：含内置 proof_artifacts，无需 Python :8000 */
export async function detectPortableStandalone(): Promise<boolean> {
  if (!isTauri()) return false;
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    const plan = await invoke<{ witness?: { files_ok?: boolean } }>("read_proof_plan", {
      modelId: "cnn-mnist-trained",
    });
    return Boolean(plan?.witness?.files_ok);
  } catch {
    return false;
  }
}
