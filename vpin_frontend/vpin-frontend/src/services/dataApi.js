const API_BASE = import.meta.env.VITE_VPIN_API || "/api/v1";

async function getJson(path) {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `${path} ${res.status}`);
  }
  return res.json();
}

/** Server-side official MNIST preprocess (single sample). */
export function fetchOfficialPreprocess(index) {
  return getJson(`/data/official/test/${index}`);
}

/** Server-side official MNIST batch preprocess. */
export function fetchOfficialBatch(start = 0, count = 10) {
  return getJson(`/data/official/batch?start=${start}&count=${count}`);
}

/** Upload image file → server preprocess + store. */
export async function uploadAndPreprocess(file) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/data/upload/preprocess`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `upload preprocess ${res.status}`);
  }
  return res.json();
}

export function listUploads(limit = 50) {
  return getJson(`/data/uploads?limit=${limit}`);
}

export function getUploadMeta(uploadId) {
  return getJson(`/data/upload/${uploadId}`);
}
