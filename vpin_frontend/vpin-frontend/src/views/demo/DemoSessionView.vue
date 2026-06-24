<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  NButton,
  NTag,
  NInput,
  NIcon,
  NSpin,
  NImage,
  useMessage,
} from "naive-ui";
import { EyeOutline, ImageOutline, SendOutline } from "@vicons/ionicons5";
import PrivacyEffectDrawer from "../../components/demo/PrivacyEffectDrawer.vue";
import { useDemoStore } from "../../composables/useDemoStore.js";
import {
  mockImageCipher,
  mockInferenceResult,
  mockDialogueReply,
  mockCipherText,
  sampleMnistDataUrl,
} from "../../utils/demoCrypto.js";

const route = useRoute();
const router = useRouter();
const message = useMessage();
const { getSession, updateSession, deleteSession, addMessage } = useDemoStore();

const sessionId = computed(() => route.params.id);
const session = computed(() => getSession(sessionId.value));

const inputText = ref("");
const pendingImage = ref(null);
const inferring = ref(false);
const showPrivacy = ref(false);
const privacyPayload = ref(null);
const chatEnd = ref(null);
const fileInput = ref(null);

let queueTimer = null;

const statusLabel = computed(() => {
  const s = session.value?.status;
  if (s === "queuing") return { text: "排队中", type: "warning" };
  if (s === "ready") return { text: "可用", type: "success" };
  if (s === "running") return { text: "推理中", type: "info" };
  return { text: "未知", type: "default" };
});

const expiresLabel = computed(() => {
  if (!session.value) return "—";
  return new Date(session.value.expiresAt).toLocaleString("zh-CN");
});

const suggestions = [
  "密态推理是如何保护图像隐私的？",
  "AHE 和 CP-SNARK 分别做什么？",
  "如何查看加密后的数据？",
];

onMounted(() => {
  if (!session.value) {
    message.error("演示服务不存在");
    router.replace("/demo");
    return;
  }
  if (session.value.status === "queuing") {
    const elapsed = Date.now() - session.value.queueStartedAt;
    const wait = Math.max(3000 - elapsed, 500);
    queueTimer = setTimeout(() => {
      updateSession(sessionId.value, { status: "ready" });
      addMessage(sessionId.value, {
        role: "assistant",
        type: "text",
        content:
          "服务已就绪。您可以上传 28×28 灰度图像执行隐私推理，或点击下方样例。发送文字可了解 vPIN 流程。点击 🔐 旁的眼睛查看密文。",
        privacy: true,
        plainOutput: "服务已就绪…",
        outputCipher: mockCipherText("welcome", 100),
      });
      scrollChat();
    }, wait);
  }
});

onUnmounted(() => {
  if (queueTimer) clearTimeout(queueTimer);
});

function scrollChat() {
  nextTick(() => chatEnd.value?.scrollIntoView({ behavior: "smooth" }));
}

function openPrivacy(msg) {
  privacyPayload.value = {
    title: "隐私保护效果查看",
    imageUrl: msg.imageUrl,
    inputCipher: msg.inputCipher,
    textCipher: msg.textCipher,
    plainQuestion: msg.plainQuestion,
    plainOutput: msg.plainOutput ?? msg.content,
    outputCipher: msg.outputCipher,
    verifyStatus: msg.verifyStatus,
  };
  showPrivacy.value = true;
}

function pickImage() {
  fileInput.value?.click();
}

function onFileChange(e) {
  const file = e.target.files?.[0];
  if (!file) return;
  if (!file.type.startsWith("image/")) {
    message.warning("请选择图像文件");
    return;
  }
  const reader = new FileReader();
  reader.onload = () => {
    pendingImage.value = reader.result;
    message.info("图像已选择，点击发送执行密态推理");
  };
  reader.readAsDataURL(file);
  e.target.value = "";
}

function useSampleImage() {
  pendingImage.value = sampleMnistDataUrl();
  message.success("已加载内置样例图像");
}

