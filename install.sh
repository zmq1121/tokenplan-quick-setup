#!/bin/bash
# 腾讯云 Token Plan 一键接入
# 用法: curl -fsSL https://raw.githubusercontent.com/zmq1121/tokenplan-quick-setup/main/install.sh | bash

set -e

echo ""
echo "  ╔══════════════════════════════════════════════╗"
echo "  ║   腾讯云 Token Plan — 一键接入              ║"
echo "  ╚══════════════════════════════════════════════╝"
echo ""

# 下载 setup.py
curl -fsSL -o /tmp/tokenplan-setup.py https://raw.githubusercontent.com/zmq1121/tokenplan-quick-setup/main/setup.py

# 运行
python3 /tmp/tokenplan-setup.py

# 清理
rm /tmp/tokenplan-setup.py