@echo off
chcp 65001 >nul
setlocal

echo ========================================
echo 智能客服RAG系统 - Docker 一键启动
echo ========================================
echo.

if not exist ".env" (
    echo [提示] 未找到 .env, 正在从 .env.example 复制...
    copy /y ".env.example" ".env" >nul
    echo [提示] 请编辑 .env 填写 API_KEY 后重新运行本脚本。
    pause
    exit /b 1
)

echo 检查 Docker...
docker --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Docker, 请先安装并启动 Docker Desktop。
    pause
    exit /b 1
)

docker info >nul 2>&1
if errorlevel 1 (
    echo [错误] Docker 守护进程未运行, 请先启动 Docker Desktop。
    pause
    exit /b 1
)

echo [成功] Docker 已就绪
echo.
echo 正在构建并启动容器(首次构建耗时较长, 请耐心等待)...
set "COMPOSE=docker compose"
%COMPOSE% version >nul 2>&1
if errorlevel 1 set "COMPOSE=docker-compose"

%COMPOSE% up -d --build
if errorlevel 1 (
    echo [错误] 启动失败, 请检查上方日志。
    pause
    exit /b 1
)

echo.
echo ========================================
echo 启动完成
echo ========================================
echo 前端地址:      http://localhost:3000
echo 后端API文档:   http://localhost:8000/docs
echo 健康检查:      http://localhost:8000/health
echo Qdrant控制台: http://localhost:6333/dashboard
echo.
echo 查看日志: %COMPOSE% logs -f
echo 停止服务: %COMPOSE% down
echo ========================================
pause