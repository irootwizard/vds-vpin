const API_BASE = import.meta.env.VITE_VPIN_API || "/api/v1";

const CLIENT_ONLY =
  "输入预处理已移至客户端（Tauri / vpin_client），服务端不再提供 /data/* 预处理 API。";

async function getJson(path) {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `${path} ${res.status}`);
  }
  return res.json();
}

/** @deprecated Use aheClient.pythonPreprocessOfficial / rustPreprocessOfficial (local Tauri). */
export function fetchOfficialPreprocess(_index) {
  return Promise.reject(new Error(CLIENT_ONLY));
}

/** @deprecated Use aheClient.pythonPreprocessBatch (local Tauri). */
export function fetchOfficialBatch(_start = 0, _count = 10) {
  return Promise.reject(new Error(CLIENT_ONLY));
}

/** @deprecated Use aheClient.pythonPreprocessUpload (local file path via Tauri). */
export async function uploadAndPreprocess(_file) {
  throw new Error(CLIENT_ONLY);
}

/** @deprecated Server-side upload index removed. */
export function listUploads(_limit = 50) {
  return Promise.reject(new Error(CLIENT_ONLY));
}

/** @deprecated Server-side upload meta removed. */
export function getUploadMeta(_uploadId) {
  return Promise.reject(new Error(CLIENT_ONLY));
}
