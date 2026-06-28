import torch
from torch.utils.data import TensorDataset, DataLoader, random_split
from sklearn.datasets import load_wine
from sklearn.model_selection import train_test_split
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
import numpy as np

# 1) 读取真实数据集（sklearn 内置公开数据）
data = load_wine(as_frame=True)
X = data.data.values          # 特征
y = data.target.values        # 标签

# 2) 缺失值处理（即使该数据集基本无缺失，也保留通用流程）
imputer = SimpleImputer(strategy="median")
X = imputer.fit_transform(X)

# 3) 划分数据集（先 train+val / test）
X_trainval, X_test, y_trainval, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)

# 4) 标准化（只在训练集 fit，避免数据泄漏）
scaler = StandardScaler()
X_trainval = scaler.fit_transform(X_trainval)
X_test = scaler.transform(X_test)

# 5) 转 tensor
X_trainval_t = torch.tensor(X_trainval, dtype=torch.float32)
y_trainval_t = torch.tensor(y_trainval, dtype=torch.long)
X_test_t = torch.tensor(X_test, dtype=torch.float32)
y_test_t = torch.tensor(y_test, dtype=torch.long)

# 6) 构建 dataset 并再切 train/val
trainval_ds = TensorDataset(X_trainval_t, y_trainval_t)
test_ds = TensorDataset(X_test_t, y_test_t)

train_size = int(0.9 * len(trainval_ds))
val_size = len(trainval_ds) - train_size
train_ds, val_ds = random_split(trainval_ds, [train_size, val_size])

# 7) DataLoader
train_loader = DataLoader(train_ds, batch_size=64, shuffle=True)
val_loader = DataLoader(val_ds, batch_size=128, shuffle=False)
test_loader = DataLoader(test_ds, batch_size=128, shuffle=False)

xb, yb = next(iter(train_loader))
print("train batch:", xb.shape, yb.shape, xb.dtype, yb.dtype)