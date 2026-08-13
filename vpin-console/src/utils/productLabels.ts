/** 产品展示用标签（隐藏内部实现名） */

export function inferenceEngineLabel(engine?: string | null): string {
  switch (engine) {
    case "rust-ark":
      return "Network A · Arkworks";
    case "rust-ec":
      return "Network A · EC";
    case "timing-demo":
      return "密态推理";
    case "python":
      return "Network A · Python";
    default:
      return engine ? `Network A · ${engine}` : "Network A";
  }
}

export function linkStatusLabel(
  status?: string,
  role: "backend" | "ahe" = "ahe",
): string {
  switch (status) {
    case "connected":
      return "已连接";
    case "checking":
      return "同步中";
    case "disconnected":
      return role === "backend" ? "未启用" : "未连接";
    case "standalone":
      return role === "backend" ? "便携内置" : "已连接";
    default:
      return "未知";
  }
}

export function clientKindLabel(isDesktop: boolean): string {
  return isDesktop ? "桌面客户端" : "Web 客户端";
}
