/** Mock AHE 密文与图像推理（演示用，非真实密码学） */

export function mockCipherText(seed, length = 120) {
  const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  let out = "";
  let h = 0;
  for (let i = 0; i < seed.length; i++) h = (h * 31 + seed.charCodeAt(i)) >>> 0;
  for (let i = 0; i < length; i++) {
    h = (h * 1103515245 + 12345) >>> 0;
    out += chars[h % chars.length];
  }
  return out;
}

export function mockImageCipher(imageDataUrl) {
  const seed = imageDataUrl.slice(-64);
  return {
    tensor: mockCipherText(`ahe-in-${seed}`, 160),
    shape: "[1, 1, 28, 28]",
    encoding: "fixed-point-16bit + AHE-ElGamal (Mock)",
  };
}

export function mockInferenceResult(imageDataUrl) {
  const labels = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"];
  const idx = Math.abs(hashStr(imageDataUrl)) % 10;
  const label = labels[idx];
  const confidence = (82 + (hashStr(imageDataUrl) % 15)).toFixed(1);
  const seed = imageDataUrl.slice(0, 48);
  return {
    label,
    confidence,
    cipherLogits: mockCipherText(`ahe-out-${seed}`, 140),
    plainText: `预测类别：${label}（置信度 ${confidence}%）`,
    verifyStatus: "passed",
    note: "Mock 推理结果，后续对接 vpin-backend 同态推理",
  };
}

function hashStr(s) {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return h;
}

/** 内置 28×28 演示图（MNIST 风格点阵） */
export function sampleMnistDataUrl() {
  const canvas = document.createElement("canvas");
  canvas.width = 28;
  canvas.height = 28;
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#000";
  ctx.fillRect(0, 0, 28, 28);
  ctx.fillStyle = "#fff";
  const pattern = [
    [8, 6], [9, 6], [10, 6], [11, 6], [12, 6],
    [7, 7], [13, 7], [7, 8], [13, 8], [7, 9], [13, 9],
    [7, 10], [8, 10], [9, 10], [10, 10], [11, 10], [12, 10], [13, 10],
    [7, 11], [13, 11], [8, 12], [9, 12], [10, 12], [11, 12], [12, 12],
    [9, 13], [10, 13], [11, 13],
  ];
  pattern.forEach(([x, y]) => ctx.fillRect(x, y, 1, 1));
  return canvas.toDataURL("image/png");
}

export function mockDialogueReply(question) {
  const q = question.toLowerCase();
  if (q.includes("加密") || q.includes("密态") || q.includes("ahe")) {
    return "在 vPIN 演示中，输入图像经定点化后由 AHE 加密为密文张量，服务端仅在密文上同态计算。点击回答旁的「眼睛」图标可查看密文与明文对照（Mock）。";
  }
  if (q.includes("验证") || q.includes("证明") || q.includes("snark")) {
    return "完整流程包含客户端挑战 γ 与 CP-SNARK 本地 Verify。当前样板间仅演示密态推理与密文展示，证明链路见任务详情「密态流程」Tab。";
  }
  if (q.includes("模型") || q.includes("cnn") || q.includes("lenet")) {
    return "样板间使用论文已验证的 CNN/LeNet 权重包，不含大模型对话训练。上传 28×28 灰度图或点击「样例图像」即可体验图像隐私推理。";
  }
  return "我是 vPIN 隐私推理演示助手。您可以：① 上传图像执行密态推理；② 提问了解 AHE/验证流程；③ 点击 🔐 旁的眼睛查看密文效果。";
}
