// [TEMP-DEMO-TLS] — demo ciphertext preview only

export async function tlsCiphertextPreview(payload: string): Promise<string> {
  const data = new TextEncoder().encode(payload);
  const hash = await crypto.subtle.digest("SHA-256", data);
  const hex = [...new Uint8Array(hash)]
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
  return `TLS1.3:${hex.slice(0, 128)}…`;
}
