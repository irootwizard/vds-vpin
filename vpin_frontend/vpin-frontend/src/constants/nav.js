/**
 * 侧栏导航配置（对照 templates/ 隐语云参考图）
 *
 * vPIN 实际能力：可验证隐私推理（AHE + CP-SNARK），不含模型训练/优化/在线服务。
 * 未实现项在 UI 中不出现；密态流程、日志等以占位组件呈现。
 */

/** @typedef {{ key: string, label: string, route: string, implemented: boolean }} NavLeaf */

export const PLATFORM_NAME = "VDS-VPIN";
export const PLATFORM_SUBTITLE = "可验证隐私推理平台";

/**
 * 隐语云有而 vPIN 不包含的能力（仅文档记录，不渲染到菜单）
 */
export const EXCLUDED_FEATURES = [
  "模型训练",
  "模型优化",
  "在线服务",
  "大模型对话样板间",
  "联邦多方节点管理",
];
