#!/bin/bash
# 修复conda环境冲突脚本
# 此脚本用于解决pyenv和conda在PATH上的冲突

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 日志函数
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# 显示当前环境状态
show_current_state() {
    echo ""
    echo "========================================="
    echo "当前环境状态"
    echo "========================================="
    
    echo -e "\n${BLUE}1. Python 路径:${NC}"
    which python
    
    echo -e "\n${BLUE}2. Python 版本:${NC}"
    python -V 2>&1
    
    echo -e "\n${BLUE}3. Conda 信息:${NC}"
    conda info --envs
    current_env=$(conda env list | grep '*' | awk '{print $1}')
    echo "当前激活的环境: $current_env"
    
    echo -e "\n${BLUE}4. PATH 中的 Python 相关路径:${NC}"
    echo $PATH | tr ':' '\n' | grep -E "(python|pyenv|conda|miniconda|shims)" | head -10
    
    echo -e "\n${BLUE}5. 检查 conda 前缀:${NC}"
    if [ -n "$CONDA_PREFIX" ]; then
        echo "CONDA_PREFIX: $CONDA_PREFIX"
    else
        echo "CONDA_PREFIX: 未设置"
    fi
}

# 临时修复当前环境
fix_current_env() {
    log_info "开始临时修复当前环境..."
    
    # 备份原始PATH
    export OLD_PATH="$PATH"
    log_info "已备份原始PATH到OLD_PATH变量"
    
    # 从PATH中移除所有pyenv shims相关路径
    log_info "从PATH中移除pyenv shims..."
    NEW_PATH=""
    IFS=':' read -ra path_parts <<< "$PATH"
    for part in "${path_parts[@]}"; do
        if [[ ! "$part" =~ \.pyenv/shims && ! "$part" =~ \.pyenv/bin ]]; then
            NEW_PATH="${NEW_PATH}:${part}"
        fi
    done
    NEW_PATH="${NEW_PATH:1}"  # 移除开头的冒号
    export PATH="$NEW_PATH"
    
    # 重新激活conda环境以确保正确的环境变量
    log_info "重新激活conda环境..."
    conda deactivate 2>/dev/null
    conda activate .qlibvenv
    
    # 确保conda环境路径在最前面
    if [ -n "$CONDA_PREFIX" ] && [ -d "$CONDA_PREFIX/bin" ]; then
        log_info "将conda环境路径移到PATH最前面..."
        export PATH="$CONDA_PREFIX/bin:$PATH"
    fi
    
    # 验证修复结果
    log_success "环境修复完成"
    echo "修复后Python路径: $(which python)"
    
    return 0
}

# 永久修复.zshrc配置
fix_zshrc_permanent() {
    log_info "开始永久修复.zshrc配置..."
    
    ZSHRC_FILE="$HOME/.zshrc"
    BACKUP_FILE="$ZSHRC_FILE.backup.$(date +%Y%m%d_%H%M%S)"
    
    # 备份原文件
    cp "$ZSHRC_FILE" "$BACKUP_FILE"
    log_success "已备份原.zshrc文件到: $BACKUP_FILE"
    
    # 创建临时文件
    TEMP_FILE="/tmp/.zshrc_temp_$(date +%s)"
    
    # 处理.zshrc文件
    in_conda_block=0
    pyenv_init_removed=0
    
    while IFS= read -r line; do
        # 检测conda初始化块
        if [[ "$line" =~ "# >>> conda initialize >>>" ]]; then
            in_conda_block=1
        elif [[ "$line" =~ "# <<< conda initialize <<<" ]]; then
            in_conda_block=0
        fi
        
        # 在conda块之后移除eval "$(pyenv init -)"
        if [[ "$line" =~ 'eval "$(pyenv init -)"' ]]; then
            if [[ $in_conda_block -eq 0 ]]; then
                log_warning "移除了在conda初始化块之后的: $line"
                pyenv_init_removed=1
                continue
            fi
        fi
        
        echo "$line" >> "$TEMP_FILE"
        
    done < "$ZSHRC_FILE"
    
    # 添加修复函数和别名
    cat >> "$TEMP_FILE" << 'EOF'

# =========================================
# Conda环境修复配置
# =========================================

# 禁用pyenv自动shim功能
export PYENV_VIRTUALENV_DISABLE_PROMPT=1

# 环境修复函数
function fix_conda_env() {
    # 临时移除pyenv shims
    export PATH=$(echo $PATH | tr ':' '\n' | grep -v ".pyenv/shims" | tr '\n' ':')
    
    # 重新激活当前conda环境
    if command -v conda >/dev/null; then
        conda deactivate 2>/dev/null
        if [ -n "$CONDA_DEFAULT_ENV" ]; then
            conda activate "$CONDA_DEFAULT_ENV"
        fi
    fi
    
    # 确保conda环境路径在前
    if [ -n "$CONDA_PREFIX" ] && [ -d "$CONDA_PREFIX/bin" ]; then
        export PATH="$CONDA_PREFIX/bin:$PATH"
    fi
    
    echo "环境已修复，当前Python: $(which python)"
}

# Conda环境别名
alias condafix="fix_conda_env"
alias pyenv_off="export PATH=\$(echo \$PATH | tr ':' '\\n' | grep -v \".pyenv/shims\" | tr '\\n' ':')"
alias pyenv_on="export PATH=\"\$HOME/.pyenv/shims:\$PATH\""

# 激活qlib环境并修复
alias activate_qlib="conda activate .qlibvenv && fix_conda_env"

# 验证环境的Python
alias check_python="echo \"Python路径: \$(which python)\" && echo \"Python版本: \$(python -V 2>&1)\""
EOF
    
    # 替换原文件
    mv "$TEMP_FILE" "$ZSHRC_FILE"
    
    if [[ $pyenv_init_removed -eq 1 ]]; then
        log_success "已永久修复.zshrc配置"
        log_info "修改摘要:"
        log_info "1. 移除了conda初始化块之后的 'eval \"\$(pyenv init -)\"'"
        log_info "2. 添加了环境修复函数 fix_conda_env()"
        log_info "3. 添加了多个有用的别名"
        echo ""
        log_warning "请运行以下命令使配置生效:"
        echo "  source ~/.zshrc"
    else
        log_info "未发现需要修复的配置，文件保持不变"
    fi
    
    return 0
}

