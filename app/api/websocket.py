"""
WebSocket支持 - 实时日志推送
"""
import time
import threading
from flask_socketio import emit, join_room, leave_room, disconnect
from flask import request
from app.core.logger import LoggerManager
from app.api.auth import verify_token  # 导入 token 验证函数

logger = LoggerManager.get_logger()

# WebSocket客户端管理
connected_clients = set()
authenticated_clients = set()  # 已认证的客户端
log_push_thread = None
stop_log_push = False


def setup_websocket(socketio):
    """设置WebSocket事件处理"""

    @socketio.on('connect')
    def handle_connect(auth=None):
        """客户端连接"""
        client_id = request.sid

        # 验证 token
        if auth and isinstance(auth, dict):
            token = auth.get('token')
            if token and verify_token(token):
                # 认证成功
                connected_clients.add(client_id)
                authenticated_clients.add(client_id)
                logger.info(f"WebSocket客户端连接并认证成功: {client_id}")
                emit('connected', {'message': '已连接到日志推送服务', 'authenticated': True})

                # 启动日志推送线程
                global log_push_thread, stop_log_push
                if not log_push_thread or not log_push_thread.is_alive():
                    stop_log_push = False
                    log_push_thread = threading.Thread(target=push_logs, args=(socketio,))
                    log_push_thread.daemon = True
                    log_push_thread.start()
            else:
                # 认证失败
                logger.warning(f"WebSocket客户端认证失败: {client_id}")
                emit('error', {'message': '认证失败'})
                disconnect()  # 断开连接
                return False
        else:
            # 没有提供认证信息
            logger.warning(f"WebSocket客户端未提供认证信息: {client_id}")
            emit('error', {'message': '需要认证'})
            disconnect()  # 断开连接
            return False

    @socketio.on('disconnect')
    def handle_disconnect():
        """客户端断开"""
        client_id = request.sid
        connected_clients.discard(client_id)
        authenticated_clients.discard(client_id)
        logger.info(f"WebSocket客户端断开: {client_id}")

        # 如果没有客户端连接，停止日志推送
        if not connected_clients:
            global stop_log_push
            stop_log_push = True

    @socketio.on('join_logs')
    def handle_join_logs():
        """加入日志房间"""
        client_id = request.sid

        # 检查是否已认证
        if client_id not in authenticated_clients:
            emit('error', {'message': '未认证'})
            return

        join_room('logs')
        emit('joined', {'room': 'logs'})

        # 发送最近的日志
        recent_logs = LoggerManager.get_logs(50)
        emit('logs_history', {'logs': recent_logs})

    @socketio.on('leave_logs')
    def handle_leave_logs():
        """离开日志房间"""
        client_id = request.sid

        # 检查是否已认证
        if client_id not in authenticated_clients:
            return

        leave_room('logs')
        emit('left', {'room': 'logs'})


def push_logs(socketio):
    """推送日志到客户端（只推送给已认证的客户端）"""
    last_log_count = len(LoggerManager.get_logs())

    while not stop_log_push:
        try:
            # 检查是否有新日志
            current_logs = LoggerManager.get_logs()
            current_count = len(current_logs)

            if current_count > last_log_count:
                # 获取新日志
                new_logs = current_logs[last_log_count:]

                # 只推送给已认证的客户端
                socketio.emit('new_logs', {
                    'logs': new_logs
                }, room='logs', skip_sid=[sid for sid in connected_clients if sid not in authenticated_clients])

                last_log_count = current_count

            time.sleep(1)  # 每秒检查一次

        except Exception as e:
            logger.error(f"推送日志错误: {e}")
            time.sleep(5)