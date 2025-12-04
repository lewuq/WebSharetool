#!/bin/bash
# 进入脚本所在目录
cd "$(dirname "$0")"

echo "=========================================="
echo "      WebShareTool 环境自检与启动"
echo "=========================================="

# 定义打开网页函数
open_url() {
    open "$1"
}

# 1. 检测 Python3
if ! command -v python3 &> /dev/null; then
    echo "❌ [错误] 未检测到 Python3。"
    echo "正在为您打开 Python 官网..."
    open_url "https://www.python.org/downloads/macos/"
    read -p "安装完成后，请按回车键重新运行..."
    exit 1
fi

# 2. 检测并安装 Flask (关键修改部分)
python3 -c "import flask" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "[提示] 未检测到 Flask 库。"
    echo "正在自动安装 Flask..."
    
    # 【核心修改】使用 python3 -m pip 代替 pip3
    # 这样能确保库安装到当前 python3 能读取的目录中
    python3 -m pip install flask -i https://pypi.tuna.tsinghua.edu.cn/simple
    
    if [ $? -ne 0 ]; then
        echo "[错误] Flask 安装失败！"
        read -p "按回车键退出..."
        exit 1
    fi
    echo "Flask 安装成功！"
else
    echo " 环境正常：Python3 和 Flask 已安装。"
fi

# 3. 配置 cloudflared 权限
if [ -f "cloudflared" ]; then
    chmod +x cloudflared
fi

# 4. 启动工具
echo "------------------------------------------"
echo "正在启动 WebShareTool..."

# 再次确认 Flask 是否可被加载
python3 -c "import flask" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "[严重错误] Flask 安装了但无法加载。"
    echo "尝试方案：请手动运行 'pip3 install flask' 后重试。"
    read -p "按回车键退出..."
    exit 1
fi

python3 WebShareTool.py

echo "------------------------------------------"
echo "程序已退出。"