#!/bin/bash
# =============================================
#  趋势筛选器 Mac 一键安装
#  用法: bash setup_mac.sh
# =============================================
set -e

echo "============================================"
echo "  趋势筛选器 Mac 安装"
echo "============================================"
echo

# 检查 Python
if ! command -v python3 &>/dev/null; then
    echo "[X] 需要 Python 3.9+，请先安装: brew install python"
    exit 1
fi
echo "[OK] Python: $(python3 --version)"

# 安装依赖
echo
echo ">> 安装 Python 依赖..."
pip3 install pandas numpy flask baostock akshare

# 下载数据（可选，但推荐）
echo
read -p ">> 是否现在下载全量A股历史数据?(约40分钟) (y/n): " ans
if [ "$ans" = "y" ]; then
    python3 batch_download.py
else
    echo "   跳过。之后可手动运行: python3 batch_download.py"
fi

echo
echo "============================================"
echo "  安装完成！"
echo
echo "  启动 Web UI:  ./启动.sh"
echo "  CLI 分析:     python3 analyzer.py 600519"
echo "  CLI 批量:     python3 analyzer.py --batch 600519 000858"
echo "============================================"
