"""LeNet5-CIFAR10 for 3-channel 32x32 input.

Source: https://github.com/2j2h5/lenet-alexnet-vggnet-resnet-comparison
Architecture (original LeNet-5 adapted for 3-channel CIFAR10):
  Conv(3,6,5)   -> ReLU -> AvgPool(2,2)   -> 6x14x14
  Conv(6,16,5)  -> ReLU -> AvgPool(2,2)   -> 16x5x5
  Conv(16,120,5)-> ReLU                   -> 120x1x1  (C3 kernel=spatial size)
  flatten -> 120
  FC(120->84)   -> ReLU
  FC(84->10)
"""

import torch.nn as nn
from collections import OrderedDict


class LeNet5_CIFAR10(nn.Module):
    def __init__(self, num_classes: int = 10):
        super().__init__()
        self.c1 = nn.Sequential(OrderedDict([
            ('c1',    nn.Conv2d(3, 6, kernel_size=5)),
            ('relu1', nn.ReLU()),
            ('s1',    nn.AvgPool2d(kernel_size=2, stride=2)),
        ]))
        self.c2 = nn.Sequential(OrderedDict([
            ('c2',    nn.Conv2d(6, 16, kernel_size=5)),
            ('relu2', nn.ReLU()),
            ('s2',    nn.AvgPool2d(kernel_size=2, stride=2)),
        ]))
        # C3: 5x5 kernel exactly collapses the 5x5 spatial map -> 120x1x1
        self.c3 = nn.Sequential(OrderedDict([
            ('c3',    nn.Conv2d(16, 120, kernel_size=5)),
            ('relu3', nn.ReLU()),
        ]))
        self.f4 = nn.Sequential(OrderedDict([
            ('f4',    nn.Linear(120, 84)),
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
