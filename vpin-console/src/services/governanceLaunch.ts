export const GOVERNANCE_LAUNCH_KEY = "vpin-governance-launch";

export interface GovernanceLaunchPayload {
  modelId: string;
  datasetId: string;
  inferMode: "single" | "batch";
  sampleIndex: number;
  batchStart: number;
  batchEnd: number;
}

export function saveGovernanceLaunch(payload: GovernanceLaunchPayload): void {
  sessionStorage.setItem(GOVERNANCE_LAUNCH_KEY, JSON.stringify(payload));
}

export function loadGovernanceLaunch(): GovernanceLaunchPayload | null {
  try {
    const raw = sessionStorage.getItem(GOVERNANCE_LAUNCH_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as GovernanceLaunchPayload;
  } catch {
    return null;
  }
}

export function clearGovernanceLaunch(): void {
  sessionStorage.removeItem(GOVERNANCE_LAUNCH_KEY);
}
