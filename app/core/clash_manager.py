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
        self.session = requests.Session()

    def download_and_merge_configs(self, urls: List[str]) -> Tuple[Optional[str], List[Dict]]:
        """下载并合并多个配置文件"""
        all_proxies = []
        configs = []

        for i, url in enumerate(urls):
            self.logger.info(f"下载配置 {i + 1}/{len(urls)}: {url}")
            try:
                response = requests.get(url, timeout=30)
                response.raise_for_status()

                config_data = yaml.safe_load(response.text)
                configs.append(config_data)

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

        merged_config = self._merge_configs(configs, all_proxies)

        self.clash_config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.clash_config_path, 'w', encoding='utf-8') as f:
            yaml.dump(merged_config, f, allow_unicode=True, sort_keys=False)

        self.logger.info(f"配置已保存到: {self.clash_config_path}")
        return str(self.clash_config_path), all_proxies

    def _merge_configs(self, configs: List[Dict], all_proxies: List[Dict]) -> Dict:
        """合并多个配置文件"""
        merged = {
            'port': 7890,
            'socks-port': 7891,
            'mode': 'global',
            'external-controller':  self.config.get('clash.external_controller', '127.0.0.1'),
            'secret': self.config.get('clash.secret', ''),
            'dns': {
                'enable': True,
                'enhanced-mode': 'fake-ip',
                'nameserver': [
                    '114.114.114.114',
                    '223.5.5.5',
                    '8.8.8.8'
                ],
                'fallback': [],
                'fake-ip-filter': [
                    '+.stun.*.*',
                    '+.stun.*.*.*',
                    '+.stun.*.*.*.*',
                    '+.stun.*.*.*.*.*',
                    '*.n.n.srv.nintendo.net',
                    '+.stun.playstation.net',
                    'xbox.*.*.microsoft.com',
                    '*.*.xboxlive.com',
                    '*.msftncsi.com',
                    '*.msftconnecttest.com',
                    'WORKGROUP'
                ]
            }
        }

        proxy_config = self.config.get('clash.proxy', {})
        if proxy_config.get('auth'):
            merged['authentication'] = [
                f"{proxy_config['user']}:{proxy_config['pass']}"
            ]

        # 设置代理列表
        merged['proxies'] = all_proxies

        if configs:
            base_config = configs[0]

            if 'proxy-groups' in base_config:
                merged['proxy-groups'] = base_config['proxy-groups']

            if 'rules' in base_config:
                merged['rules'] = base_config['rules']

            for key in ['rule-providers', 'hosts', 'tun', 'profile', 'experimental']:
                if key in base_config:
                    merged[key] = base_config[key]

        return merged


    def start_clash(self) -> bool:
        """启动Clash进程"""
        try:
            if self._check_clash_running():
                self.logger.info("Clash已经在运行")
                return True

            if not self.clash_config_path.exists():
                self.logger.error(f"配置文件不存在: {self.clash_config_path}")
                return False

            cmd = f'nohup /usr/local/bin/clash -d /root/.config/mihomo > /root/.config/mihomo/clash.log 2>&1 &'
            self.logger.info(f"启动Clash: {cmd}")

            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

            if result.returncode != 0:
                self.logger.error(f"执行启动命令失败: {result.stderr}")
                return False

            time.sleep(3)

            if self._check_clash_running():
                self.logger.info("Clash启动成功")
                try:
                    pid_result = subprocess.run("pgrep -f '/usr/local/bin/clash -d'",
                                                shell=True, capture_output=True, text=True)
                    if pid_result.returncode == 0:
                        pid = pid_result.stdout.strip()
                        self.logger.info(f"Clash PID: {pid}")
                except:
                    pass
                return True
            else:
                self.logger.error("Clash启动后API不可访问")
                try:
                    with open('/root/.config/mihomo/clash.log', 'r') as f:
                        last_lines = f.readlines()[-20:]  # 读取最后20行
                        self.logger.error(f"Clash日志: {''.join(last_lines)}")
                except Exception as e:
                    self.logger.error(f"无法读取日志: {e}")
                return False


        except Exception as e:
            self.logger.error(f"启动Clash异常: {e}")
            return False

    def stop_clash(self) -> bool:
        """停止Clash进程"""
        try:
            if self.clash_process:
                self.logger.info("正在停止Clash进程...")
                self.clash_process.terminate()

                try:
                    self.clash_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    # 强制终止
                    self.logger.warning("正常终止超时，强制终止Clash")
                    self.clash_process.kill()
                    self.clash_process.wait()

                self.clash_process = None

            try:
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
            if config_path and config_path != str(self.clash_config_path):
                import shutil
                shutil.copy2(config_path, self.clash_config_path)
                self.logger.info(f"已更新配置文件: {self.clash_config_path}")

            self.stop_clash()
            time.sleep(2)

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
                self.logger.info(f"成功切换到代理: {proxy_name}")
                time.sleep(0.5)
                return True
            else:
                self.logger.error(f"切换代理失败: {response.status_code}")
                return False

        except Exception as e:
            self.logger.error(f"切换代理异常: {e}")
            return False

    def get_current_proxy(self) -> Optional[str]:
        """获取当前使用的代理"""
        try:
            selector = self._find_selector()
            if not selector:
                return None

            resp = self.session.get(f"{self.clash_api_url}/proxies/{selector}")
            if resp.status_code == 200:
                data = resp.json()
                return data.get('now')
        except Exception as e:
            self.logger.error(f"获取当前代理失败: {e}")
        return None

    def _find_selector(self) -> Optional[str]:
        """查找可用的选择器"""
        try:
            resp = self.session.get(f"{self.clash_api_url}/proxies")
            if resp.status_code != 200:
                self.logger.error(f"获取代理列表失败: {resp.status_code}")
                return None

            data = resp.json()
            proxies = data.get('proxies', {})

            selectors = []
            for name, info in proxies.items():
                if info.get('type') == 'Selector' and 'all' in info:
                    selectors.append(name)

            common_names = ['GLOBAL']
            for name in common_names:
                if name in selectors:
                    return name

            return selectors[0] if selectors else None

        except Exception as e:
            self.logger.error(f"查找选择器失败: {e}")
            return None

    def get_clash_logs(self, lines: int = 100) -> List[str]:
        """获取Clash日志"""
        try:
            if self.clash_process:
                return ["Clash正在运行"]
            else:
                return ["Clash未运行"]
        except Exception as e:
            self.logger.error(f"获取Clash日志失败: {e}")
            return [f"获取日志失败: {e}"]

    def cleanup(self):
        """清理资源"""
        self.stop_clash()