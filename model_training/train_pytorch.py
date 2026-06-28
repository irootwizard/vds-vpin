import argparse
from dataclasses import dataclass

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset
from torchvision import datasets, transforms


@dataclass
class PTConfig:
    dataset: str = "mnist"
    data_dir: str = "./data"
    epochs: int = 3
    batch_size: int = 64
    lr: float = 1e-3
    num_workers: int = 0


class SimpleCNN(nn.Module):
    def __init__(self, in_channels: int, image_size: int, num_classes: int) -> None:
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(in_channels, 16, kernel_size=3, padding=1),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
            nn.Conv2d(16, 32, kernel_size=3, padding=1),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
        )
        flattened = 32 * (image_size // 4) * (image_size // 4)
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Linear(flattened, 128),
            nn.ReLU(inplace=True),
            nn.Linear(128, num_classes),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.features(x)
        return self.classifier(x)


def build_dataloaders(cfg: PTConfig) -> tuple[DataLoader, DataLoader, int, int, int]:
    dataset = cfg.dataset.lower()
    if dataset == "mnist":
        transform = transforms.Compose([transforms.ToTensor()])
        train_ds = datasets.MNIST(root=cfg.data_dir, train=True, download=True, transform=transform)
        test_ds = datasets.MNIST(root=cfg.data_dir, train=False, download=True, transform=transform)
        return (
            DataLoader(train_ds, batch_size=cfg.batch_size, shuffle=True, num_workers=cfg.num_workers),
            DataLoader(test_ds, batch_size=cfg.batch_size, shuffle=False, num_workers=cfg.num_workers),
            1,
            28,
            10,
        )
    if dataset == "cifar10":
        transform = transforms.Compose([transforms.ToTensor()])
        train_ds = datasets.CIFAR10(root=cfg.data_dir, train=True, download=True, transform=transform)
        test_ds = datasets.CIFAR10(root=cfg.data_dir, train=False, download=True, transform=transform)
        return (
            DataLoader(train_ds, batch_size=cfg.batch_size, shuffle=True, num_workers=cfg.num_workers),
            DataLoader(test_ds, batch_size=cfg.batch_size, shuffle=False, num_workers=cfg.num_workers),
            3,
            32,
            10,
        )
    if dataset == "synthetic":
        n_train, n_test = 1024, 256
        channels, size, num_classes = 1, 28, 10
        x_train = torch.rand(n_train, channels, size, size)
        y_train = torch.randint(0, num_classes, (n_train,))
        x_test = torch.rand(n_test, channels, size, size)
        y_test = torch.randint(0, num_classes, (n_test,))
        train_ds = TensorDataset(x_train, y_train)
        test_ds = TensorDataset(x_test, y_test)
        return (
            DataLoader(train_ds, batch_size=cfg.batch_size, shuffle=True, num_workers=cfg.num_workers),
            DataLoader(test_ds, batch_size=cfg.batch_size, shuffle=False, num_workers=cfg.num_workers),
            channels,
            size,
            num_classes,
        )
    raise ValueError(f"Unsupported dataset: {cfg.dataset}")


def evaluate(model: nn.Module, loader: DataLoader, device: torch.device) -> float:
    model.eval()
    correct = 0
    total = 0
    with torch.no_grad():
        for x, y in loader:
            x, y = x.to(device), y.to(device)
            logits = model(x)
            pred = logits.argmax(dim=1)
            correct += (pred == y).sum().item()
            total += y.size(0)
    return correct / max(total, 1)


def train(cfg: PTConfig) -> None:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    train_loader, test_loader, in_channels, image_size, num_classes = build_dataloaders(cfg)
    model = SimpleCNN(in_channels=in_channels, image_size=image_size, num_classes=num_classes).to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=cfg.lr)

    for epoch in range(cfg.epochs):
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

        avg_loss = running_loss / max(len(train_loader), 1)
        acc = evaluate(model, test_loader, device)
        print(f"[PyTorch] Epoch {epoch + 1}/{cfg.epochs} - loss: {avg_loss:.4f}, test_acc: {acc:.4f}")


def parse_args() -> PTConfig:
    parser = argparse.ArgumentParser(description="Simple CNN training with PyTorch")
    parser.add_argument("--dataset", type=str, default="mnist", choices=["mnist", "cifar10", "synthetic"])
    parser.add_argument("--data-dir", type=str, default="./data")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--num-workers", type=int, default=0)
    args = parser.parse_args()
    return PTConfig(
        dataset=args.dataset,
        data_dir=args.data_dir,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        num_workers=args.num_workers,
    )


if __name__ == "__main__":
    train(parse_args())
