/** 演示用推理任务数据（后续对接 GET /api/v1/sessions） */

export const TASK_STATUS = {
  running: { label: "运行中", type: "info" },
  completed: { label: "已完成", type: "success" },
  failed: { label: "失败", type: "error" },
  pending: { label: "等待中", type: "warning" },
};

export const mockTasks = [
  {
    id: "vpin-demo-001",
    name: "mnist_cnn_a_infer",
    model: "CNN Network A",
    modelVersion: "v1.0-paper",
    status: "completed",
    scheme: "AHE + CP-SNARK",
    startedAt: "2026-06-08 10:12:04",
    endedAt: "2026-06-08 10:18:33",
    description: "论文网络 A 演示推理会话",
  },
  {
    id: "vpin-demo-002",
    name: "lenet5_verify_run",
    model: "LeNet-5",
    modelVersion: "table2",
    status: "running",
    scheme: "AHE",
    startedAt: "2026-06-10 09:01:22",
    endedAt: "—",
    description: "LeNet 准确率实验（Mock）",
  },
  {
    id: "vpin-demo-003",
    name: "conv_layer_bench",
    model: "Conv Layer",
    modelVersion: "fig3",
    status: "failed",
    scheme: "AHE + CP-SNARK",
    startedAt: "2026-06-09 14:20:11",
    endedAt: "2026-06-09 14:22:05",
    description: "卷积层基准（截断轮次超时 Mock）",
  },
];

export function getTaskById(id) {
  return mockTasks.find((t) => t.id === id) ?? null;
}

export const mockLogs = `2026-06-08 10:12:04 INFO  vpin-client|session.py:42    SessionStart client_version=0.1.0 ahe_params_id=E2-default
2026-06-08 10:12:05 INFO  vpin-server|handshake.py:88  SessionAccept session_id=vpin-demo-001
2026-06-08 10:12:06 INFO  vpin-client|commit.py:31     ModelBinding cm_W verified OK (Mock)
2026-06-08 10:12:08 INFO  vpin-client|ahe.py:120       Input encrypted, cm_x committed
2026-06-08 10:12:15 INFO  vpin-server|infer.py:204     Homomorphic layer 1/5 complete
2026-06-08 10:12:18 INFO  vpin-client|truncate.py:67   TruncateRequest bits=16 → client relu/shift (Mock)
2026-06-08 10:18:20 INFO  vpin-client|challenge.py:55  ClientChallenge γ sampled locally
2026-06-08 10:18:28 INFO  vpin-server|prove.py:112     Proof π generated via cp-snark bridge
2026-06-08 10:18:33 INFO  vpin-client|verify.py:89     Verify PASSED (coverage: partial, see report)`;

export const CONFIDENTIAL_FLOW_STEPS = [
  {
    title: "Setup：AHE 参数与预计算表",
    desc: "客户端生成密钥对，协商曲线 E2，加载 BSGS 预计算表（当前 Mock）。",
    status: "done",
  },
  {
    title: "Commit：模型承诺 cm_W",
    desc: "绑定远程模型权重承诺，发送输入前校验指纹（对接模型中心 API）。",
    status: "done",
  },
  {
    title: "Commit：输入承诺 cm_x",
    desc: "图像定点化 → AHE 加密 → 上传密文输入。",
    status: "done",
  },
  {
    title: "Infer：同态推理与客户端截断",
    desc: "服务端同态卷积/FC；收到 TruncateRequest 后客户端解密、ReLU、重加密。",
    status: "active",
  },
  {
    title: "Challenge：客户端采样 γ",
    desc: "根据会话 #PtAdd/#PtMul 统计在客户端本地采样挑战（禁止服务端代采）。",
    status: "pending",
  },
  {
    title: "Prove：服务端生成 π",
    desc: "收到 γ 后调用 cp-snark-full 证明路径（桥接开发中）。",
    status: "pending",
  },
  {
    title: "Verify：客户端本地验证",
    desc: "verifier_run 等价逻辑；生成验证报告并明示证明覆盖范围。",
    status: "pending",
  },
];
