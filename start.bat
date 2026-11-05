@echo off
chcp 65001 >nul
title SillyTavern All-in-One Launcher

echo =======================================================
echo    EODHCTSiqsxajs-Wikipedia+ReAct结构分析框架
echo =======================================================
echo.

echo 🚀 [1/2] 正在启动 Python ReAct 代理服务器...
:: 这里的 "你的代理文件夹" 请替换为你实际存放 react_proxy.py 的子文件夹名称
start "ReAct Proxy" cmd /k "cd /d %~dp0EODHCTSiqsxajs-react-wiki1.5\react-proxy && python react_proxy.py"

timeout /t 2 /nobreak >nul

echo 🍺 [2/2] 正在启动 SillyTavern...
:: 直接调用同级目录下的官方启动脚本
call Start.bat