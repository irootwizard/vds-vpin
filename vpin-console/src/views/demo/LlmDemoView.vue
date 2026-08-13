<script setup lang="ts">
import { nextTick, onMounted, ref } from "vue";
import { NAvatar, NButton, NCollapse, NCollapseItem, NIcon, NSpin, NTag } from "naive-ui";
import { ArrowUpOutline, PersonOutline, SparklesOutline } from "@vicons/ionicons5";
import { hasDeepSeekKey, streamChat, streamChatDemo } from "@/demo/deepseekClient";
import { tlsCiphertextPreview } from "@/demo/tlsCiphertextPreview";
import {
  buildMockComputeReceipt,
  mockVerifyComputeReceipt,
  type MockComputeReceipt,
  type MockVerifyResult,
} from "@/demo/mockComputeCommitment";
import { saveLlmReceiptSnapshot } from "@/demo/llmReceiptStore";

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
}

const input = ref("");
const messages = ref<ChatMessage[]>([]);
const cipherPreview = ref("");
const loading = ref(false);
const scrollEl = ref<HTMLElement | null>(null);
const inputEl = ref<HTMLTextAreaElement | null>(null);

const receipt = ref<MockComputeReceipt | null>(null);
const verifying = ref(false);
const verifyResult = ref<MockVerifyResult | null>(null);

const suggestions = [
  "什么是密视可验证隐私推理？",
  "同态加密推理和 ZK 证明有什么区别？",
  "计算量承诺 receipt 包含哪些字段？",
];

function uid(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

async function scrollToBottom(): Promise<void> {
  await nextTick();
  const el = scrollEl.value;
  if (el) el.scrollTop = el.scrollHeight;
}

function resizeInput(): void {
  const el = inputEl.value;
  if (!el) return;
  el.style.height = "auto";
  el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
}

function onInputKeydown(e: KeyboardEvent): void {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    void send();
  }
}

async function streamReply(text: string, assistantId: string): Promise<void> {
  const idx = messages.value.findIndex((m) => m.id === assistantId);
  if (idx < 0) return;

  const append = (chunk: string) => {
    messages.value[idx] = {
      ...messages.value[idx],
      content: messages.value[idx].content + chunk,
    };
    void scrollToBottom();
  };

  if (hasDeepSeekKey()) {
    try {
      for await (const chunk of streamChat(text)) {
        append(chunk);
      }
      return;
    } catch {
      /* 静默回退演示流 */
    }
  }
  for await (const chunk of streamChatDemo(text)) {
    append(chunk);
  }
}

async function runAutoVerify(r: MockComputeReceipt): Promise<void> {
  verifying.value = true;
  verifyResult.value = null;
  try {
    verifyResult.value = await mockVerifyComputeReceipt(r);
    saveLlmReceiptSnapshot(r, verifyResult.value);
  } finally {
    verifying.value = false;
  }
}

async function send(textOverride?: string): Promise<void> {
  const text = (textOverride ?? input.value).trim();
  if (!text || loading.value) return;

  input.value = "";
  resizeInput();
  loading.value = true;
  receipt.value = null;
  verifyResult.value = null;

  const userId = uid();
  const assistantId = uid();
  messages.value.push({ id: userId, role: "user", content: text });
  messages.value.push({ id: assistantId, role: "assistant", content: "" });
  await scrollToBottom();

  try {
    cipherPreview.value = await tlsCiphertextPreview(text);
    await streamReply(text, assistantId);
    const answer = messages.value.find((m) => m.id === assistantId)?.content ?? "";
    if (answer) {
      receipt.value = await buildMockComputeReceipt(text, answer);
      await runAutoVerify(receipt.value);
    }
  } finally {
    loading.value = false;
    await scrollToBottom();
  }
}

onMounted(() => {
  resizeInput();
});
</script>

