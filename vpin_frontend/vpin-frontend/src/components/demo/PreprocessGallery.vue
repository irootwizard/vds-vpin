<template>
  <n-spin :show="loading && !items.length">
    <div v-if="items.length" class="gallery">
      <button
        v-for="item in items"
        :key="sampleKey(item)"
        type="button"
        class="gallery-item"
        :class="{ selected: isSelected(item), 'multi-selected': multiSelect && isMultiSelected(item) }"
        @click="onClick(item, $event)"
      >
        <img
          :src="`data:image/png;base64,${item.preview_png_base64}`"
          :alt="item.filename || `mnist ${item.mnist_index}`"
        />
        <span class="gallery-meta">{{ formatMeta(item) }}</span>
      </button>
    </div>
    <n-empty v-else-if="!loading" description="暂无预览" size="small" />
  </n-spin>
</template>

<script setup>
defineProps({
  items: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  lane: { type: String, default: "python" },
  multiSelect: { type: Boolean, default: false },
  isSelected: { type: Function, required: true },
  isMultiSelected: { type: Function, default: () => false },
  formatMeta: { type: Function, required: true },
  sampleKey: { type: Function, required: true },
});

const emit = defineEmits(["select"]);

function onClick(item, ev) {
  emit("select", item, {
    ctrl: ev.ctrlKey || ev.metaKey,
    shift: ev.shiftKey,
  });
}
</script>

<style scoped>
.gallery {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 8px;
  margin-top: 8px;
}

.gallery-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 6px;
  border: 2px solid #e0e0e0;
  border-radius: 6px;
  background: #fafafa;
  cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s;
}

.gallery-item:hover {
  border-color: #18a058;
}

.gallery-item.selected {
  border-color: #18a058;
  box-shadow: 0 0 0 1px #18a058;
  background: #f0faf4;
}

.gallery-item.multi-selected {
  border-color: #2080f0;
  background: #f0f7ff;
}

.gallery-item img {
  width: 56px;
  height: 56px;
  image-rendering: pixelated;
}

.gallery-meta {
  margin-top: 4px;
  font-size: 11px;
  color: #666;
  text-align: center;
  word-break: break-all;
}
</style>

