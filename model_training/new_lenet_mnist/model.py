"""LeNet5 for MNIST — 1-channel 32x32 input, 10 digit classes."""

from collections import OrderedDict
import torch.nn as nn


class LeNet5_MNIST(nn.Module):
    def __init__(self, num_classes=10):
        super().__init__()
        self.c1 = nn.Sequential(OrderedDict([
            ('c1', nn.Conv2d(1, 6, kernel_size=5)),
            ('relu1', nn.ReLU()),
            ('s1', nn.AvgPool2d(kernel_size=2, stride=2)),
        ]))
        self.c2 = nn.Sequential(OrderedDict([
            ('c2', nn.Conv2d(6, 16, kernel_size=5)),
            ('relu2', nn.ReLU()),
            ('s2', nn.AvgPool2d(kernel_size=2, stride=2)),
        ]))
        self.c3 = nn.Sequential(OrderedDict([
            ('c3', nn.Conv2d(16, 120, kernel_size=5)),
            ('relu3', nn.ReLU()),
        ]))
        self.f4 = nn.Sequential(OrderedDict([
            ('f4', nn.Linear(120, 84)),
            ('relu4', nn.ReLU()),
        ]))
        self.f5 = nn.Linear(84, num_classes)

    def forward(self, x):
        x = self.c1(x)
        x = self.c2(x)
        x = self.c3(x)
        x = x.view(x.size(0), -1)
        x = self.f4(x)
        return self.f5(x)
