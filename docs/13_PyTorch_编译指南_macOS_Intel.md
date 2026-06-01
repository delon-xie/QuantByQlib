# PyTorch 2.6.0 macOS Intel 源码编译指南

## 概述

不可行，请使用 Miniconda 维护包

PyTorch 官方已于 2024 年停止为 macOS Intel (x86_64) 提供预编译 wheel，这意味着 `pip install torch` 在 Intel Mac 上只能安装 1.13.1 版本。

本文档详细介绍如何在 **macOS Intel Core i5** 机器上通过源码编译安装 PyTorch 2.6.0，以支持 NumPy 2.x 和最新的深度学习功能。

## 环境要求

### 硬件环境
- **CPU**: Intel Core i5 (推荐 6 核及以上)
- **内存**: 至少 16GB RAM (编译过程占用大量内存)
- **磁盘空间**: 至少 30GB 可用空间
- **网络**: 稳定网络（需下载大量依赖）

### 软件环境
- **macOS**: 10.14 (Mojave) 或更高版本
- **Python**: 3.9 - 3.12
- **Xcode**: 15.0 或更高版本
- **CMake**: 3.18 或更高版本
- **Git**: 最新版本

### 验证 Xcode 安装
```bash
# 检查编译器是否可用
gcc --version
clang --version
git --version

xcode-select --install  # 安装 Command Line Tools
xcodebuild -version      # 验证 Xcode 版本

#通常 xcodebuild 没有安装完整版

# 1. 通过 App Store 安装 Xcode（约 15GB）
#    或从 https://developer.apple.com/download/all/ 下载 .xip

# 2. 安装完成后，设置 Xcode 为激活的开发者目录
sudo xcode-select -s /Applications/Xcode.app/Contents/Developer

# 3. 接受许可协议
sudo xcodebuild -license accept

# 4. 安装额外组件（如果需要）
xcode-select --install

```

---

## 方案对比

| 方案 | 难度 | 支持版本 | 优点 | 缺点 |
|------|------|----------|------|------|
| **Conda 安装** | ⭐ 简单 | torch 2.x | 安装快速，官方支持 | 需要安装 conda |
| **pip (已放弃)** | - | 仅 1.13.1 | - | 版本过老 |
| **源码编译** | ⭐⭐⭐ 复杂 | 2.6.0+ | 可获得最新功能 | 编译耗时长 (1-2小时+) |

**推荐**：如果不需要 PyTorch 2.6+ 的特定功能，使用 **Conda 安装 torch 2.2.2** 是最简单稳定的选择。

---

## 方案一：Conda 安装（推荐）

### 1. 安装 Miniconda
```bash
# 使用 Homebrew 安装
brew install miniconda

# 或手动下载安装
curl -O https://repo.anaconda.com/miniconda/Miniconda3-latest-MacOSX-x86_64.sh
sh Miniconda3-latest-MacOSX-x86_64.sh
```

### 2. 创建环境并安装 PyTorch
```bash
# 创建 Python 3.10 环境
conda create -n pytorch python=3.10
conda activate pytorch

# 安装 PyTorch (CPU 版本)
conda install pytorch torchvision torchaudio -c pytorch

# 验证安装
python -c "import torch; print(torch.__version__)"
```

### 3. 安装其他依赖
```bash
pip install numpy pandas
```

---

## 方案二：源码编译 PyTorch 2.6.0

> 以下步骤基于社区成功案例，编译环境：macOS 14.7.1, Intel i5-8500B, Apple clang 16.0.0

### 预估耗时
- **首次完整编译**: 1-2 小时（取决于 CPU 性能）
- **磁盘空间**: 约 20-30 GB

### 步骤 1：安装编译依赖

```bash
# 安装 Homebrew (如果没有)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 安装基础工具
brew install cmake ninja git

# 安装 Python 依赖
pip install astunparse numpy ninja pyyaml setuptools wheel
```

### 步骤 2：克隆 PyTorch 源码

```bash
# 创建工作目录
mkdir -p ~/pytorch-build
cd ~/pytorch-build

# 克隆源码（使用递归以包含所有子模块）
git clone --recursive https://github.com/pytorch/pytorch
cd pytorch

# 切换到 2.6.0 标签
git checkout tags/v2.6.0

# 同步子模块
git submodule sync
git submodule update --init --recursive
```

> **注意**：如果网络中断导致子模块下载失败，可使用镜像：
> ```bash
> git submodule update --init --recursive --depth 1
> ```

