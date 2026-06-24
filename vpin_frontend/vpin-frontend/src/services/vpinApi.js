const API_BASE = import.meta.env.VITE_VPIN_API || "/api/v1";

async function getJson(path) {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`${path} ${res.status}`);
  return res.json();
}

export function fetchHealth() {
  return getJson("/health");
}

export function fetchModels() {
  return getJson("/models");
}

export function fetchMnistIndex() {
  return getJson("/mnist/index");
}

/**
 * Upload AHE npy bundle (zip with weight_fc1_*.npy …) or model_export.json.
 * @param {{ modelId: string, name: string, network: string, file: File }} opts
 */
export async function uploadModel({ modelId, name, network, file }) {
  const form = new FormData();
  form.append("model_id", modelId);
  form.append("name", name);
  form.append("network", network || "A");

  const lower = file.name.toLowerCase();
  if (lower.endsWith(".zip")) {
    form.append("npy_bundle", file);
  } else if (lower.endsWith(".json")) {
    form.append("weights", file);
  } else {
    throw new Error("仅支持 .zip（AHE npy 包）或 .json（model_export.json）");
  }

  const res = await fetch(`${API_BASE}/models`, { method: "POST", body: form });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `upload ${res.status}`);
  }
  return res.json();
}
