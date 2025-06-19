"""
WebSocket支持 - 实时日志推送
"""

import json
import time
import threading
from flask_socketio import emit, join_room, leave_room

from app.core.logger import LoggerManager

logger = LoggerManager.get_logger()

# WebSocket客户端管理
connected_clients = set()
log_push_thread = None
stop_log_push = False


def setup_websocket(socketio):
    """设置WebSocket事件处理"""

    @socketio.on('connect')
    def handle_connect():
        """客户端连接"""
        client_id = request.sid
        connected_clients.add(client_id)
        logger.info(f"WebSocket客户端连接: {client_id}")
        emit('connected', {'message': '已连接到日志推送服务'})

        # 启动日志推送线程
        global log_push_thread, stop_log_push
        if not log_push_thread or not log_push_thread.is_alive():
            stop_log_push = False
            log_push_thread = threading.Thread(target=push_logs, args=(socketio,))
            log_push_thread.daemon = True
            log_push_thread.start()

    @socketio.on('disconnect')
    def handle_disconnect():
        """客户端断开"""
        client_id = request.sid
        connected_clients.discard(client_id)
        logger.info(f"WebSocket客户端断开: {client_id}")

        # 如果没有客户端连接，停止日志推送
        if not connected_clients:
            global stop_log_push
            stop_log_push = True

    @socketio.on('join_logs')
    def handle_join_logs():
        """加入日志房间"""
        join_room('logs')
        emit('joined', {'room': 'logs'})

        # 发送最近的日志
        recent_logs = LoggerManager.get_logs(50)
        emit('logs_history', {'logs': recent_logs})

    @socketio.on('leave_logs')
    def handle_leave_logs():
        """离开日志房间"""
        leave_room('logs')
        emit('left', {'room': 'logs'})


def push_logs(socketio):
    """推送日志到客户端"""
    last_log_count = len(LoggerManager.get_logs())

    while not stop_log_push:
        try:
            # 检查是否有新日志
            current_logs = LoggerManager.get_logs()
            current_count = len(current_logs)

            if current_count > last_log_count:
                # 获取新日志
                new_logs = current_logs[last_log_count:]

                # 推送到所有在日志房间的客户端
                with socketio.app.app_context():
                    socketio.emit('new_logs', {
                        'logs': new_logs
                    }, room='logs')

                last_log_count = current_count

            time.sleep(1)  # 每秒检查一次

        except Exception as e:
            logger.error(f"推送日志错误: {e}")
            time.sleep(5)