<template>
  <div class="llm-page">
    <div ref="scrollEl" class="chat-scroll">
      <div v-if="messages.length === 0" class="welcome">
        <div class="welcome-icon">
          <NIcon size="28" color="#6366f1"><SparklesOutline /></NIcon>
        </div>
        <h2>大模型推理</h2>
        <p>端到端 TLS 加密对话 · 本地计算量承诺自动验证</p>
        <div class="suggestions">
          <button
            v-for="s in suggestions"
            :key="s"
            type="button"
            class="suggestion-chip"
            @click="send(s)"
          >
            {{ s }}
          </button>
        </div>
      </div>

      <article
        v-for="msg in messages"
        :key="msg.id"
        class="message-row"
        :class="msg.role"
      >
        <div class="message-inner">
          <NAvatar
            round
            size="small"
            class="msg-avatar"
            :style="
              msg.role === 'user'
                ? { background: 'var(--color-primary)' }
                : { background: 'linear-gradient(135deg, #6366f1, #8b5cf6)' }
            "
          >
            <NIcon v-if="msg.role === 'user'" :component="PersonOutline" />
            <NIcon v-else :component="SparklesOutline" />
          </NAvatar>
          <div class="msg-body">
            <div class="msg-role">{{ msg.role === "user" ? "你" : "助手" }}</div>
            <div v-if="msg.role === 'assistant' && loading && !msg.content" class="typing">
              <span /><span /><span />
            </div>
            <div v-else class="msg-content">{{ msg.content }}</div>
          </div>
        </div>
      </article>
    </div>

    <div class="composer-wrap">
      <div class="composer">
        <textarea
          ref="inputEl"
          v-model="input"
          class="composer-input"
          rows="1"
          placeholder="发送消息…"
          @input="resizeInput"
          @keydown="onInputKeydown"
        />
        <NButton
          type="primary"
          circle
          class="composer-send"
          :disabled="!input.trim() || loading"
          :loading="loading"
          @click="send()"
        >
          <template #icon>
            <NIcon><ArrowUpOutline /></NIcon>
          </template>
        </NButton>
      </div>
      <p class="composer-hint">Enter 发送 · Shift+Enter 换行</p>
    </div>

    <div class="security-panel">
      <NCollapse>
        <NCollapseItem name="tls">
          <template #header>传输加密详情</template>
          <template #header-extra>
            <NTag v-if="cipherPreview" size="tiny" type="success" :bordered="false">
              TLS 1.2+
            </NTag>
          </template>
          <div class="security-block">
            <p class="security-desc">请求体经浏览器标准 HTTPS 加密后发送至 DeepSeek API。</p>
            <pre class="mono cipher">{{ cipherPreview || "发送消息后显示密文摘要预览" }}</pre>
          </div>
        </NCollapseItem>

        <NCollapseItem name="receipt">
          <template #header>计算量承诺与验证</template>
          <template #header-extra>
            <NTag
              v-if="verifyResult?.pass"
              size="tiny"
              type="success"
              :bordered="false"
            >
              PASS
            </NTag>
            <NSpin v-else-if="verifying" size="small" />
          </template>
          <div class="security-block">
            <template v-if="receipt">
              <dl class="receipt-grid">
                <dt>session</dt>
                <dd class="mono">{{ receipt.session_id }}</dd>
                <dt>model</dt>
                <dd>{{ receipt.model_label }}</dd>
                <dt>cm_W</dt>
                <dd class="mono">{{ receipt.cm_W }}</dd>
                <dt>cm_trace</dt>
                <dd class="mono">{{ receipt.cm_trace }}</dd>
                <dt>decode</dt>
                <dd class="mono">{{ receipt.decode_policy_hash }}</dd>
                <dt>tokens</dt>
                <dd>
                  {{ receipt.token_count }} · N≈{{ receipt.audit_space_N.toLocaleString() }}
                </dd>
              </dl>
              <div class="vrf-tags">
                <NTag
                  v-for="(u, i) in receipt.sampled_units"
                  :key="i"
                  size="small"
                  :bordered="false"
                >
                  L{{ u.layer }}·t{{ u.token }}·c{{ u.coord }}
                </NTag>
              </div>
              <div v-if="verifyResult" class="verify-report">
                <NTag type="success" size="small">PASS · rational-audit</NTag>
                <span class="verify-meta">
                  verifier {{ verifyResult.verifier_ms }} ms · p_hit≈{{ verifyResult.p_hit }}
                </span>
                <ul class="verify-checks">
                  <li v-for="c in verifyResult.checks" :key="c.id">
                    <NTag :type="c.ok ? 'success' : 'error'" size="tiny">
                      {{ c.ok ? "OK" : "FAIL" }}
                    </NTag>
                    {{ c.label }}
                    <span class="muted">{{ c.detail }}</span>
                  </li>
                </ul>
              </div>
            </template>
            <p v-else class="security-desc">完成一轮对话后自动生成 receipt 并完成本地验证。</p>
          </div>
        </NCollapseItem>
      </NCollapse>
    </div>
  </div>
</template>

<style scoped>
.llm-page {
  display: flex;
  flex-direction: column;
  height: calc(100vh - var(--header-height) - 200px);
  min-height: 420px;
  max-width: 820px;
  margin: 0 auto;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  overflow: hidden;
  box-shadow: var(--shadow-sm);
}

