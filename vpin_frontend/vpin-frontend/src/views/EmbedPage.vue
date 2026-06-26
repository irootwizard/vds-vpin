<script setup>
import { computed } from "vue";
import { useRoute } from "vue-router";

const route = useRoute();

const frameSrc = computed(
  () => `/vpin/pages/${route.meta.page}?embed=1`,
);
</script>

<template>
  <div class="embed-wrap">
    <iframe
      :key="frameSrc"
      :src="frameSrc"
      :title="route.meta.title || '页面'"
      class="embed-frame"
    />
  </div>
</template>

<style scoped>
.embed-wrap {
  height: calc(100vh - 64px - 48px - 140px);
  min-height: 420px;
  border-radius: 14px;
  overflow: hidden;
  background: #fff;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.06);
  border: 1px solid rgba(226, 232, 240, 0.9);
}

.embed-frame {
  width: 100%;
  height: 100%;
  border: 0;
  display: block;
  background: #fff;
}
</style>
