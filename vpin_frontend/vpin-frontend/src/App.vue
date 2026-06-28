<script setup>
import { NMessageProvider, NDialogProvider } from "naive-ui";
</script>

<template>
  <NMessageProvider>
    <NDialogProvider>
      <router-view />
    </NDialogProvider>
  </NMessageProvider>
</template>
