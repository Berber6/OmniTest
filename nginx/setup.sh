#!/bin/bash
# OmniTest Nginx 安装与配置脚本
# 需要 sudo 权限运行

set -e

echo "=== 安装 Nginx ==="
sudo apt-get update -qq
sudo apt-get install -y -qq nginx

echo "=== 配置 OmniTest 反向代理 ==="
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# 复制配置文件
sudo cp "$SCRIPT_DIR/omnitest.conf" /etc/nginx/sites-available/omnitest

# 启用站点（禁用 default 可选）
sudo ln -sf /etc/nginx/sites-available/omnitest /etc/nginx/sites-enabled/

# 更新截图路径（确保与实际项目路径一致）
ACTUAL_SCREENSHOT_PATH="$PROJECT_DIR/backend/data/screenshots"
sudo sed -i "s|/data1/workspace/zhibin/omni_test/backend/data/screenshots/|$ACTUAL_SCREENSHOT_PATH/|g" /etc/nginx/sites-available/omnitest

echo "=== 测试 Nginx 配置 ==="
sudo nginx -t

echo "=== 重载 Nginx ==="
sudo systemctl reload nginx

echo ""
echo "=== 完成！ ==="
echo "Nginx 已在 8080 端口监听，访问 http://localhost:8080 即可使用 OmniTest"
echo ""
echo "启动服务："
echo "  后端: cd $PROJECT_DIR/backend && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
echo "  前端: cd $PROJECT_DIR/frontend && npm run dev"
echo ""
echo "停止 Nginx: sudo systemctl stop nginx"
echo "重载配置:   sudo systemctl reload nginx"