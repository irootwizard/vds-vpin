import torch
import torch.nn as nn
import torch.optim as optim


def make_data(n: int = 2000, d: int = 20, seed: int = 42) -> tuple[torch.Tensor, torch.Tensor]:
    # 使用固定随机种子，保证每次运行结果可复现。
    g = torch.Generator().manual_seed(seed)
    x = torch.randn(n, d, generator=g)
    # 真实权重 true_w 用于合成“有规律”的二分类数据。
    true_w = torch.randn(d, 1, generator=g)
    logits = x @ true_w + 0.2 * torch.randn(n, 1, generator=g)
    # (logits > 0) 得到 bool，再转成 float 作为 0/1 标签。
    y = (logits > 0).float()
    return x, y


def main() -> None:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"device={device}")

    x, y = make_data()
    # to(device) 把数据拷贝到和模型一致的设备（CPU/GPU）。
    x, y = x.to(device), y.to(device)

    # 线性层：输入 20 维，输出 1 维（二分类 logit）。
    model = nn.Linear(20, 1).to(device)
    # BCEWithLogitsLoss = sigmoid + 二元交叉熵，数值更稳定。
    criterion = nn.BCEWithLogitsLoss()
    # model.parameters() 返回可训练参数给优化器更新。
    optimizer = optim.Adam(model.parameters(), lr=1e-2)

    epochs = 20
    for epoch in range(epochs):
        # 清空上一步梯度；PyTorch 会默认累加梯度。
        optimizer.zero_grad()
        # 前向传播：得到预测 logits。
        logits = model(x)
        # 计算损失。
        loss = criterion(logits, y)
        # 反向传播：自动计算每个参数的梯度。
        loss.backward()
        # 参数更新：w = w - lr * grad（由优化器实现细节）。
        optimizer.step()

        # no_grad() 下不记录梯度，适合评估阶段，省显存更快。
        with torch.no_grad():
            pred = (torch.sigmoid(logits) > 0.5).float()
            acc = (pred == y).float().mean().item()

        print(f"epoch={epoch + 1:02d} loss={loss.item():.4f} acc={acc:.4f}")

    # TODO:
    # 1) 将 Adam 改成 SGD，比较收敛速度
    # 2) 改学习率为 1e-3 / 1e-1，观察 loss 曲线变化


if __name__ == "__main__":
    main()
