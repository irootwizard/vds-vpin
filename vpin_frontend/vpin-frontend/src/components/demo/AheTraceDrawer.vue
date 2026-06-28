<template>
  <n-drawer :show="show" :width="520" placement="right" @update:show="(v) => emit('update:show', v)">
    <n-drawer-content :title="step?.title || '阶段详情'" closable>
      <template v-if="step">
        <n-tag :type="tagType" size="small" style="margin-bottom: 8px">{{ step.category }}</n-tag>
        <n-text depth="3" style="display: block; margin-bottom: 12px">{{ step.summary }}</n-text>

        <img
          v-if="previewB64"
          :src="`data:image/png;base64,${previewB64}`"
          alt="preview"
          class="trace-preview"
        />

        <n-descriptions v-if="descRows.length" :column="1" bordered size="small" style="margin-top: 12px">
          <n-descriptions-item v-for="row in descRows" :key="row.label" :label="row.label">
            <n-text code style="word-break: break-all">{{ row.value }}</n-text>
          </n-descriptions-item>
        </n-descriptions>

        <n-collapse v-if="logits.length" style="margin-top: 12px">
          <n-collapse-item title="Logits (float)" name="logits">
            <n-space>
              <n-tag v-for="(v, i) in logits" :key="i" :type="i === argmax ? 'success' : 'default'" size="small">
                {{ i }}: {{ typeof v === "number" ? v.toFixed(2) : v }}
              </n-tag>
            </n-space>
          </n-collapse-item>
        </n-collapse>

        <n-collapse style="margin-top: 12px">
          <n-collapse-item title="原始 JSON" name="json">
            <n-code :code="jsonText" language="json" word-wrap />
          </n-collapse-item>
        </n-collapse>
      </template>
      <n-empty v-else description="未选择阶段" />
    </n-drawer-content>
  </n-drawer>
</template>

<script setup>
import { computed } from "vue";
import { TRACE_CATEGORIES } from "../../constants/aheFlow.js";

const props = defineProps({
  show: { type: Boolean, default: false },
  step: { type: Object, default: null },
});

const emit = defineEmits(["update:show"]);

const tagType = computed(() => TRACE_CATEGORIES[props.step?.category] || "default");

const previewB64 = computed(() => {
  const d = props.step?.detail;
  if (!d) return "";
  return d.preview_png_base64 || d.normalized?.preview_png_base64 || "";
});

const logits = computed(() => props.step?.detail?.logits_float || []);
const argmax = computed(() => props.step?.detail?.argmax ?? -1);

const descRows = computed(() => {
  const d = props.step?.detail;
  if (!d) return [];
  const rows = [];
  const push = (label, value) => {
    if (value != null && value !== "") rows.push({ label, value: String(value) });
  };

  push("数据形式", d.data_form);
  push("层 / 算子", d.layer);
  push("服务端操作", d.server_op || d.operation);
  push("客户端操作", d.client_action || d.action);
  push("phase_id", d.phase_id);
  push("shape", fmtShape(d.shape || d.decrypted?.shape || d.output?.shape || d.plain_input?.shape));
  push("dtype", d.dtype || d.decrypted?.dtype || d.output?.dtype);
  push("element_type", d.element_type || d.c1?.element_type);
  push("fixed_point_bits", d.fixed_point_bits || d.decrypted?.fixed_point_bits);
  push("shift_bits", d.shift_bits);
  push("direction", d.direction);
  push("min", d.min ?? d.decrypted?.min ?? d.output?.min);
  push("max", d.max ?? d.decrypted?.max ?? d.output?.max);
  push("mean", d.mean ?? d.decrypted?.mean ?? d.output?.mean);
  push("sample", fmtArr(d.sample || d.decrypted?.sample || d.output?.sample));
  push("wire_chunks", d.wire_chunks ? JSON.stringify(d.wire_chunks) : null);
  push("input_digest_hex", d.input_digest_hex);
  push("weights_digest_hex", d.weights_digest_hex);
  push("network_id", d.network_id);
  push("model_id", d.model_id);
  push("note", d.note);

  if (d.c1 && d.c2) {
    push("c1 shape", fmtShape(d.c1.shape));
    push("c2 shape", fmtShape(d.c2.shape));
  }

  return rows;
});

const jsonText = computed(() => JSON.stringify(props.step?.detail || {}, null, 2));

function fmtShape(s) {
  if (!s) return "";
  return Array.isArray(s) ? s.join(" × ") : String(s);
}

function fmtArr(a) {
  if (!a || !a.length) return "";
  return a.map((x) => (typeof x === "number" ? x.toFixed(4) : x)).join(", ");
}
</script>

<style scoped>
.trace-preview {
  width: 112px;
  height: 112px;
  image-rendering: pixelated;
  border: 1px solid #e0e0e0;
  border-radius: 4px;
}
</style>
