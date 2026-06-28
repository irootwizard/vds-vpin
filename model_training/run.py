import argparse
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Unified launcher for model_training backends")
    parser.add_argument(
        "--task",
        type=str,
        default="",
        choices=["", "network-a", "network-b", "network-lenet", "network-resnet"],
    )
    parser.add_argument("--backend", type=str, default="pytorch", choices=["pytorch", "numpy"])
    parser.add_argument("--dataset", type=str, default="mnist")
    parser.add_argument("--data-dir", type=str, default="./data")
    parser.add_argument("--data-path", type=str, default="")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--num-workers", type=int, default=0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", type=str, default="cuda")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.task == "network-a":
        repo = Path(__file__).resolve().parent
        sys.path.insert(0, str(repo.parent.parent))
        from model_training.network_a.train import train_network_a

        train_network_a(device=args.device, batch_size=args.batch_size, lr=args.lr)
        return

    if args.task == "network-b":
        repo = Path(__file__).resolve().parent
        sys.path.insert(0, str(repo.parent.parent))
        from model_training.network_b.train import train_network_b

        train_network_b(device=args.device, batch_size=args.batch_size, lr=args.lr)
        return

    if args.task == "network-lenet":
        if args.dataset not in ("cifar10", ""):
            print(f"Error: network-lenet requires --dataset cifar10, got {args.dataset!r}", flush=True)
            sys.exit(1)
        repo = Path(__file__).resolve().parent
        sys.path.insert(0, str(repo.parent))
        from model_training.network_lenet.train import train_network_lenet

        train_network_lenet(device=args.device, batch_size=args.batch_size, lr=args.lr)
        return

    if args.task == "network-resnet":
        if args.dataset not in ("cifar10", ""):
            print(f"Error: network-resnet requires --dataset cifar10, got {args.dataset!r}", flush=True)
            sys.exit(1)
        repo = Path(__file__).resolve().parent
        sys.path.insert(0, str(repo.parent))
        from model_training.network_resnet.train import train_resnet18_cifar

        train_resnet18_cifar(
            device=args.device,
            batch_size=256 if args.batch_size == 64 else args.batch_size,
            lr=0.1,
            epochs=120 if args.epochs == 3 else args.epochs,
            amp=None,
        )
        return

    if args.backend == "pytorch":
        from train_pytorch import PTConfig, train

        cfg = PTConfig(
            dataset=args.dataset,
            data_dir=args.data_dir,
            epochs=args.epochs,
            batch_size=args.batch_size,
            lr=args.lr,
            num_workers=args.num_workers,
        )
        train(cfg)
        return

    from train_numpy import NPConfig, train

    cfg = NPConfig(
        dataset=args.dataset,
        data_path=args.data_path,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        seed=args.seed,
    )
    train(cfg)


if __name__ == "__main__":
    main()
