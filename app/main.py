#!/usr/bin/env python3
"""
主入口文件 - 启动Web服务和后台任务
"""

import os
import sys
import signal
import logging
from flask import Flask
from flask_cors import CORS
from flask_socketio import SocketIO

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import Config
from app.core.logger import setup_logger
from app.core.scheduler import TaskScheduler
from app.core.clash_manager import LocalClashManager
from app.api.routes import api_bp
from app.api.websocket import setup_websocket

# 全局变量
app = None
socketio = None
scheduler = None
clash_manager = None
logger = None


def create_app():
    """创建Flask应用"""
    flask_app = Flask(__name__,
                      template_folder='web/templates',
                      static_folder='web/static')

    # 加载配置
    config = Config()
    flask_app.config['SECRET_KEY'] = config.get('http_server.access_key', 'default-secret-key')
    flask_app.config['JSON_AS_ASCII'] = False

    # 启用CORS
    CORS(flask_app)

    # 创建SocketIO实例
    socketio_instance = SocketIO(flask_app,
                                 cors_allowed_origins="*",
                                 async_mode='gevent')

    # 注册蓝图
    flask_app.register_blueprint(api_bp, url_prefix='/api')

    # 设置WebSocket
    setup_websocket(socketio_instance)

    return flask_app, socketio_instance


def signal_handler(signum, frame):
    """处理信号"""
    global scheduler, clash_manager
    logger.info(f"接收到信号 {signum}，正在关闭...")

    if scheduler:
        scheduler.shutdown()

    if clash_manager:
        clash_manager.cleanup()

    sys.exit(0)


def main():
    """主函数"""
    global app, socketio, scheduler, clash_manager, logger

    # 设置日志
    logger = setup_logger()
    logger.info("Netflix Unblock Checker 启动中...")

    # 创建应用
    app, socketio = create_app()

    # 初始化配置
    config = Config()

    # 初始化Clash管理器并启动Clash
    clash_manager = LocalClashManager(config)
    logger.info("正在启动Clash服务...")

    # 如果有默认配置，启动Clash
    default_config = "/root/.config/mihomo/config.yaml"
    if os.path.exists(default_config):
        if clash_manager.start_clash():
            logger.info("Clash服务启动成功")
        else:
            logger.warning("Clash服务启动失败，但继续运行Web服务")
    else:
        logger.info("没有找到默认Clash配置，等待通过Web界面配置")

    # 初始化调度器
    scheduler = TaskScheduler(config)
    scheduler.start()

    # 注册信号处理
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 启动服务器
    port = config.get('http_server.port', 8080)
    logger.info(f"Web服务器启动在端口 {port}")

    socketio.run(app,
                 host='0.0.0.0',
                 port=port,
                 debug=False)


if __name__ == "__main__":
    main()