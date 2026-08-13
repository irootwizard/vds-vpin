<script setup lang="ts">
import { NEmpty } from "naive-ui";
import PageCard from "@/components/PageCard.vue";

defineProps<{ title: string }>();
</script>

<template>
  <PageCard>
    <h1 class="page-title">{{ title }}</h1>
    <NEmpty description="功能开发中" />
  </PageCard>
</template>
