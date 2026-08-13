<script setup lang="ts">
import { computed } from "vue";
import { NForm, NFormItem, NInput } from "naive-ui";
import PageCard from "@/components/PageCard.vue";
import { aheServerApiBase, backendApiBase } from "@/config/endpoints";
import { clientKindLabel } from "@/utils/productLabels";
import { isTauri } from "@/services/aheClient";

const clientLabel = computed(() => clientKindLabel(isTauri()));
</script>

<template>
  <PageCard>
    <h1 class="page-title">环境与连接</h1>
    <p class="page-subtitle">端点与会话配置</p>
    <NForm label-placement="left" label-width="160">
      <NFormItem label="客户端">
        <NInput :value="clientLabel" disabled />
      </NFormItem>
      <NFormItem label="backend_url">
        <NInput :value="backendApiBase()" disabled />
      </NFormItem>
      <NFormItem label="ahe_server_url">
        <NInput :value="aheServerApiBase()" disabled />
      </NFormItem>
      <NFormItem label="大模型推理">
        <NInput value="DeepSeek · TLS" disabled />
      </NFormItem>
    </NForm>
  </PageCard>
</template>
