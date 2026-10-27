@echo off
chcp 65001 >nul
cd /d "%~dp0"

python -c "import sys;sys.exit(0 if sys.version_info>=(3,10) else 1)" >nul 2>&1
if errorlevel 1 (
    echo [错误] 需要 Python 3.10 或以上版本，当前 python 可执行文件版本不满足。
    python --version
    echo.
    echo 请安装 Python 3.11+ 并在安装时勾选 "Add python.exe to PATH"：
    echo https://www.python.org/downloads/
    pause
    exit /b 1
)

if not exist .venv (
    echo [1/3] 首次运行，正在创建虚拟环境...
    python -m venv .venv
    .venv\Scripts\python -m pip install -U pip
    echo [2/3] 正在安装依赖，大约需要 2-3 分钟...
    .venv\Scripts\pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --timeout 60
)

if not exist .env (
    echo [提示] 未找到 .env，已从 .env.example 复制一份。
    copy .env.example .env >nul
    echo 请在弹出的记事本里把 DASHSCOPE_API_KEY 换成你自己的 Key，保存并关闭。
    notepad .env
)

echo [3/3] 启动中，浏览器会自动打开 http://localhost:8501
.venv\Scripts\python -m streamlit run app.py
pause