async function sendMessage() {
  if (!session.value || session.value.status !== "ready") return;

  const text = inputText.value.trim();
  const image = pendingImage.value;

  if (!text && !image) return;

  if (text && !image) {
    inputText.value = "";
    addMessage(sessionId.value, {
      role: "user",
      type: "text",
      content: text,
      plainQuestion: text,
      textCipher: mockCipherText(`q-${text}`, 100),
    });
    scrollChat();
    const reply = mockDialogueReply(text);
    addMessage(sessionId.value, {
      role: "assistant",
      type: "text",
      content: reply,
      privacy: true,
      plainOutput: reply,
      outputCipher: mockCipherText(`a-${reply}`, 120),
    });
    scrollChat();
    return;
  }

  if (image) {
    inputText.value = "";
    pendingImage.value = null;
    inferring.value = true;
    updateSession(sessionId.value, { status: "running" });

    addMessage(sessionId.value, {
      role: "user",
      type: "image",
      content: text || "上传图像进行隐私推理",
      imageUrl: image,
      inputCipher: mockImageCipher(image),
      plainQuestion: text || "[图像输入]",
      textCipher: mockCipherText(`img-${image.slice(-20)}`, 80),
    });
    scrollChat();

    await new Promise((r) => setTimeout(r, 1200));

    const result = mockInferenceResult(image);
    addMessage(sessionId.value, {
      role: "assistant",
      type: "inference",
      content: result.plainText,
      privacy: true,
      imageUrl: image,
      inputCipher: mockImageCipher(image),
      plainOutput: result.plainText,
      outputCipher: result.cipherLogits,
      verifyStatus: result.verifyStatus,
      label: result.label,
      confidence: result.confidence,
    });

    inferring.value = false;
    updateSession(sessionId.value, { status: "ready" });
    scrollChat();
  }
}

function removeService() {
  deleteSession(sessionId.value);
  message.success("已删除演示服务");
  router.push("/demo");
}
</script>

<template>
  <div v-if="session" class="session-layout">
    <div class="chat-panel">
      <div class="chat-body">
        <div v-if="session.status === 'queuing'" class="queue-state">
          <div class="queue-icon">⏳</div>
          <p>服务还在排队中，预计需要 5～10 秒，请耐心等待哦～</p>
        </div>

        <template v-else>
          <div v-if="session.messages.length === 0" class="empty-hint">
            <p>👋 隐私推理演示已就绪</p>
            <div class="suggestions">
              <NButton
                v-for="s in suggestions"
                :key="s"
                size="small"
                secondary
                @click="inputText = s; sendMessage()"
              >
                {{ s }}
              </NButton>
            </div>
          </div>

          <div v-for="msg in session.messages" :key="msg.id" class="msg-row" :class="msg.role">
            <div class="bubble">
              <NImage v-if="msg.imageUrl && msg.role === 'user'" :src="msg.imageUrl" width="84" class="thumb" />
              <p>{{ msg.content }}</p>
              <div v-if="msg.role === 'assistant' && msg.privacy" class="privacy-row">
                <NTag size="tiny" round type="info">🔐 隐私模式</NTag>
                <NButton quaternary circle size="tiny" @click="openPrivacy(msg)">
                  <template #icon><NIcon><EyeOutline /></NIcon></template>
                </NButton>
              </div>
              <div v-if="msg.type === 'inference'" class="infer-meta">
                <NTag size="small" type="success">Verify Mock 通过</NTag>
                <span>密态 logits 已生成，可查看密文</span>
              </div>
            </div>
          </div>
          <div ref="chatEnd" />
        </template>
      </div>

      <div class="chat-footer">
        <div v-if="pendingImage" class="pending-preview">
          <NImage :src="pendingImage" width="48" />
          <span>已选图像 · 发送即执行密态推理</span>
          <NButton size="tiny" quaternary @click="pendingImage = null">取消</NButton>
        </div>
        <div class="input-row">
          <NButton quaternary circle :disabled="session.status !== 'ready'" @click="pickImage">
            <template #icon><NIcon><ImageOutline /></NIcon></template>
          </NButton>
          <NButton size="small" secondary :disabled="session.status !== 'ready'" @click="useSampleImage">
            样例图像
          </NButton>
          <NInput
            v-model:value="inputText"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 3 }"
            placeholder="提问了解密态流程，或上传图像后发送推理"
            :disabled="session.status !== 'ready'"
            @keydown.enter.exact.prevent="sendMessage"
          />
          <NButton
            type="primary"
            :disabled="session.status !== 'ready' || inferring"
            :loading="inferring"
            @click="sendMessage"
          >
            <template #icon><NIcon><SendOutline /></NIcon></template>
            发送
          </NButton>
        </div>
        <p class="disclaimer">演示内容由 Mock 生成，仅供理解 vPIN 密态推理流程，不代表生产推理结果。</p>
        <input ref="fileInput" type="file" accept="image/*" hidden @change="onFileChange" />
      </div>
    </div>

    <aside class="info-panel">
      <h3>{{ session.name }}</h3>
      <dl>
        <dt>当前状态</dt>
        <dd><NTag :type="statusLabel.type" size="small" round>{{ statusLabel.text }}</NTag></dd>
        <dt>使用模型</dt>
        <dd>{{ session.modelName }} ({{ session.modelVersion }})</dd>
        <dt>到期时间</dt>
        <dd>{{ expiresLabel }}</dd>
        <dt>会话 ID</dt>
        <dd><code>{{ session.id }}</code></dd>
      </dl>
      <NButton type="error" secondary block class="del-btn" @click="removeService">删除服务</NButton>
    </aside>

    <PrivacyEffectDrawer v-model:show="showPrivacy" :payload="privacyPayload" />
  </div>
