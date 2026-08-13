import type { MockComputeReceipt, MockVerifyResult } from "@/demo/mockComputeCommitment";

const KEY = "vpin.llm.receipt.v1";

export interface LlmReceiptSnapshot {
  receipt: MockComputeReceipt;
  verify: MockVerifyResult;
  saved_at: string;
}

export function saveLlmReceiptSnapshot(receipt: MockComputeReceipt, verify: MockVerifyResult): void {
  try {
    const snap: LlmReceiptSnapshot = {
      receipt,
      verify,
      saved_at: new Date().toISOString(),
    };
    sessionStorage.setItem(KEY, JSON.stringify(snap));
  } catch {
    /* quota / private mode */
  }
}

export function loadLlmReceiptSnapshot(): LlmReceiptSnapshot | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (!raw) return null;
    return JSON.parse(raw) as LlmReceiptSnapshot;
  } catch {
    return null;
  }
}
