"""
认证相关功能
"""

import jwt
import functools
from datetime import datetime, timedelta
from flask import request, jsonify, g

from app.core.config import Config
from app.core.logger import LoggerManager

logger = LoggerManager.get_logger()


def generate_token(access_key: str) -> str:
    """生成JWT令牌"""
    config = Config()
    secret_key = config.get('http_server.access_key')

    payload = {
        'access_key': access_key,
        'exp': datetime.utcnow() + timedelta(hours=24)  # 24小时过期
    }

    return jwt.encode(payload, secret_key, algorithm='HS256')


def verify_token(token: str) -> bool:
    """验证JWT令牌"""
    try:
        config = Config()
        secret_key = config.get('http_server.access_key')

        payload = jwt.decode(token, secret_key, algorithms=['HS256'])
        return True
    except jwt.ExpiredSignatureError:
        logger.warning("令牌已过期")
        return False
    except jwt.InvalidTokenError:
        logger.warning("无效的令牌")
        return False


def require_auth(f):
    """需要认证的装饰器"""

    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        # 从请求头获取令牌
        auth_header = request.headers.get('Authorization')

        if not auth_header:
            return jsonify({'error': '缺少认证信息'}), 401

        try:
            # Bearer token
            parts = auth_header.split(' ')
            if len(parts) != 2 or parts[0] != 'Bearer':
                return jsonify({'error': '认证格式错误'}), 401

            token = parts[1]

            if not verify_token(token):
                return jsonify({'error': '认证失败'}), 401

            return f(*args, **kwargs)

        except Exception as e:
            logger.error(f"认证错误: {e}")
            return jsonify({'error': '认证失败'}), 401

    return decorated_function


def check_access_key(access_key: str) -> bool:
    """检查访问密钥"""
    config = Config()
    correct_key = config.get('http_server.access_key')
    return access_key == correct_key