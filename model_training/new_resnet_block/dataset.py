"""CIFAR-10 dataloaders for new_resnet_block — identical to new_resnet."""

from model_training.new_resnet.dataset import (  # noqa: F401  re-export
    build_cifar10_loaders,
    cifar10_root,
    CIFAR10_MEAN,
    CIFAR10_STD,
)
