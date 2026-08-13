import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class NPConfig:
    dataset: str = "synthetic"
    data_path: str = ""
    epochs: int = 3
    batch_size: int = 32
    lr: float = 1e-2
    seed: int = 42


def relu(x: np.ndarray) -> np.ndarray:
    return np.maximum(0, x)


def relu_grad(x: np.ndarray) -> np.ndarray:
    return (x > 0).astype(np.float32)


def softmax(logits: np.ndarray) -> np.ndarray:
    z = logits - logits.max(axis=1, keepdims=True)
    exp = np.exp(z)
    return exp / exp.sum(axis=1, keepdims=True)


class TinyNumpyCNN:
    def __init__(self, in_channels: int = 1, image_size: int = 28, num_classes: int = 10, seed: int = 42) -> None:
        rng = np.random.default_rng(seed)
        self.num_classes = num_classes
        self.image_size = image_size
        self.in_channels = in_channels
        self.conv_out = 8
        self.kernel = 3

        self.Wc = rng.normal(0, 0.1, (self.conv_out, in_channels, self.kernel, self.kernel)).astype(np.float32)
        self.bc = np.zeros((self.conv_out,), dtype=np.float32)

        conv_size = image_size - self.kernel + 1
        pooled_size = conv_size // 2
        self.flat_dim = self.conv_out * pooled_size * pooled_size
        self.Wf = rng.normal(0, 0.1, (self.flat_dim, num_classes)).astype(np.float32)
        self.bf = np.zeros((num_classes,), dtype=np.float32)

    def conv2d_valid(self, x: np.ndarray, w: np.ndarray, b: np.ndarray) -> np.ndarray:
        n, c, h, w_in = x.shape
        out_c, _, kh, kw = w.shape
        out_h, out_w = h - kh + 1, w_in - kw + 1
        out = np.zeros((n, out_c, out_h, out_w), dtype=np.float32)
        for i in range(out_h):
            for j in range(out_w):
                patch = x[:, :, i : i + kh, j : j + kw]
                out[:, :, i, j] = np.tensordot(patch, w, axes=([1, 2, 3], [1, 2, 3])) + b
        return out

    def maxpool2x2(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        n, c, h, w = x.shape
        out_h, out_w = h // 2, w // 2
        out = np.zeros((n, c, out_h, out_w), dtype=np.float32)
        mask = np.zeros_like(x, dtype=np.float32)
        for i in range(out_h):
            for j in range(out_w):
                patch = x[:, :, 2 * i : 2 * i + 2, 2 * j : 2 * j + 2]
                max_vals = patch.max(axis=(2, 3))
                out[:, :, i, j] = max_vals
                for pi in range(2):
                    for pj in range(2):
                        is_max = patch[:, :, pi, pj] == max_vals
                        mask[:, :, 2 * i + pi, 2 * j + pj] = np.where(is_max, 1.0, mask[:, :, 2 * i + pi, 2 * j + pj])
        return out, mask

    def maxpool_backward(self, grad_out: np.ndarray, mask: np.ndarray) -> np.ndarray:
        n, c, out_h, out_w = grad_out.shape
        grad = np.zeros_like(mask, dtype=np.float32)
        for i in range(out_h):
            for j in range(out_w):
                grad[:, :, 2 * i : 2 * i + 2, 2 * j : 2 * j + 2] += (
                    grad_out[:, :, i, j][:, :, None, None] * mask[:, :, 2 * i : 2 * i + 2, 2 * j : 2 * j + 2]
                )
        return grad

    def forward(self, x: np.ndarray) -> dict[str, np.ndarray]:
        z_conv = self.conv2d_valid(x, self.Wc, self.bc)
        a_conv = relu(z_conv)
        p, pool_mask = self.maxpool2x2(a_conv)
        flat = p.reshape(p.shape[0], -1)
        logits = flat @ self.Wf + self.bf
        probs = softmax(logits)
        return {
            "x": x,
            "z_conv": z_conv,
            "a_conv": a_conv,
            "pool": p,
            "pool_mask": pool_mask,
            "flat": flat,
            "logits": logits,
            "probs": probs,
        }

    def backward(self, cache: dict[str, np.ndarray], y: np.ndarray) -> dict[str, np.ndarray]:
        n = y.shape[0]
        probs = cache["probs"].copy()
        probs[np.arange(n), y] -= 1
        probs /= n

        dWf = cache["flat"].T @ probs
        dbf = probs.sum(axis=0)
        dflat = probs @ self.Wf.T
        dpool = dflat.reshape(cache["pool"].shape)
        da_conv = self.maxpool_backward(dpool, cache["pool_mask"])
        dz_conv = da_conv * relu_grad(cache["z_conv"])

        x = cache["x"]
        n, c, h, w = x.shape
        out_c, _, kh, kw = self.Wc.shape
        out_h, out_w = dz_conv.shape[2], dz_conv.shape[3]
        dWc = np.zeros_like(self.Wc)
        dbc = dz_conv.sum(axis=(0, 2, 3))

        for oc in range(out_c):
            for ic in range(c):
                for i in range(kh):
                    for j in range(kw):
                        patch = x[:, ic, i : i + out_h, j : j + out_w]
                        dWc[oc, ic, i, j] = np.sum(patch * dz_conv[:, oc, :, :])

        return {"dWf": dWf, "dbf": dbf, "dWc": dWc, "dbc": dbc}

    def step(self, grads: dict[str, np.ndarray], lr: float) -> None:
        self.Wf -= lr * grads["dWf"]
        self.bf -= lr * grads["dbf"]
        self.Wc -= lr * grads["dWc"]
        self.bc -= lr * grads["dbc"]

    def predict(self, x: np.ndarray) -> np.ndarray:
        probs = self.forward(x)["probs"]
        return probs.argmax(axis=1)


def one_hot_ce_loss(probs: np.ndarray, y: np.ndarray) -> float:
    eps = 1e-9
    return float(-np.log(probs[np.arange(y.shape[0]), y] + eps).mean())


def load_data(cfg: NPConfig) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    if cfg.dataset == "synthetic":
        rng = np.random.default_rng(cfg.seed)
        x_train = rng.random((512, 1, 28, 28), dtype=np.float32)
        y_train = rng.integers(0, 10, size=(512,), endpoint=False)
        x_test = rng.random((128, 1, 28, 28), dtype=np.float32)
        y_test = rng.integers(0, 10, size=(128,), endpoint=False)
        return x_train, y_train, x_test, y_test

    if cfg.dataset == "npz":
        if not cfg.data_path:
            raise ValueError("When dataset=npz, --data-path is required.")
        path = Path(cfg.data_path)
        data = np.load(path)
        x_train = data["x_train"].astype(np.float32)
        y_train = data["y_train"].astype(np.int64)
        x_test = data["x_test"].astype(np.float32)
        y_test = data["y_test"].astype(np.int64)
        return x_train, y_train, x_test, y_test

    raise ValueError("Unsupported dataset for numpy backend. Use synthetic or npz.")


def train(cfg: NPConfig) -> None:
    np.random.seed(cfg.seed)
    x_train, y_train, x_test, y_test = load_data(cfg)
    model = TinyNumpyCNN(in_channels=x_train.shape[1], image_size=x_train.shape[2], num_classes=10, seed=cfg.seed)

    n_train = x_train.shape[0]
    for epoch in range(cfg.epochs):
        perm = np.random.permutation(n_train)
        x_train, y_train = x_train[perm], y_train[perm]
        epoch_loss = 0.0
        steps = 0
        for start in range(0, n_train, cfg.batch_size):
            end = start + cfg.batch_size
            xb = x_train[start:end]
            yb = y_train[start:end]
            cache = model.forward(xb)
            loss = one_hot_ce_loss(cache["probs"], yb)
            grads = model.backward(cache, yb)
            model.step(grads, cfg.lr)
            epoch_loss += loss
            steps += 1

        pred = model.predict(x_test)
        acc = float((pred == y_test).mean())
        print(f"[NumPy] Epoch {epoch + 1}/{cfg.epochs} - loss: {epoch_loss / max(steps, 1):.4f}, test_acc: {acc:.4f}")


def parse_args() -> NPConfig:
    parser = argparse.ArgumentParser(description="Tiny CNN training without PyTorch (NumPy only)")
    parser.add_argument("--dataset", type=str, default="synthetic", choices=["synthetic", "npz"])
    parser.add_argument("--data-path", type=str, default="")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=1e-2)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    return NPConfig(
        dataset=args.dataset,
        data_path=args.data_path,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        seed=args.seed,
    )


if __name__ == "__main__":
    train(parse_args())
