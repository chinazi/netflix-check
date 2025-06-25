"""
API路由定义
"""

import os
from flask import Blueprint, request, jsonify, render_template, send_file, redirect, url_for

from app.core.config import Config
from app.core.logger import LoggerManager
from app.core.scheduler import TaskScheduler
from app.core.netflix_checker import NetflixChecker
from app.api.auth import require_auth, check_access_key, generate_token


api_bp = Blueprint('api', __name__)
logger = LoggerManager.get_logger()

# 全局调度器实例（在main.py中初始化）
scheduler = None


@api_bp.route('/login', methods=['POST'])
def login():
    """登录接口"""
    try:
        data = request.get_json()
        access_key = data.get('access_key', '')

        if not access_key:
            return jsonify({'error': '请输入访问密钥'}), 400

        if check_access_key(access_key):
            token = generate_token(access_key)
            logger.info("用户登录成功")
            return jsonify({
                'success': True,
                'token': token
            })
        else:
            logger.warning("登录失败：密钥错误")
            return jsonify({'error': '访问密钥错误'}), 401

    except Exception as e:
        logger.error(f"登录错误: {e}")
        return jsonify({'error': '登录失败'}), 500


@api_bp.route('/config', methods=['GET'])
@require_auth
def get_config():
    """获取配置"""
    try:
        config = Config()
        config_data = config.get_all()

        return jsonify({
            'success': True,
            'config': config_data
        })
    except Exception as e:
        logger.error(f"获取配置错误: {e}")
        return jsonify({'error': '获取配置失败'}), 500


@api_bp.route('/config', methods=['POST'])
@require_auth
def update_config():
    """更新配置"""
    try:
        new_config = request.get_json()

        if not new_config:
            return jsonify({'error': '配置不能为空'}), 400

        config = Config()

        if config.update_all(new_config):
            logger.info("配置已更新")
            return jsonify({
                'success': True,
                'message': '配置已保存'
            })
        else:
            return jsonify({'error': '保存配置失败'}), 500

    except Exception as e:
        logger.error(f"更新配置错误: {e}")
        return jsonify({'error': '更新配置失败'}), 500


@api_bp.route('/scheduler/status', methods=['GET'])
@require_auth
def get_scheduler_status():
    """获取调度器状态"""
    global scheduler

    try:
        if scheduler:
            status = {
                'running': scheduler.is_running(),
                'task_running': scheduler.is_task_running()
            }
        else:
            status = {
                'running': False,
                'task_running': False
            }

        return jsonify({
            'success': True,
            'status': status
        })
    except Exception as e:
        logger.error(f"获取状态错误: {e}")
        return jsonify({'error': '获取状态失败'}), 500


@api_bp.route('/scheduler/start', methods=['POST'])
@require_auth
def start_scheduler():
    """启动调度器"""
    global scheduler

    try:
        if not scheduler:
            config = Config()
            scheduler = TaskScheduler(config)

        scheduler.start()

        return jsonify({
            'success': True,
            'message': '调度器已启动'
        })
    except Exception as e:
        logger.error(f"启动调度器错误: {e}")
        return jsonify({'error': '启动失败'}), 500


@api_bp.route('/scheduler/stop', methods=['POST'])
@require_auth
def stop_scheduler():
    """停止调度器"""
    global scheduler

    try:
        if scheduler:
            scheduler.stop()

        return jsonify({
            'success': True,
            'message': '调度器已停止'
        })
    except Exception as e:
        logger.error(f"停止调度器错误: {e}")
        return jsonify({'error': '停止失败'}), 500


@api_bp.route('/scheduler/run-now', methods=['POST'])
@require_auth
def run_task_now():
    """立即执行任务"""
    global scheduler

    try:
        if not scheduler:
            config = Config()
            scheduler = TaskScheduler(config)

        if scheduler.run_task_now():
            return jsonify({
                'success': True,
                'message': '任务已开始执行'
            })
        else:
            return jsonify({'error': '任务正在执行中'}), 400

    except Exception as e:
        logger.error(f"执行任务错误: {e}")
        return jsonify({'error': '执行失败'}), 500


