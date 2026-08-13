<script setup lang="ts">
defineProps<{
  displayAccuracy?: number;
  correctCount?: number;
  wrongCount?: number;
  total: number;
}>();
</script>

<template>
  <n-card size="small" title="批量准确度">
    <n-statistic label="推理准确度">
      {{ ((displayAccuracy ?? 0) * 100).toFixed(2) }}%
    </n-statistic>
    <n-space style="margin-top: 12px">
      <n-tag type="success">正确 {{ correctCount ?? 0 }} 张</n-tag>
      <n-tag type="error">错误 {{ wrongCount ?? 0 }} 张</n-tag>
      <n-tag>合计 {{ total }} 张</n-tag>
    </n-space>
  </n-card>
</template>
