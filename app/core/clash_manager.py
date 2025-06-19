"""
Clash管理模块
"""

import os
import yaml
import requests
import subprocess
import time
import signal
from pathlib import Path
from typing import Dict, List, Tuple, Optional

from app.core.logger import LoggerManager
from app.core.config import Config


class LocalClashManager:
    """本地Clash管理器"""

    def __init__(self, config: Config):
        self.config = config
        self.logger = LoggerManager.get_logger()
        self.clash_api_url = config.get('clash.api_url', 'http://127.0.0.1:9090')
        self.clash_secret = config.get('clash.secret', '')
        self.temp_dir = Path("temp")
        self.temp_dir.mkdir(exist_ok=True)
        self.clash_process = None
        self.clash_config_path = Path("/root/.config/mihomo/config.yaml")

    def download_and_merge_configs(self, urls: List[str]) -> Tuple[Optional[str], List[Dict]]:
        """下载并合并多个配置文件"""
        all_proxies = []
        configs = []

        # 下载所有配置
        for i, url in enumerate(urls):
            self.logger.info(f"下载配置 {i + 1}/{len(urls)}: {url}")
            try:
                response = requests.get(url, timeout=30)
                response.raise_for_status()

                config_data = yaml.safe_load(response.text)
                configs.append(config_data)

                # 提取代理
                if 'proxies' in config_data:
                    proxies = config_data['proxies']
                    all_proxies.extend(proxies)
                    self.logger.info(f"从配置 {i + 1} 提取了 {len(proxies)} 个代理")

            except Exception as e:
                self.logger.error(f"下载配置失败 {url}: {e}")
                continue

        if not configs:
            self.logger.error("没有成功下载任何配置")
            return None, []

        # 合并配置
        merged_config = self._merge_configs(configs, all_proxies)

        # 保存合并后的配置到Clash配置目录
        self.clash_config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.clash_config_path, 'w', encoding='utf-8') as f:
            yaml.dump(merged_config, f, allow_unicode=True, sort_keys=False)

        self.logger.info(f"配置已保存到: {self.clash_config_path}")
        return str(self.clash_config_path), all_proxies

    def _merge_configs(self, configs: List[Dict], all_proxies: List[Dict]) -> Dict:
        """合并多个配置文件"""
        # 基础配置
        merged = {
            'mixed-port': 7890,
            'allow-lan': True,
            'bind-address': '*',
            'mode': 'rule',
            'log-level': 'info',
            'external-controller': '0.0.0.0:9090',
            'secret': self.config.get('clash.secret', ''),
            'proxies': [],
            'proxy-groups': [],
            'rules': []
        }

        # 如果配置了认证
        proxy_config = self.config.get('clash.proxy', {})
        if proxy_config.get('auth'):
            merged['authentication'] = [
                f"{proxy_config['user']}:{proxy_config['pass']}"
            ]

        # 更新代理列表
        merged['proxies'] = all_proxies

        # 创建代理组
        proxy_names = [p['name'] for p in all_proxies]

        # 从第一个配置复制规则和其他设置
        if configs:
            base_config = configs[0]
            if 'rules' in base_config:
                merged['rules'] = base_config['rules']
            if 'dns' in base_config:
                merged['dns'] = base_config['dns']

        # 创建代理组
        merged['proxy-groups'] = [
            {
                'name': 'GLOBAL',
                'type': 'select',
                'proxies': ['DIRECT'] + proxy_names
            },
            {
                'name': '🌍 All Proxies',
                'type': 'select',
                'proxies': proxy_names
            }
        ]

        # 添加基本规则（如果没有规则）
        if not merged['rules']:
            merged['rules'] = [
                'MATCH,GLOBAL'
            ]

        return merged

    def start_clash(self) -> bool:
        """启动Clash进程"""
        try:
            # 检查Clash是否已经在运行
            if self._check_clash_running():
                self.logger.info("Clash已经在运行")
                return True

            # 确保配置文件存在
            if not self.clash_config_path.exists():
                self.logger.error(f"配置文件不存在: {self.clash_config_path}")
                return False

            # 启动Clash
            cmd = ['/usr/local/bin/clash', '-f', str(self.clash_config_path)]
            self.logger.info(f"启动Clash: {' '.join(cmd)}")

            self.clash_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )

            # 等待启动
            time.sleep(3)

            # 检查是否成功启动
            if self.clash_process.poll() is not None:
                stdout, stderr = self.clash_process.communicate()
                self.logger.error(f"Clash启动失败: {stderr}")
                return False

            # 验证API是否可访问
            if self._check_clash_running():
                self.logger.info("Clash启动成功")
                return True
            else:
                self.logger.error("Clash启动后API不可访问")
                self.stop_clash()
                return False

        except Exception as e:
            self.logger.error(f"启动Clash异常: {e}")
            return False

    def stop_clash(self) -> bool:
        """停止Clash进程"""
        try:
            # 如果有进程引用，尝试正常终止
            if self.clash_process:
                self.logger.info("正在停止Clash进程...")
                self.clash_process.terminate()

                # 等待进程结束
                try:
                    self.clash_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    # 强制终止
                    self.logger.warning("正常终止超时，强制终止Clash")
                    self.clash_process.kill()
                    self.clash_process.wait()

                self.clash_process = None

            # 确保所有Clash进程都被终止
            try:
                # 查找所有clash进程
                result = subprocess.run(
                    ['pgrep', '-f', 'clash'],
                    capture_output=True,
                    text=True
                )

                if result.stdout.strip():
                    pids = result.stdout.strip().split('\n')
                    for pid in pids:
                        try:
                            os.kill(int(pid), signal.SIGTERM)
                        except:
                            pass
                    time.sleep(2)

            except Exception as e:
                self.logger.error(f"查找Clash进程失败: {e}")

            self.logger.info("Clash已停止")
            return True

        except Exception as e:
            self.logger.error(f"停止Clash失败: {e}")
            return False

    def restart_clash(self, config_path: str = None) -> bool:
        """重启Clash"""
        try:
            # 如果提供了新配置路径，更新配置
            if config_path and config_path != str(self.clash_config_path):
                import shutil
                shutil.copy2(config_path, self.clash_config_path)
                self.logger.info(f"已更新配置文件: {self.clash_config_path}")

            # 停止现有进程
            self.stop_clash()
            time.sleep(2)

            # 启动新进程
            return self.start_clash()

        except Exception as e:
            self.logger.error(f"重启Clash失败: {e}")
            return False

    def _check_clash_running(self) -> bool:
        """检查Clash是否在运行"""
        try:
            response = requests.get(
                f"{self.clash_api_url}/version",
                timeout=5,
                headers={'Authorization': f'Bearer {self.clash_secret}'} if self.clash_secret else {}
            )
            return response.status_code == 200
        except:
            return False

    def switch_proxy(self, proxy_name: str) -> bool:
        """切换代理"""
        try:
            headers = {}
            if self.clash_secret:
                headers['Authorization'] = f'Bearer {self.clash_secret}'

            # 切换GLOBAL代理组
            response = requests.put(
                f"{self.clash_api_url}/proxies/GLOBAL",
                json={'name': proxy_name},
                headers=headers,
                timeout=10
            )

            if response.status_code == 204:
                self.logger.debug(f"成功切换到代理: {proxy_name}")
                time.sleep(0.5)  # 给代理切换一点时间
                return True
            else:
                self.logger.error(f"切换代理失败: {response.status_code}")
                return False

        except Exception as e:
            self.logger.error(f"切换代理异常: {e}")
            return False

    def get_clash_logs(self, lines: int = 100) -> List[str]:
        """获取Clash日志"""
        try:
            if self.clash_process:
                # 从进程输出读取日志
                # 这里需要更复杂的实现来非阻塞读取
                return ["Clash正在运行"]
            else:
                return ["Clash未运行"]
        except Exception as e:
            self.logger.error(f"获取Clash日志失败: {e}")
            return [f"获取日志失败: {e}"]

    def cleanup(self):
        """清理资源"""
        self.stop_clash()