# 安装PyTorch到当前环境
install_pytorch() {
    log_info "开始安装PyTorch到当前环境..."
    
    # 检查当前conda环境
    current_env=$(conda env list | grep '*' | awk '{print $1}')
    if [ "$current_env" != ".qlibvenv" ]; then
        log_warning "当前不在.qlibvenv环境中，正在切换到.qlibvenv..."
        conda activate .qlibvenv
    fi
    
    # 验证Python路径正确
    python_path=$(which python)
    if [[ ! "$python_path" =~ \.qlibvenv ]]; then
        log_warning "Python路径可能不正确: $python_path"
        read -p "是否继续安装? (y/n): " confirm
        if [[ ! $confirm =~ ^[Yy]$ ]]; then
            log_info "安装已取消"
            return 1
        fi
    fi
    
    # 安装PyTorch
    log_info "正在安装PyTorch及相关依赖..."
    echo "安装命令: conda install pytorch>=2.6.0 torchvision torchaudio numpy>=2.4.6 -c pytorch -c conda-forge"
    echo ""
    
    read -p "是否继续安装? (y/n): " confirm
    if [[ $confirm =~ ^[Yy]$ ]]; then
        conda install pytorch>=2.6.0 torchvision torchaudio numpy>=2.4.6 -c pytorch -c conda-forge
        if [ $? -eq 0 ]; then
            log_success "PyTorch安装完成"
            
            # 验证安装
            log_info "验证安装..."
            python -c "
try:
    import torch
    import numpy
    print(f'PyTorch版本: {torch.__version__}')
    print(f'NumPy版本: {numpy.__version__}')
    print(f'CUDA可用: {torch.cuda.is_available()}')
except Exception as e:
    print(f'验证失败: {e}')
"
        else
            log_error "PyTorch安装失败"
            return 1
        fi
    else
        log_info "安装已取消"
    fi
    
    return 0
}

# 主菜单
main_menu() {
    while true; do
        echo ""
        echo "========================================="
        echo "Conda环境修复工具"
        echo "========================================="
        echo "1. 显示当前环境状态"
        echo "2. 临时修复当前环境"
        echo "3. 永久修复.zshrc配置"
        echo "4. 安装PyTorch到当前环境"
        echo "5. 测试当前环境"
        echo "6. 退出"
        echo ""
        
        read -p "请选择操作 (1-6): " choice
        
        case $choice in
            1)
                show_current_state
                ;;
            2)
                fix_current_env
                show_current_state
                ;;
            3)
                fix_zshrc_permanent
                ;;
            4)
                install_pytorch
                ;;
            5)
                test_current_env
                ;;
            6)
                log_info "退出"
                exit 0
                ;;
            *)
                log_error "无效选择"
                ;;
        esac
        
        echo ""
        read -p "按Enter键继续..."
    done
}

# 测试当前环境
test_current_env() {
    echo ""
    echo "========================================="
    echo "环境测试"
    echo "========================================="
    
    echo -e "\n${BLUE}1. 基本Python测试:${NC}"
    python -c "
import sys
print('Python版本:', sys.version.split()[0])
print('Python路径:', sys.executable)
print('平台:', sys.platform)
"
    
    echo -e "\n${BLUE}2. 包导入测试:${NC}"
    python -c "
packages = ['os', 'sys', 'json', 'math', 'datetime']
for pkg in packages:
    try:
        __import__(pkg)
        print(f'{pkg}: OK')
    except ImportError as e:
        print(f'{pkg}: FAIL - {e}')
"
    
    echo -e "\n${BLUE}3. 科学计算包测试:${NC}"
    python -c "
sci_packages = ['numpy', 'pandas', 'scipy', 'torch']
for pkg in sci_packages:
    try:
        module = __import__(pkg)
        version = getattr(module, '__version__', 'unknown')
        print(f'{pkg}: OK (v{version})')
    except ImportError:
        print(f'{pkg}: Not installed')
"
    
    echo -e "\n${BLUE}4. 环境变量测试:${NC}"
    echo "CONDA_PREFIX: ${CONDA_PREFIX:-未设置}"
    echo "CONDA_DEFAULT_ENV: ${CONDA_DEFAULT_ENV:-未设置}"
    echo "VIRTUAL_ENV: ${VIRTUAL_ENV:-未设置}"
}

# 如果脚本被直接运行
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    # 检查是否在conda环境中
    if ! command -v conda &> /dev/null; then
        log_error "未找到conda命令，请确保conda已安装并正确初始化"
        exit 1
    fi
    
    main_menu
fi
