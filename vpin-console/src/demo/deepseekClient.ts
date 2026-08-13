// [TEMP-DEMO-LLM]

import { DEFAULT_SYSTEM_PROMPT } from "./defaultSystemPrompt";

const baseUrl = () =>
  (import.meta.env.VITE_DEEPSEEK_BASE_URL ?? "https://api.deepseek.com").replace(/\/$/, "");

const apiKey = () => import.meta.env.VITE_DEEPSEEK_API_KEY?.trim() ?? "";

const model = () => import.meta.env.VITE_DEEPSEEK_MODEL ?? "deepseek-v4-pro";

export function hasDeepSeekKey(): boolean {
  return apiKey().length > 0;
}

/** 无 API 或网络失败时的本地演示流，不抛错 */
export async function* streamChatDemo(userMessage: string): AsyncGenerator<string> {
  const reply =
    `已收到您的问题。本能力由密视团队部署的专用大语言模型提供。\n\n` +
    `关于「${userMessage.slice(0, 120)}${userMessage.length > 120 ? "…" : ""}」：` +
    `我们采用 TLS 加密传输与本地计算量承诺 receipt，可在页面下方展开查看 cm_W、cm_trace 与 VRF 抽样验证报告。`;
  for (const ch of reply) {
    await new Promise((r) => setTimeout(r, 12 + Math.random() * 8));
    yield ch;
  }
}

export async function* streamChat(
  userMessage: string,
  onDelta?: (text: string) => void,
): AsyncGenerator<string> {
  const key = apiKey();
  if (!key) throw new Error("NO_KEY");

  const res = await fetch(`${baseUrl()}/v1/chat/completions`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${key}`,
    },
    body: JSON.stringify({
      model: model(),
      stream: true,
      messages: [
        { role: "system", content: DEFAULT_SYSTEM_PROMPT },
        { role: "user", content: userMessage },
      ],
    }),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`DeepSeek API ${res.status}: ${text.slice(0, 200)}`);
  }

  const reader = res.body?.getReader();
  if (!reader) throw new Error("无响应流");

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed.startsWith("data:")) continue;
      const data = trimmed.slice(5).trim();
      if (data === "[DONE]") return;
      try {
        const json = JSON.parse(data) as {
          choices?: { delta?: { content?: string } }[];
        };
        const chunk = json.choices?.[0]?.delta?.content ?? "";
        if (chunk) {
          onDelta?.(chunk);
          yield chunk;
        }
      } catch {
        // skip malformed SSE chunk
      }
    }
  }
}