</template>

<style scoped>
.session-layout {
  display: grid;
  grid-template-columns: 1fr 260px;
  gap: 16px;
  min-height: calc(100vh - 180px);
}

.chat-panel {
  background: linear-gradient(180deg, #eef2ff 0%, #f8fafc 100%);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.chat-body {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  min-height: 320px;
}

.queue-state {
  text-align: center;
  padding: 48px 16px;
  color: var(--color-text-secondary);
}

.queue-icon {
  font-size: 48px;
  margin-bottom: 12px;
}

.empty-hint {
  text-align: center;
  padding: 24px;
  color: var(--color-text-secondary);
}

.suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
  margin-top: 12px;
}

.msg-row {
  display: flex;
  margin-bottom: 14px;
}

.msg-row.user {
  justify-content: flex-end;
}

.msg-row.user .bubble {
  background: #fff;
  border: 1px solid var(--color-border);
}

.msg-row.assistant .bubble {
  background: #fff;
  border: 1px solid #dbeafe;
}

.bubble {
  max-width: 85%;
  padding: 12px 14px;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.6;
}

.bubble p {
  margin: 0;
}

.thumb {
  margin-bottom: 8px;
  border-radius: 6px;
  border: 1px solid var(--color-border);
}

.privacy-row {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 8px;
}

.infer-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
  font-size: 11px;
  color: var(--color-text-muted);
  flex-wrap: wrap;
}

.chat-footer {
  padding: 12px 16px 8px;
  background: rgba(255, 255, 255, 0.85);
  border-top: 1px solid var(--color-border);
}

.pending-preview {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  font-size: 12px;
  color: var(--color-text-secondary);
}

.input-row {
  display: flex;
  align-items: flex-end;
  gap: 8px;
}

.input-row :deep(.n-input) {
  flex: 1;
}

.disclaimer {
  margin: 8px 0 0;
  font-size: 11px;
  color: var(--color-text-muted);
  text-align: center;
}

.info-panel {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 20px;
  height: fit-content;
}

.info-panel h3 {
  margin: 0 0 16px;
  font-size: 16px;
  word-break: break-all;
}

.info-panel dl {
  margin: 0 0 20px;
}

.info-panel dt {
  font-size: 12px;
  color: var(--color-text-muted);
  margin-bottom: 4px;
}

.info-panel dd {
  margin: 0 0 12px;
  font-size: 13px;
}

.info-panel code {
  font-family: var(--font-mono);
  font-size: 11px;
  word-break: break-all;
}

.del-btn {
  margin-top: 8px;
}

@media (max-width: 900px) {
  .session-layout {
    grid-template-columns: 1fr;
  }
}
</style>
