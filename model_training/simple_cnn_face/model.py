"""SimpleCNN for face recognition — lightweight architecture for AHE feasibility."""

import torch.nn as nn


class SimpleCNN(nn.Module):
    """3 conv + 2 FC, designed for 64x64 RGB input.

    Architecture:
        Conv2d(3, 16, 3, pad=1) -> BN -> ReLU -> MaxPool2d(2)  # 64 -> 32
        Conv2d(16, 32, 3, pad=1) -> BN -> ReLU -> MaxPool2d(2) # 32 -> 16
        Conv2d(32, 64, 3, pad=1) -> BN -> ReLU -> MaxPool2d(2) # 16 -> 8
        Flatten -> FC(64*8*8, 128) -> ReLU -> Dropout(0.3)
        FC(128, num_classes)

    Parameters: ~530K for 50 classes.
    AHE truncation phases: 5 (3 conv outputs + 2 FC outputs).
    """

    def __init__(self, num_classes: int = 50, dropout: float = 0.3):
        super().__init__()
        self.conv1 = nn.Conv2d(3, 16, 3, padding=1, bias=False)
        self.bn1 = nn.BatchNorm2d(16)
        self.conv2 = nn.Conv2d(16, 32, 3, padding=1, bias=False)
        self.bn2 = nn.BatchNorm2d(32)
        self.conv3 = nn.Conv2d(32, 64, 3, padding=1, bias=False)
        self.bn3 = nn.BatchNorm2d(64)
        self.pool = nn.MaxPool2d(2)

        self.fc1 = nn.Linear(64 * 8 * 8, 128)
        self.dropout = nn.Dropout(dropout)
        self.fc2 = nn.Linear(128, num_classes)
        self.relu = nn.ReLU(inplace=True)

    def forward(self, x):
        x = self.pool(self.relu(self.bn1(self.conv1(x))))  # 64 -> 32
        x = self.pool(self.relu(self.bn2(self.conv2(x))))  # 32 -> 16
        x = self.pool(self.relu(self.bn3(self.conv3(x))))  # 16 -> 8
        x = x.view(x.size(0), -1)
        x = self.relu(self.fc1(x))
        x = self.dropout(x)
        x = self.fc2(x)
        return x
