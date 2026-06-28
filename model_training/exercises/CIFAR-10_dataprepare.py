import torch
from torch.utils.data import DataLoader, random_split
from torchvision import datasets, transforms

# 1) 定义训练/验证预处理
train_tf = transforms.Compose([
    transforms.RandomCrop(32, padding=4),      # 数据增强
    transforms.RandomHorizontalFlip(),
    transforms.ToTensor(),                      # [0,255] -> [0,1]
    transforms.Normalize((0.4914, 0.4822, 0.4465),
                         (0.2470, 0.2435, 0.2616))
])

val_tf = transforms.Compose([
    transforms.ToTensor(),
    transforms.Normalize((0.4914, 0.4822, 0.4465),
                         (0.2470, 0.2435, 0.2616))
])

# 2) 下载真实数据集（联网）
full_train = datasets.CIFAR10(
    root="./data", train=True, download=True, transform=train_tf
)
test_set = datasets.CIFAR10(
    root="./data", train=False, download=True, transform=val_tf
)

# 3) 划分训练/验证
train_size = int(0.9 * len(full_train))
val_size = len(full_train) - train_size
train_set, val_set = random_split(full_train, [train_size, val_size])

# random_split 后验证集仍用 train_tf；若你想严格区分增强，可自定义 Subset 包装再改 transform
# 这里先给通用流程版本

# 4) DataLoader
train_loader = DataLoader(train_set, batch_size=128, shuffle=True, num_workers=4, pin_memory=True)
val_loader   = DataLoader(val_set,   batch_size=256, shuffle=False, num_workers=4, pin_memory=True)
test_loader  = DataLoader(test_set,  batch_size=256, shuffle=False, num_workers=4, pin_memory=True)

# 5) 取一个 batch 检查
x, y = next(iter(train_loader))
print("train batch:", x.shape, y.shape, x.dtype, y.dtype)