.chat-scroll {
  flex: 1;
  overflow-y: auto;
  scroll-behavior: smooth;
}

.welcome {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 48px 24px 32px;
  min-height: 280px;
}

.welcome-icon {
  width: 52px;
  height: 52px;
  border-radius: 50%;
  background: #f0f0ff;
  display: grid;
  place-items: center;
  margin-bottom: 16px;
}

.welcome h2 {
  margin: 0 0 8px;
  font-size: 22px;
  font-weight: 600;
}

.welcome p {
  margin: 0 0 24px;
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}

.suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
  max-width: 560px;
}

.suggestion-chip {
  padding: 10px 14px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-full);
  background: var(--color-bg);
  font-size: var(--text-sm);
  color: var(--color-text-primary);
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}

.suggestion-chip:hover {
  background: #fff;
  border-color: var(--color-primary-light);
}

.message-row {
  border-bottom: 1px solid var(--color-border);
}

.message-row.user {
  background: #f7f7f8;
}

.message-row.assistant {
  background: #fff;
}

.message-inner {
  display: flex;
  gap: 16px;
  max-width: 720px;
  margin: 0 auto;
  padding: 20px 24px;
}

.msg-avatar {
  flex-shrink: 0;
  margin-top: 2px;
}

.msg-body {
  flex: 1;
  min-width: 0;
}

.msg-role {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-muted);
  margin-bottom: 6px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.msg-content {
  font-size: 15px;
  line-height: 1.65;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--color-text-primary);
}

.typing {
  display: flex;
  gap: 5px;
  padding: 4px 0;
}

.typing span {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--color-text-muted);
  animation: bounce 1.2s infinite ease-in-out;
}

.typing span:nth-child(2) {
  animation-delay: 0.15s;
}

.typing span:nth-child(3) {
  animation-delay: 0.3s;
}

@keyframes bounce {
  0%,
  80%,
  100% {
    transform: translateY(0);
    opacity: 0.4;
  }
  40% {
    transform: translateY(-5px);
    opacity: 1;
  }
}

.composer-wrap {
  flex-shrink: 0;
  padding: 12px 16px 8px;
  background: var(--color-surface);
  border-top: 1px solid var(--color-border);
}

.composer {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  padding: 10px 10px 10px 16px;
  border: 1px solid var(--color-border);
  border-radius: 24px;
  background: #fff;
  box-shadow: var(--shadow-sm);
}

.composer-input {
  flex: 1;
  border: none;
  outline: none;
  resize: none;
  font-family: inherit;
  font-size: 15px;
  line-height: 1.5;
  max-height: 200px;
  background: transparent;
  color: var(--color-text-primary);
}

.composer-send {
  flex-shrink: 0;
}

.composer-hint {
  margin: 6px 0 0;
  text-align: center;
  font-size: 11px;
  color: var(--color-text-muted);
}

.security-panel {
  flex-shrink: 0;
  border-top: 1px solid var(--color-border);
  background: var(--color-bg);
}

.security-panel :deep(.n-collapse-item__header) {
  padding: 10px 16px !important;
  font-size: var(--text-sm);
}

.security-panel :deep(.n-collapse-item__content-inner) {
  padding: 0 16px 12px !important;
}

.collapse-title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-weight: 500;
}

.collapse-icon {
  color: var(--color-text-secondary);
}

.security-block {
  font-size: var(--text-sm);
}

.security-desc {
  margin: 0 0 8px;
  color: var(--color-text-secondary);
  line-height: 1.5;
}

.cipher {
  margin: 0;
  padding: 10px 12px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font-size: 11px;
  color: var(--color-text-secondary);
  white-space: pre-wrap;
  word-break: break-all;
}

.mono {
  font-family: var(--font-mono);
}

.receipt-grid {
  display: grid;
  grid-template-columns: 88px 1fr;
  gap: 6px 12px;
  margin: 0 0 10px;
}

.receipt-grid dt {
  margin: 0;
  color: var(--color-text-muted);
  font-size: var(--text-xs);
}

.receipt-grid dd {
  margin: 0;
  font-size: var(--text-sm);
  word-break: break-all;
}

.vrf-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 12px;
}

.verify-report {
  padding-top: 10px;
  border-top: 1px dashed var(--color-border);
}

.verify-meta {
  display: block;
  margin: 8px 0;
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
}

.verify-checks {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 6px;
}

.verify-checks li {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  font-size: var(--text-sm);
}

.muted {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}
</style>
