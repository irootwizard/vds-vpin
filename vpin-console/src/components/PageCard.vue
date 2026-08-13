<template>
  <div class="page-card">
    <slot />
  </div>
</template>

<style scoped>
.page-card {
  background: var(--color-surface);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border);
  box-shadow: var(--shadow-sm);
  padding: var(--space-5);
  min-height: 120px;
}
</style>
