"""
配置管理模块
"""

import os

import yaml
from typing import Any, Dict
from threading import Lock


class Config:
    """配置管理器 - 单例模式"""

    _instance = None
    _lock = Lock()
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if Config._initialized:
            return

        with Config._lock:
            if Config._initialized:
                return

            print("[Config] 开始初始化配置...")

            self.config_file = os.environ.get('CONFIG_FILE', 'config/config.yaml')
            self._config = {}
            self._config_lock = Lock()

            self.load_config()

            Config._initialized = True
            print("[Config] 配置初始化完成")

    def load_config(self) -> bool:
        """加载配置文件"""
        try:
            print(f"[Config] 尝试加载配置文件: {self.config_file}")

            if not os.path.isabs(self.config_file):
                project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                self.config_file = os.path.join(project_root, self.config_file)

            print(f"[Config] 配置文件绝对路径: {self.config_file}")

            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self._config = yaml.safe_load(f) or {}
                print(f"[Config] 成功加载配置文件")
                return True
            else:
                print(f"[Config] 配置文件不存在，使用默认配置")
                self._config = self._get_default_config()
                os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
                self.save_config()
                return True

        except Exception as e:
            print(f"[Config] 加载配置失败: {e}")
            import traceback
            traceback.print_exc()
            self._config = self._get_default_config()
            return False

    def save_config(self) -> bool:
        """保存配置到文件"""
        try:
            with self._config_lock:
                os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
                with open(self.config_file, 'w', encoding='utf-8') as f:
                    yaml.dump(self._config, f,
                             default_flow_style=False,
                             allow_unicode=True,
                             sort_keys=False)
                print(f"[Config] 配置已保存到: {self.config_file}")
                return True
        except Exception as e:
            print(f"[Config] 保存配置失败: {e}")
            return False

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值，支持点号分隔的嵌套键"""
        try:
            with self._config_lock:
                keys = key.split('.')
                value = self._config

                for k in keys:
                    if isinstance(value, dict) and k in value:
                        value = value[k]
                    else:
                        return default

                return value
        except Exception as e:
            print(f"[Config] 获取配置错误 {key}: {e}")
            return default

    def set(self, key: str, value: Any) -> bool:
        """设置配置值，支持点号分隔的嵌套键"""
        try:
            with self._config_lock:
                keys = key.split('.')
                config = self._config

                # 创建嵌套结构
                for k in keys[:-1]:
                    if k not in config:
                        config[k] = {}
                    config = config[k]

                config[keys[-1]] = value
                return self.save_config()
        except Exception as e:
            print(f"[Config] 设置配置错误 {key}: {e}")
            return False

    def get_all(self) -> Dict:
        """获取所有配置"""
        with self._config_lock:
            return self._config.copy()

    def update_all(self, new_config: Dict) -> bool:
        """更新整个配置"""
        try:
            config_copy = new_config.copy()

            with self._config_lock:
                self._config = config_copy

            return self.save_config()

        except Exception as e:
            print(f"[Config] 更新配置错误: {e}")
            return False


    def _get_default_config(self) -> Dict:
        """获取默认配置"""
        return {
            "proxy_config_urls": [],
            "http_server": {
                "port": 8080,
                "access_key": "your-secret-key"
            },
            "schedule": {
                "cron": "0 */6 * * *"
            },
            "clash": {
                "api_url": "http://127.0.0.1:9090",
                "secret": "",
                "proxy": {
                    "auth": False,
                    "user": "",
                    "pass": "",
                    "host": "127.0.0.1",
                    "port": 7890
                }
            },
            "netflix": {
                "test_urls": [
                    "https://www.netflix.com/title/70143836",
                    "https://www.netflix.com/title/81280792"
                ],
                "error_msg": "Oh no!",
                "timeout": 20,
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "accept_language": "zh-CN,zh;q=0.9,en;q=0.8"
            }
        }