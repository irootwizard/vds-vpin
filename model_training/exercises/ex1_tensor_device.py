import time

import torch


def timed_matmul(
    device: torch.device,
    dtype: torch.dtype,
    n: int = 2048,
    warmup: int = 5,
    repeat: int = 20,
) -> tuple[float, float]:
    # 在指定设备和精度上创建随机矩阵，n 表示矩阵边长。
    x = torch.randn(n, n, device=device, dtype=dtype)
    y = torch.randn(n, n, device=device, dtype=dtype)

    # 预热：触发内核编译/缓存，避免首轮异常慢影响统计。
    for _ in range(warmup):
        _ = x @ y
    if device.type == "cuda":
        torch.cuda.synchronize()

    times_ms: list[float] = []
    for _ in range(repeat):
        if device.type == "cuda":
            start_event = torch.cuda.Event(enable_timing=True)
            end_event = torch.cuda.Event(enable_timing=True)
            start_event.record()
            z = x @ y
            end_event.record()
            torch.cuda.synchronize()
            elapsed_ms = start_event.elapsed_time(end_event)
        else:
            start = time.perf_counter()
            z = x @ y
            elapsed_ms = (time.perf_counter() - start) * 1000.0
        # 防止编译器/运行时把结果优化掉。
        _ = z[0, 0].item()
        times_ms.append(elapsed_ms)

    times_ms.sort()
    median_ms = times_ms[len(times_ms) // 2]
    mean_ms = sum(times_ms) / len(times_ms)
    return median_ms, mean_ms


def main() -> None:
    # torch.device 用于显式指定张量所在设备。
    cpu = torch.device("cpu")
    has_cuda = torch.cuda.is_available()
    print(f"torch={torch.__version__}")
    print(f"cuda_available={has_cuda}")
    if has_cuda:
        print(f"cuda_device={torch.cuda.get_device_name(0)}")
        # 允许 TF32，可提升部分 GPU 上的 float32 matmul 吞吐。
        torch.backends.cuda.matmul.allow_tf32 = True

    # Step 1: CPU float32 baseline
    t_cpu_median, t_cpu_mean = timed_matmul(cpu, torch.float32, n=2048, warmup=2, repeat=8)
    print(f"[CPU float32] median={t_cpu_median:.3f}ms mean={t_cpu_mean:.3f}ms")

    # Step 2: CUDA float32
    if has_cuda:
        # float16 常用于提速和省显存，但数值精度更低。
        t_gpu_fp16_median, t_gpu_fp16_mean = timed_matmul(torch.device("cuda:0"), torch.float16)
        print(f"[GPU float16] median={t_gpu_fp16_median:.3f}ms mean={t_gpu_fp16_mean:.3f}ms")

        t_gpu_fp32_median, t_gpu_fp32_mean = timed_matmul(torch.device("cuda:0"), torch.float32)
        print(f"[GPU float32] median={t_gpu_fp32_median:.3f}ms mean={t_gpu_fp32_mean:.3f}ms")

        for n in (1024, 4096):
            t16_median, t16_mean = timed_matmul(torch.device("cuda:0"), torch.float16, n=n)
            t32_median, t32_mean = timed_matmul(torch.device("cuda:0"), torch.float32, n=n)
            print(f"[GPU matrix {n} float16] median={t16_median:.3f}ms mean={t16_mean:.3f}ms")
            print(f"[GPU matrix {n} float32] median={t32_median:.3f}ms mean={t32_mean:.3f}ms")

    # TODO:
    # 1) 把 repeat 改成 50，看统计值是否更稳定
    # 2) 对比 median 和 mean，理解离群值影响

if __name__ == "__main__":
    main()
