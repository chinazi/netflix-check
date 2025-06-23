"""
认证相关功能
"""
import jwt
import functools
from datetime import datetime, timedelta, timezone
from flask import request, jsonify
from app.core.config import Config
from app.core.logger import LoggerManager
logger = LoggerManager.get_logger()

def generate_token(access_key: str) -> str:
    """生成JWT令牌"""
    try:
        config = Config()
        secret_key = config.get('http_server.access_key')
        # 使用UTC时间避免时区问题
        payload = {
            'access_key': access_key,
            'exp': datetime.now(timezone.utc) + timedelta(hours=24),
            'iat': datetime.now(timezone.utc)
        }
        token = jwt.encode(payload, secret_key, algorithm='HS256')
        logger.info(f"生成令牌成功")
        return token
    except Exception as e:
        logger.error(f"生成令牌失败: {e}")
        raise

def verify_token(token: str) -> bool:
    """验证JWT令牌"""
    try:
        config = Config()
        secret_key = config.get('http_server.access_key')
        # 解码并验证
        payload = jwt.decode(token, secret_key, algorithms=['HS256'])
        # 验证access_key是否匹配
        stored_key = payload.get('access_key')
        if stored_key != secret_key:
            logger.warning("令牌中的密钥不匹配")
            return False
        logger.debug("令牌验证成功")
        return True
    except jwt.ExpiredSignatureError:
        logger.warning("令牌已过期")
        return False
    except jwt.InvalidTokenError as e:
        logger.warning(f"无效的令牌: {e}")
        return False
    except Exception as e:
        logger.error(f"验证令牌异常: {e}")
        return False

def require_auth(f):
    """需要认证的装饰器"""
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        # 记录请求详情
        logger.debug(f"收到请求 - 方法: {request.method}, 路径: {request.path}, "
                    f"来源IP: {request.remote_addr}, "
                    f"User-Agent: {request.headers.get('User-Agent', 'Unknown')}")

        # 记录所有请求头（用于调试）
        logger.debug(f"请求头: {dict(request.headers)}")

        # 从请求头获取令牌
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            logger.warning(f"缺少Authorization头 - 路径: {request.path}, "
                         f"方法: {request.method}, 来源IP: {request.remote_addr}, "
                         f"User-Agent: {request.headers.get('User-Agent', 'Unknown')}")
            return jsonify({'error': '缺少认证信息'}), 401

        try:
            # Bearer token
            parts = auth_header.split(' ')
            if len(parts) != 2 or parts[0] != 'Bearer':
                logger.warning(f"认证格式错误: {auth_header} - 路径: {request.path}")
                return jsonify({'error': '认证格式错误'}), 401

            token = parts[1]
            if not verify_token(token):
                logger.warning(f"令牌验证失败 - 路径: {request.path}, 来源IP: {request.remote_addr}")
                return jsonify({'error': '认证失败'}), 401

            logger.debug(f"认证成功 - 路径: {request.path}")
            return f(*args, **kwargs)

        except Exception as e:
            logger.error(f"认证错误: {e} - 路径: {request.path}")
            return jsonify({'error': '认证失败'}), 401

    return decorated_function

def check_access_key(access_key: str) -> bool:
    """检查访问密钥"""
    config = Config()
    correct_key = config.get('http_server.access_key')
    result = access_key == correct_key
    if not result:
        logger.warning(f"密钥不匹配 - 提供的密钥: {access_key[:4]}****")
    return result