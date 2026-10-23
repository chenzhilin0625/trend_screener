#!/bin/bash
# 趋势筛选器 Mac 启动脚本
cd "$(dirname "$0")"

echo
echo "  ============================"
echo "    趋势筛选器 Web UI"
echo "  ============================"
echo

# 首次运行检查
if [ ! -f "trend_data.db" ]; then
    echo "  首次运行，需要下载全量数据 (~40分钟)"
    echo "  运行: python batch_download.py"
    echo
    read -p "  是否现在下载? (y/n): " ans
    if [ "$ans" = "y" ]; then
        python batch_download.py
    else
        echo "  跳过数据下载。部分功能可能不可用。"
    fi
    echo
fi

open http://localhost:5050 2>/dev/null || echo "  请手动打开浏览器: http://localhost:5050"
python server.py
