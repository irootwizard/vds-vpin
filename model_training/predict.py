"""Run inference on arbitrary images with trained CIFAR-10 and MNIST models."""

from __future__ import annotations

import sys
from pathlib import Path

import torch
import torch.nn.functional as F
from torchvision import transforms
from PIL import Image, ImageOps

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from model_training.new_lenet.model import LeNet5_CIFAR10
from model_training.new_resnet.model import ResNet18
from model_training.new_lenet_mnist.model import LeNet5_MNIST

CIFAR10_CLASSES = ["airplane", "automobile", "bird", "cat", "deer",
                   "dog", "frog", "horse", "ship", "truck"]
CIFAR10_CLASSES_ZH = ["飞机", "汽车", "鸟", "猫", "鹿",
                       "狗", "青蛙", "马", "船", "卡车"]
MNIST_CLASSES = [str(i) for i in range(10)]

CHECKPOINTS = {
    "LeNet5_CIFAR10": REPO / "model_training/outputs/lenet_20260629_053826/checkpoint.pt",
    "ResNet18_CIFAR10": REPO / "model_training/outputs/resnet18_20260629_054142/checkpoint.pt",
    "LeNet5_MNIST": REPO / "model_training/outputs/lenet_mnist_20260629_070515/checkpoint.pt",
}

CIFAR10_TRANSFORM = transforms.Compose([
    transforms.Resize((32, 32)),
    transforms.ToTensor(),
    transforms.Normalize(mean=(0.4914, 0.4822, 0.4465),
                         std=(0.2470, 0.2435, 0.2616)),
])

MNIST_TRANSFORM = transforms.Compose([
    transforms.Resize((32, 32)),
    transforms.ToTensor(),
    transforms.Normalize(mean=(0.1307,), std=(0.3081,)),
])


def auto_invert(img: Image.Image) -> Image.Image:
    """Invert if background is bright (black-on-white → white-on-black)."""
    gray = img.convert("L")
    mean_brightness = sum(gray.getdata()) / (gray.width * gray.height)
    if mean_brightness > 127:
        img = ImageOps.invert(img)
        print("    [自动反转: 检测到白底黑字，已转为白字黑底]")
    return img


def load_models(device: torch.device) -> dict:
    result = {}
    model_classes = {
        "LeNet5_CIFAR10": LeNet5_CIFAR10(),
        "ResNet18_CIFAR10": ResNet18(),
        "LeNet5_MNIST": LeNet5_MNIST(),
    }
    for name, model in model_classes.items():
        ckpt = torch.load(CHECKPOINTS[name], map_location=device, weights_only=False)
        model.load_state_dict(ckpt["state_dict"])
        model.to(device).eval()
        result[name] = model
    return result


def predict_cifar10(image_path: str, models: dict, device: torch.device):
    img = Image.open(image_path).convert("RGB")
    x = CIFAR10_TRANSFORM(img).unsqueeze(0).to(device)
    print(f"\n[CIFAR-10] {Path(image_path).name}  ({img.size[0]}x{img.size[1]})")
    print("-" * 45)
    with torch.no_grad():
        for name in ["LeNet5_CIFAR10", "ResNet18_CIFAR10"]:
            logits = models[name](x)
            probs = F.softmax(logits, dim=1)[0]
            top3 = probs.topk(3)
            label = "LeNet5" if "LeNet5" in name else "ResNet18"
            print(f"  [{label}]")
            for prob, idx in zip(top3.values, top3.indices):
                i = idx.item()
                marker = " <--" if prob == top3.values[0] else "    "
                print(f"    {CIFAR10_CLASSES_ZH[i]:<3s}({CIFAR10_CLASSES[i]:<12s}): {prob.item()*100:5.1f}%{marker}")


def predict_mnist(image_path: str, models: dict, device: torch.device):
    img = Image.open(image_path).convert("L")  # grayscale
    img = auto_invert(img)
    x = MNIST_TRANSFORM(img).unsqueeze(0).to(device)
    print(f"\n[MNIST] {Path(image_path).name}  ({img.size[0]}x{img.size[1]})")
    print("-" * 45)
    with torch.no_grad():
        logits = models["LeNet5_MNIST"](x)
        probs = F.softmax(logits, dim=1)[0]
        top3 = probs.topk(3)
        print("  [LeNet5_MNIST]")
        for prob, idx in zip(top3.values, top3.indices):
            i = idx.item()
            marker = " <--" if prob == top3.values[0] else "    "
            print(f"    数字 {MNIST_CLASSES[i]}: {prob.item()*100:5.1f}%{marker}")


def main():
    if len(sys.argv) < 3:
        print("用法:")
        print("  CIFAR-10: python model_training/predict.py cifar10 <图片> [图片2...]")
        print("  MNIST:    python model_training/predict.py mnist  <图片> [图片2...]")
        sys.exit(1)

    mode = sys.argv[1].lower()
    paths = sys.argv[2:]

    if mode not in ("cifar10", "mnist"):
        print(f"模式必须是 cifar10 或 mnist，不是 '{mode}'")
        sys.exit(1)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}  |  模式: {mode.upper()}")
    print("加载模型...")
    models = load_models(device)
    print("=" * 45)

    for path in paths:
        try:
            if mode == "cifar10":
                predict_cifar10(path, models, device)
            else:
                predict_mnist(path, models, device)
        except FileNotFoundError:
            print(f"\n[错误] 找不到文件: {path}")
        except Exception as e:
            print(f"\n[错误] {path}: {e}")

    print()


if __name__ == "__main__":
    main()
