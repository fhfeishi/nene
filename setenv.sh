#!/bin/zsh

# 1. 重载 zsh 配置（确保基础环境变量是最新的）
source ~/.zshrc

# 2. 安全退出可能存在的 conda 环境（如果没在 conda 环境中，这行会静默跳过）
conda deactivate 2>/dev/null

# 3. 激活当前目录下的 venv 虚拟环境
source .venv/bin/activate