import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader
from torchvision import datasets, transforms


class SmallCNN(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        # Sequential 按定义顺序堆叠网络层，适合简单前向结构。
        self.net = nn.Sequential(
            # 28x28 -> 28x28（padding=1 保持尺寸）
            nn.Conv2d(1, 16, kernel_size=3, padding=1),
            nn.ReLU(inplace=True),
            # 28x28 -> 14x14
            nn.MaxPool2d(2),
            nn.Conv2d(16, 32, kernel_size=3, padding=1),
            nn.ReLU(inplace=True),
            # 14x14 -> 7x7
            nn.MaxPool2d(2),
            nn.Flatten(),
            # 32*7*7 展平后接全连接分类。
            nn.Linear(32 * 7 * 7, 128),
            nn.ReLU(inplace=True),
            nn.Linear(128, 10),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


def evaluate(model: nn.Module, loader: DataLoader, device: torch.device) -> float:
    # eval() 切换到评估模式（如 Dropout/BN 会改变行为）。
    model.eval()
    correct = 0
    total = 0
    # 评估不需要梯度，关闭 autograd。
    with torch.no_grad():
        for x, y in loader:
            x, y = x.to(device), y.to(device)
            # argmax(dim=1) 取每个样本预测概率最大的类别索引。
            pred = model(x).argmax(dim=1)
            correct += (pred == y).sum().item()
            total += y.size(0)
    return correct / max(total, 1)


def main() -> None:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"device={device}")

    # ToTensor: 把 [0,255] 的 PIL 图像转成 [0,1] 的张量。
    transform = transforms.ToTensor()
    train_ds = datasets.MNIST(root="./data", train=True, download=True, transform=transform)
    test_ds = datasets.MNIST(root="./data", train=False, download=True, transform=transform)

    # shuffle=True 仅用于训练集，打乱顺序可提升泛化。
    train_loader = DataLoader(train_ds, batch_size=64, shuffle=True)
    test_loader = DataLoader(test_ds, batch_size=256, shuffle=False)

    model = SmallCNN().to(device)
    optimizer = optim.Adam(model.parameters(), lr=1e-3)
    criterion = nn.CrossEntropyLoss()

    epochs = 2
    for epoch in range(epochs):
        # train() 切换到训练模式。
        model.train()
        running_loss = 0.0
        for x, y in train_loader:
            x, y = x.to(device), y.to(device)
            optimizer.zero_grad()
            logits = model(x)
            loss = criterion(logits, y)
            loss.backward()
            optimizer.step()
            running_loss += loss.item()

        test_acc = evaluate(model, test_loader, device)
        avg_loss = running_loss / max(len(train_loader), 1)
        print(f"epoch={epoch + 1}/{epochs} loss={avg_loss:.4f} test_acc={test_acc:.4f}")

    # TODO:
    # 1) 把 epochs 改成 5，观察 test_acc 提升
    # 2) 尝试 batch_size=128，比较速度和精度
    # 3) 保存模型参数并写一个加载后推理 10 张图的小脚本


if __name__ == "__main__":
    main()
