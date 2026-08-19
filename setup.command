#!/bin/bash
# 腾讯云 Token Plan 一键接入
# 双击即可运行

cd "$(dirname "$0")"

if ! command -v python3 &> /dev/null; then
    echo "正在安装 Python 3..."
    xcode-select --install 2>/dev/null
    echo "安装完成后再次双击此文件"
    read -p "按回车退出..."
    exit 1
fi

python3 setup.py
read -p "按回车退出..."