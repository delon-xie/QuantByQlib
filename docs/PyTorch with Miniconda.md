# 安装 Miniconda

``` bash
# 安装 Miniconda
brew install --cask miniconda
conda init zsh   # 或 bash
source ~/.zshrc

# 同意条款
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r

# 2. 退出并删除旧环境 3.10
conda deactivate
conda env remove -n .venv

# 新建 conda 环境（Python 3.11 与你 venv 一致） 3.11.13
conda create -n .venv python=3.11 -y
conda activate .venv

python -V      
# Python 3.11.13

# 2. 先装 PyTorch（conda 渠道，Intel Mac 唯一途径）
conda install "pytorch>=2.6.0" "torchvision" "torchaudio" "numpy>=2.4.6" -c pytorch -c conda-forge

# ② 再装其余依赖（pip）
pip install -r requirements_base.txt   # 不含 torch/numpy
```