@api_bp.route('/logs', methods=['GET'])
@require_auth
def get_logs():
    """获取日志"""
    try:
        limit = request.args.get('limit', 100, type=int)
        logs = LoggerManager.get_logs(limit)

        return jsonify({
            'success': True,
            'logs': logs
        })
    except Exception as e:
        logger.error(f"获取日志错误: {e}")
        return jsonify({'error': '获取日志失败'}), 500


@api_bp.route('/results', methods=['GET'])
@require_auth
def get_results():
    """获取检测结果"""
    try:
        config = Config()
        checker = NetflixChecker(config)
        results = checker.load_results()

        if results:
            return jsonify({
                'success': True,
                'results': results
            })
        else:
            return jsonify({
                'success': True,
                'results': None,
                'message': '暂无检测结果'
            })
    except Exception as e:
        logger.error(f"获取结果错误: {e}")
        return jsonify({'error': '获取结果失败'}), 500


@api_bp.route('/results/download', methods=['GET'])
@require_auth
def download_results():
    """下载检测结果"""
    try:
        results_file = "/app/results/netflix_check_results.json"
        if os.path.exists(results_file):
            return send_file(
                results_file,
                as_attachment=True,
                download_name='netflix_results.json',
                mimetype='application/json'
            )
        else:
            return jsonify({'error': '结果文件不存在'}), 404
    except Exception as e:
        logger.error(f"下载结果错误: {e}")
        return jsonify({'error': '下载失败'}), 500


@api_bp.route('/version', methods=['GET'])
@require_auth
def get_version():
    """获取版本信息"""
    try:
        version_info = {
            'app_version': '1.0.0',
            'mihomo_info': None
        }
        version_file = '/app/version.txt'
        if os.path.exists(version_file):
            with open(version_file, 'r') as f:
                version_content = f.read().strip()
                version_info['mihomo_info'] = version_content

        return jsonify({
            'success': True,
            'version': version_info
        })
    except Exception as e:
        logger.error(f"获取版本信息错误: {e}")
        return jsonify({'error': '获取版本信息失败'}), 500


def set_scheduler(sched):
    """设置调度器实例"""
    global scheduler
    scheduler = sched


@api_bp.route('/subscription', methods=['GET'])
def get_netflix_subscription():
    """获取Netflix解锁节点订阅"""
    try:
        subscription_key = request.args.get('key', '')

        config = Config()
        correct_key = config.get('subscription.key', '')

        if not correct_key:
            logger.warning("订阅密钥未在配置文件中设置")
            return jsonify({'error': '订阅服务未配置'}), 503

        if subscription_key != correct_key:
            logger.warning(f"订阅密钥错误: {subscription_key}")
            return jsonify({'error': '无效的订阅密钥'}), 401

        subscription_file = "results/netflix_unlocked_proxies.yaml"
        if not os.path.exists(subscription_file):
            logger.info("订阅文件不存在，返回空订阅")
            empty_subscription = {
                'proxies': []
            }
            import yaml
            return yaml.dump(empty_subscription, allow_unicode=True), 200, {
                'Content-Type': 'text/plain; charset=utf-8',
                'Content-Disposition': 'inline; filename="netflix_proxies.yaml"'
            }

        with open(subscription_file, 'r', encoding='utf-8') as f:
            content = f.read()

        logger.info(f"订阅文件已提供给用户")

        return content, 200, {
            'Content-Type': 'text/plain; charset=utf-8',
            'Content-Disposition': 'inline; filename="netflix_proxies.yaml"'
        }

    except Exception as e:
        logger.error(f"获取订阅错误: {e}")
        return jsonify({'error': '获取订阅失败'}), 500