### 步骤 3：安装 Python 依赖

```bash
# 进入 pytorch 目录
cd pytorch

# 创建虚拟环境（推荐）
pyenv shell 3.10.20
python3.10 -m venv pytorch-env
source pytorch-env/bin/activate

# 安装 PyTorch 需求
pip install -r requirements.txt

# 安装 Intel MKL（优化 CPU 性能）
pip install mkl-static mkl-include

# 安装其他依赖
pip install scikit-build
```

### 步骤 4：配置编译环境变量

```bash
# 设置 macOS 最低部署目标
export MACOS_DEPLOYMENT_TARGET=10.14

# 设置 PyTorch 版本
export TORCH_BUILD_VERSION=2.6.0

# 禁用不需要的特性（加速编译）
export USE_MPS=0          # Intel 不支持 MPS
export USE_CUDA=0        # Intel 没有 CUDA
export USE_CUDNN=0
export USE_DISTRIBUTED=0  # 禁用分布式训练
export BUILD_TEST=0       # 不编译测试
export BUILD_CAFFE2=0

# 启用 MKLDNN（Intel CPU 优化）
export USE_MKLDNN=1

# 编译标志
export DEBUG=0
export MAX_JOBS=4         # 并行编译任务数（建议 CPU 核心数）

# 可选：使用 ICC 优化（如果有 Intel Compiler）
# export CC=icc
# export CXX=icpc
```

### 步骤 5：开始编译

并行加速安装

``` bash
# 安装 OpenMP 运行时库
brew install libomp

# 修改源代码

    # Intel Mac OpenMP fix
if(APPLE)
    set(OpenMP_C_FOUND TRUE)
    set(OpenMP_CXX_FOUND TRUE)
    set(OpenMP_C_FLAGS "-Xpreprocessor -fopenmp -I/usr/local/opt/libomp/include")
    set(OpenMP_CXX_FLAGS "-Xpreprocessor -fopenmp -I/usr/local/opt/libomp/include")
    set(OpenMP_C_LIB_NAMES "omp")
    set(OpenMP_CXX_LIB_NAMES "omp")
    set(OpenMP_omp_LIBRARY "/usr/local/opt/libomp/lib/libomp.dylib")
endif()

    find_package(OpenMP) # 在这句话前添加上面的特殊限制

# 设置必要的环境变量（让 cmake 能找到）
export LDFLAGS="-L/opt/homebrew/opt/libomp/lib"
export CPPFLAGS="-I/opt/homebrew/opt/libomp/include"
export OpenMP_C_FLAGS="-Xpreprocessor -fopenmp -I/opt/homebrew/opt/libomp/include"
export OpenMP_CXX_FLAGS="-Xpreprocessor -fopenmp -I/opt/homebrew/opt/libomp/include"
export OpenMP_C_LIB_NAMES="omp"
export OpenMP_CXX_LIB_NAMES="omp"
export OpenMP_omp_LIBRARY="/opt/homebrew/opt/libomp/lib/libomp.dylib"

# 确认安装是否成功
brew list libomp 2>/dev/null || brew install libomp

OMP_PREFIX=$(brew --prefix libomp)

# 彻底清理
python setup.py clean
rm -rf build

# 使用 CMAKE_ARGS 传递所有 OpenMP 参数，通过 CMake 参数传递所有 flags
CMAKE_ARGS="-DOpenMP_C_FLAGS='-Xpreprocessor -fopenmp -I/usr/local/opt/libomp/include' \
             -DOpenMP_CXX_FLAGS='-Xpreprocessor -fopenmp -I/usr/local/opt/libomp/include' \
             -DOpenMP_C_LIB_NAMES='omp' \
             -DOpenMP_CXX_LIB_NAMES='omp' \
             -DOpenMP_omp_LIBRARY='/usr/local/opt/libomp/lib/libomp.dylib' \
             -DCMAKE_CXX_FLAGS='-Wno-nontrivial-memcall' \
             -DCMAKE_C_FLAGS='-Wno-nontrivial-memcall'" \
CMAKE_POLICY_VERSION_MINIMUM=3.5 \
USE_XPU=OFF \
python setup.py develop
```
编译 wheel
``` bash
# 进入 PyTorch 源码目录
cd pytorch

# 运行编译
python setup.py bdist_wheel

# 设置特定版本的CMAKE
CMAKE_POLICY_VERSION_MINIMUM=3.5 python setup.py develop
```

