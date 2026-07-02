"""Weight file layout for ResNet18/CIFAR-10 AHE npy bundle."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ResNetBundleLayout:
    @property
    def required_files(self) -> tuple[str, ...]:
        return (
            # Stem
            "stem_weight_64_3_3_3.npy",
            "stem_bias_64.npy",
            # Layer1 block0
            "l1b0_conv1_weight_64_64_3_3.npy",
            "l1b0_conv1_bias_64.npy",
            "l1b0_conv2_weight_64_64_3_3.npy",
            "l1b0_conv2_bias_64.npy",
            # Layer1 block1
            "l1b1_conv1_weight_64_64_3_3.npy",
            "l1b1_conv1_bias_64.npy",
            "l1b1_conv2_weight_64_64_3_3.npy",
            "l1b1_conv2_bias_64.npy",
            # Layer2 block0 (downsample)
            "l2b0_conv1_weight_128_64_3_3.npy",
            "l2b0_conv1_bias_128.npy",
            "l2b0_conv2_weight_128_128_3_3.npy",
            "l2b0_conv2_bias_128.npy",
            "l2b0_ds_weight_128_64_1_1.npy",
            "l2b0_ds_bias_128.npy",
            # Layer2 block1
            "l2b1_conv1_weight_128_128_3_3.npy",
            "l2b1_conv1_bias_128.npy",
            "l2b1_conv2_weight_128_128_3_3.npy",
            "l2b1_conv2_bias_128.npy",
            # Layer3 block0 (downsample)
            "l3b0_conv1_weight_256_128_3_3.npy",
            "l3b0_conv1_bias_256.npy",
            "l3b0_conv2_weight_256_256_3_3.npy",
            "l3b0_conv2_bias_256.npy",
            "l3b0_ds_weight_256_128_1_1.npy",
            "l3b0_ds_bias_256.npy",
            # Layer3 block1
            "l3b1_conv1_weight_256_256_3_3.npy",
            "l3b1_conv1_bias_256.npy",
            "l3b1_conv2_weight_256_256_3_3.npy",
            "l3b1_conv2_bias_256.npy",
            # Layer4 block0 (downsample)
            "l4b0_conv1_weight_512_256_3_3.npy",
            "l4b0_conv1_bias_512.npy",
            "l4b0_conv2_weight_512_512_3_3.npy",
            "l4b0_conv2_bias_512.npy",
            "l4b0_ds_weight_512_256_1_1.npy",
            "l4b0_ds_bias_512.npy",
            # Layer4 block1
            "l4b1_conv1_weight_512_512_3_3.npy",
            "l4b1_conv1_bias_512.npy",
            "l4b1_conv2_weight_512_512_3_3.npy",
            "l4b1_conv2_bias_512.npy",
            # Final linear
            "linear_weight_512_10.npy",
            "linear_bias_10.npy",
        )


_RESNET_LAYOUT = ResNetBundleLayout()


def get_resnet_layout() -> ResNetBundleLayout:
    return _RESNET_LAYOUT
