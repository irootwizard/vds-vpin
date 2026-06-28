import torch

print('torch=', torch.__version__)
print('cuda_compiled=', torch.version.cuda)
print('cuda_available=', torch.cuda.is_available())

assert torch.cuda.is_available(), 'CUDA not available'
d = torch.device('cuda:0')
print('device=', torch.cuda.get_device_name(0))
a = torch.randn(2048, 2048, device=d)
b = torch.randn(2048, 2048, device=d)
c = a @ b
torch.cuda.synchronize()
print('matmul_ok=', c.shape, c.device)
print('memory_alloc_MB=', round(torch.cuda.memory_allocated(0) / 1024 / 1024, 2))