**编译输出位置**: `pytorch/dist/*.whl`

### 步骤 6：安装编译产物

```bash
# 安装 wheel 包
pip install dist/torch-*.whl

# 安装 torchvision (可选)
pip install torchvision

# 验证安装
python -c "import torch; print(f'PyTorch version: {torch.__version__}')"
python -c "import torch; print(f'NumPy required: {torch._numpy_requirements}')"
```

---

## 常见问题与解决方案

### Q1: 编译过程中内存不足 (OOM)

**错误**: `killed: 9` 或 `memory error`

**解决方案**:
```bash
# 减少并行编译任务数
export MAX_JOBS=2

# 或者关闭某些优化
export DEBUG=1
```

### Q2: 子模块下载失败

**解决方案**:
```bash
# 重试子模块更新
git submodule update --init --recursive

# 使用镜像加速（针对国内网络）
export https_proxy=http://127.0.0.1:7890
export http_proxy=http://127.0.0.1:7890
```

### Q3: CMake 找不到 Python

**解决方案**:
```bash
# 设置 Python 路径
which python
export PATH=/path/to/your/python/bin:$PATH
export CMAKE_PREFIX_PATH=/path/to/your/python
```

### Q4: 编译后测试失败 (AVX2/AVX512)

**说明**: 这是正常的精度差异，不影响正常使用。

**验证方法**:
```bash
python -c "
import torch
x = torch.randn(100, 100)
y = torch.randn(100, 100)
z = torch.mm(x, y)
print('Basic operations work correctly')
"
```

### Q5: NumPy 版本冲突

**问题**: PyTorch 2.6.0 需要 NumPy 2.x，但某些库不兼容

**解决方案**:
```bash
# 升级 NumPy
pip install 'numpy>=2.0.0'

# 验证兼容性
python -c "import torch; import numpy as np; print(f'Torch: {torch.__version__}, NumPy: {np.__version__}')"
```

---

## 与 NumPy 2.x 的兼容性

### PyTorch 版本与 NumPy 兼容性表

| PyTorch 版本 | NumPy 1.x | NumPy 2.x |
|-------------|-----------|-----------|
| 1.11 - 1.13 | ✅ 支持 | ❌ 不支持 |
| 2.0 - 2.5 | ✅ 支持 | ❌ 不支持 |
| 2.6.0+ | ✅ 支持 | ✅ 支持 |

### 配置 requirements.txt

如果使用 PyTorch 2.6.0+ 和 NumPy 2.x：

```txt
# 深度学习
torch>=2.6.0
numpy>=2.0.0
pandas-ta-classic>=0.6.20
```

---

## 验证安装

### 基础验证
```python
import torch
import numpy as np

print(f"PyTorch 版本: {torch.__version__}")
print(f"NumPy 版本: {np.__version__}")
print(f"CPU 支持: {torch.backends.cpu.cpu_capability()}")
```

### 完整功能测试
```python
import torch

# 张量操作
x = torch.randn(3, 3)
y = torch.randn(3, 3)
z = torch.mm(x, y)
print(f"矩阵乘法成功: {z.shape}")

# GPU/MPS 检测 (Apple Silicon)
if torch.backends.mps.is_available():
    print("MPS 可用")
else:
    print("MPS 不可用 (正常，Intel Mac)")

# CUDA 检测
print(f"CUDA 可用: {torch.cuda.is_available()}")
```

---

## 卸载与清理

### 卸载 PyTorch
```bash
pip uninstall torch torchvision torchaudio
```

### 清理编译缓存
```bash
cd ~/pytorch-build/pytorch
rm -rf build/
rm -rf dist/
rm -rf *.egg-info
```

### 清理磁盘空间
```bash
# 删除源码目录
rm -rf ~/pytorch-build

# 删除虚拟环境
rm -rf pytorch-env
```

---

## 参考链接

- [PyTorch 官方 GitHub](https://github.com/pytorch/pytorch)
- [PyTorch macOS 编译讨论](https://discuss.pytorch.org/t/building-pytorch-2-6-0-from-source-on-macos-x86-64-intel/216283)
- [PyTorch 官方安装指南](https://pytorch.org/get-started/locally/)
- [PyTorch 从源码编译文档](https://github.com/pytorch/pytorch#from-source)

---

## 更新日志

| 日期 | 版本 | 更新内容 |
|------|------|----------|
| 2026-05-31 | v1.0 | 初始文档创建 |

