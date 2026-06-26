<script setup>
import { ref, computed } from "vue";
import { NDrawer, NDrawerContent, NButton, NTag, NImage } from "naive-ui";

const props = defineProps({
  show: { type: Boolean, default: false },
  payload: { type: Object, default: null },
});

const emit = defineEmits(["update:show"]);

const showPlain = ref(false);

const title = computed(() => props.payload?.title ?? "隐私保护效果查看");

function close() {
  emit("update:show", false);
  showPlain.value = false;
}
</script>

<template>
  <NDrawer :show="show" :width="420" placement="right" @update:show="emit('update:show', $event)">
    <NDrawerContent closable :title="title" @close="close">
      <div class="drawer-toolbar">
        <NTag size="small" type="info" round>🔐 密态视图</NTag>
        <NButton size="small" :type="showPlain ? 'primary' : 'default'" @click="showPlain = !showPlain">
          {{ showPlain ? "切换密文" : "切换明文" }}
        </NButton>
      </div>

      <template v-if="payload">
        <section v-if="payload.imageUrl" class="block">
          <h4>输入图像</h4>
          <NImage v-if="showPlain" :src="payload.imageUrl" width="112" />
          <div v-else class="cipher-box">{{ payload.inputCipher?.tensor }}</div>
          <p class="meta">{{ payload.inputCipher?.encoding }} · {{ payload.inputCipher?.shape }}</p>
        </section>

        <section v-if="payload.textCipher" class="block">
          <h4>对话内容</h4>
          <div class="cipher-box user-cipher">
            {{ showPlain ? payload.plainQuestion : payload.textCipher }}
          </div>
        </section>

        <section class="block">
          <h4>推理 / 回答输出</h4>
          <div class="cipher-box output-cipher">
            {{ showPlain ? payload.plainOutput : payload.outputCipher }}
          </div>
          <p v-if="payload.verifyStatus" class="meta">
            Verify：{{ payload.verifyStatus === "passed" ? "通过（Mock）" : "—" }}
          </p>
        </section>
      </template>
    </NDrawerContent>
  </NDrawer>
</template>

<style scoped>
.drawer-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.block {
  margin-bottom: 20px;
}

.block h4 {
  margin: 0 0 8px;
  font-size: 13px;
  color: var(--color-text-secondary);
}

.cipher-box {
  font-family: var(--font-mono);
  font-size: 11px;
  line-height: 1.5;
  word-break: break-all;
  background: #f1f5f9;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: 12px;
  max-height: 160px;
  overflow: auto;
}

.output-cipher {
  background: #eff6ff;
  border-color: #bfdbfe;
}

.user-cipher {
  background: #fafafa;
}

.meta {
  margin: 6px 0 0;
  font-size: 11px;
  color: var(--color-text-muted);
}
</style>
