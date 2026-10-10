#!/bin/bash
set -e

echo "========================================"
echo "智能客服RAG系统 - Docker 一键启动"
echo "========================================"
echo ""

if [ ! -f ".env" ]; then
  echo "[提示] 未找到 .env, 正在从 .env.example 复制..."
  cp .env.example .env
  echo "[提示] 请编辑 .env 填写 API_KEY 后重新运行本脚本。"
  exit 1
fi

echo "检查 Docker..."
if ! command -v docker >/dev/null 2>&1; then
  echo "[错误] 未检测到 Docker, 请先安装 Docker。"
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "[错误] Docker 守护进程未运行, 请先启动 Docker。"
  exit 1
fi

echo "[成功] Docker 已就绪"
echo ""

if docker compose version >/dev/null 2>&1; then
  COMPOSE="docker compose"
else
  COMPOSE="docker-compose"
fi

echo "正在构建并启动容器(首次构建耗时较长, 请耐心等待)..."
$COMPOSE up -d --build

echo ""
echo "========================================"
echo "启动完成"
echo "========================================"
echo "前端地址:      http://localhost:3000"
echo "后端API文档:   http://localhost:8000/docs"
echo "健康检查:      http://localhost:8000/health"
echo "Qdrant控制台: http://localhost:6333/dashboard"
echo ""
echo "查看日志: $COMPOSE logs -f"
echo "停止服务: $COMPOSE down"
echo "========================================"