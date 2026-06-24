<script setup>
import { NModal, NButton, NScrollbar } from "naive-ui";

defineProps({
  show: { type: Boolean, default: false },
});

const emit = defineEmits(["update:show", "agree"]);
</script>

<template>
  <NModal
    :show="show"
    preset="card"
    title="服务须知"
    style="width: 640px; max-width: 92vw"
    :mask-closable="false"
    @update:show="emit('update:show', $event)"
  >
    <NScrollbar style="max-height: 420px">
      <div class="notice-body">
        <p><strong>本须知发布时间：2026-06-10</strong></p>
        <p>
          欢迎使用 <strong>VDS-VPIN 可验证隐私推理平台</strong> 隐私样板间。本平台面向
          vPIN 论文复现与实验，提供 <strong>图像隐私推理演示</strong>（AHE 同态计算 + 可验证证明链路说明），
          <strong>非</strong> 大模型训练、在线对话商用服务。
        </p>
        <ol>
          <li>
            样板间展示密态推理过程中输入/输出的密文形态，以及推理结论；密文为 Mock 数据，用于理解协议流程。
          </li>
          <li>
            演示模型来自论文仓库预训练权重（CNN A–E、LeNet 等），平台不保证与生产环境性能一致。
          </li>
          <li>
            完整 CP-SNARK 验证与证明覆盖范围以验证报告为准，不得将演示结果等同于论文全部安全命题。
          </li>
          <li>
            您须合法使用本平台，不得用于侵犯隐私、传播违法内容或危害网络安全的行为；实验数据请自行脱敏。
          </li>
        </ol>
        <p class="muted">点击「同意并继续」即表示已阅读并理解上述说明。</p>
      </div>
    </NScrollbar>
    <template #footer>
      <NButton type="primary" @click="emit('agree')">同意并继续</NButton>
    </template>
  </NModal>
</template>

<style scoped>
.notice-body {
  font-size: 14px;
  line-height: 1.7;
  color: var(--color-text-primary);
}

.notice-body ol {
  padding-left: 1.2em;
}

.notice-body li {
  margin-bottom: 8px;
}

.muted {
  color: var(--color-text-secondary);
  font-size: 13px;
}
</style>
