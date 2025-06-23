"""
Netflix检测核心模块
"""
import logging
import os
import json
import time
import requests
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import yaml

from app.core.logger import LoggerManager
from app.core.config import Config
from app.core.clash_manager import LocalClashManager

class NetflixChecker:
    """Netflix解锁检测器"""
    def __init__(self, config: Config):
        self.config = config
        self.logger = LoggerManager.get_logger()
        self.clash_manager = LocalClashManager(config)
        # Netflix配置
        self.test_urls = config.get('netflix.test_urls', [
            "https://www.netflix.com/title/70143836",
            "https://www.netflix.com/title/81280792"
        ])
        self.error_msg = config.get('netflix.error_msg', 'Oh no!')
        self.timeout = config.get('netflix.timeout', 20)
        self.user_agent = config.get('netflix.user_agent',
                                     'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        self.accept_language = config.get('netflix.accept_language', 'en-US,en;q=0.9')
        # 代理配置
        proxy_config = config.get('clash.proxy', {})
        if proxy_config.get('auth'):
            proxy_url = f"http://{proxy_config['user']}:{proxy_config['pass']}@" \
                        f"{proxy_config['host']}:{proxy_config['port']}"
        else:
            proxy_url = f"http://{proxy_config['host']}:{proxy_config['port']}"
        self.proxies = {
            'http': proxy_url,
            'https': proxy_url
        }
        # 结果存储
        self.results_file = "results/netflix_check_results.json"
        os.makedirs(os.path.dirname(self.results_file), exist_ok=True)

    def _test_single_url(self, url: str, proxy_name: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """测试单个URL

        返回: (是否成功, 地区码, 响应内容)
        """
        try:
            headers = {
                'User-Agent': self.user_agent,
                'Accept-Language': self.accept_language,
                # 添加防缓存头
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0'
            }

            # 创建新的session避免缓存
            session = requests.Session()
            session.proxies = self.proxies

            self.logger.debug(f"[{proxy_name}] 正在请求: {url}")

            response = session.get(
                url,
                headers=headers,
                timeout=self.timeout,
                allow_redirects=True
            )

            self.logger.debug(f"[{proxy_name}] 响应状态码: {response.status_code}")
            self.logger.debug(f"[{proxy_name}] 最终URL: {response.url}")

            if response.status_code == 200:
                content = response.text

                # 检查是否被封锁
                if self.error_msg in content:
                    self.logger.debug(f"[{proxy_name}] 检测到错误信息: {self.error_msg}")
                    return False, None, content

                # 从最终URL提取地区
                final_url = response.url
                self.logger.debug(f"[{proxy_name}] 分析最终URL: {final_url}")

                # 尝试从URL路径中提取地区码
                # 格式: https://www.netflix.com/sg/title/xxx 或 https://www.netflix.com/sg-en/title/xxx
                match = re.search(r'netflix\.com/([a-z]{2}(?:-[a-z]{2})?)/title', final_url, re.IGNORECASE)
                if match:
                    region = match.group(1).upper()
                    self.logger.debug(f"[{proxy_name}] 从URL提取到地区: {region}")
                else:
                    # 如果URL中没有地区，尝试从内容提取
                    self.logger.debug(f"[{proxy_name}] URL中未找到地区信息，尝试从内容提取")
                    region = self._extract_region_from_content(content, proxy_name)
                    if not region:
                        # 检查是否直接跳转到了主域名
                        if "www.netflix.com/title" in final_url and "/title" == final_url.split("netflix.com")[1][:6]:
                            region = 'US'  # 默认为美国
                            self.logger.debug(f"[{proxy_name}] 使用默认地区: US")

                session.close()
                return True, region, content
            else:
                session.close()
                return False, None, f"HTTP {response.status_code}"

        except requests.exceptions.Timeout:
            self.logger.debug(f"[{proxy_name}] 请求超时")
            return False, None, "Timeout"
        except requests.exceptions.ConnectionError as e:
            self.logger.debug(f"[{proxy_name}] 连接错误: {e}")
            return False, None, "Connection Error"
        except Exception as e:
            self.logger.error(f"[{proxy_name}] 测试URL时出错: {e}")
            return False, None, str(e)

    def _extract_region_from_content(self, content: str, proxy_name: str) -> Optional[str]:
        """从响应内容中提取地区信息"""
        # 尝试多种模式匹配地区
        patterns = [
            (r'"geoCountry":"([A-Z]{2})"', 'geoCountry'),
            (r'"countryCode":"([A-Z]{2})"', 'countryCode'),
            (r'data-geo="([A-Z]{2})"', 'data-geo'),
            (r'"location":"([A-Z]{2})"', 'location'),
            (r'\"geolocation\"\s*:\s*\"([A-Z]{2})\"', 'geolocation'),
            (r'window\.netflix\.reactContext\.models\.geo\.country\s*=\s*["\']([A-Z]{2})["\']', 'reactContext')
        ]

        for pattern, name in patterns:
            match = re.search(pattern, content)
            if match:
                region = match.group(1)
                self.logger.debug(f"[{proxy_name}] 从内容提取到地区 ({name}): {region}")
                return region

        # 记录一小段内容用于调试
        self.logger.debug(f"[{proxy_name}] 未能从内容提取地区，响应片段: {content[:200]}")
        return None

    def check_single_proxy(self, proxy: Dict) -> Dict:
        """检测单个代理的Netflix解锁状态"""
        proxy_name = proxy.get('name', 'Unknown')
        result = {
            'name': proxy_name,
            'type': proxy.get('type', ''),
            'server': proxy.get('server', ''),
            'port': proxy.get('port', ''),
            'status': 'failed',
            'region': None,
            'details': '',
            'check_time': datetime.now().isoformat()
        }

        try:
            # 切换代理
            self.logger.debug(f"准备切换到代理: {proxy_name}")
            if not self.clash_manager.switch_proxy(proxy_name):
                result['details'] = '切换代理失败'
                self.logger.error(f"切换到代理 {proxy_name} 失败")
                return result

            # 增加等待时间确保代理切换生效
            time.sleep(1)


            # 验证代理是否真的切换了
            current_proxy = self.clash_manager.get_current_proxy()
            self.logger.info(f"当前代理: {current_proxy}")

            current_ip = self.check_current_ip()
            self.logger.info(f"当前IP: {current_ip}")
            # 测试所有URL
            test_results = []
            regions_found = []

            for i, url in enumerate(self.test_urls):
                self.logger.debug(f"[{proxy_name}] 测试URL {i+1}/{len(self.test_urls)}")
                success, region, content = self._test_single_url(url, proxy_name)
                test_results.append({
                    'url': url,
                    'success': success,
                    'region': region
                })
                if success and region:
                    regions_found.append(region)

                # 每个URL之间稍微等待一下
                if i < len(self.test_urls) - 1:
                    time.sleep(1)

            # 记录测试结果
            self.logger.debug(f"[{proxy_name}] 测试结果: {test_results}")

            # 分析结果
            successful_tests = [t for t in test_results if t['success']]

            if len(successful_tests) == len(self.test_urls):
                # 所有URL都成功 - 完全解锁
                result['status'] = 'full'
                # 检查地区是否一致
                unique_regions = list(set(regions_found))
                if len(unique_regions) == 1:
                    result['region'] = unique_regions[0]
                elif len(unique_regions) > 1:
                    # 多个地区，可能有问题
                    result['region'] = regions_found[0]
                    self.logger.warning(f"[{proxy_name}] 检测到多个地区: {unique_regions}")
                else:
                    result['region'] = 'US'
                result['details'] = f'完全解锁 - {result["region"]}'
            elif successful_tests:
                # 部分URL成功 - 仅解锁自制剧
                result['status'] = 'partial'
                result['region'] = regions_found[0] if regions_found else None
                result['details'] = f'仅解锁自制剧 - {result["region"] or "未知地区"}'
            else:
                # 所有测试都失败 - 无法解锁
                result['status'] = 'blocked'
                result['details'] = 'Netflix检测到代理或无法访问'

        except Exception as e:
            result['status'] = 'failed'
            result['details'] = f'测试错误: {str(e)}'
            self.logger.error(f"检测代理 {proxy_name} 时出错: {e}", exc_info=True)

        return result

    def check_current_ip(self) -> str:
        """检查当前使用的IP地址"""
        try:
            proxies = {
                'http': f'http://127.0.0.1:7890',
                'https': f'http://127.0.0.1:7890'
            }
            response = requests.get('http://ip-api.com/json',
                                    proxies=proxies,
                                    timeout=10)
            data = response.json()
            return f"{data.get('query')} ({data.get('country')})"
        except Exception as e:
            self.logger.error(f"获取IP失败: {e}")
            return "Unknown"


    def check_all_proxies(self, proxies: List[Dict], max_workers: int = 1) -> List[Dict]:
        """检测所有代理"""
        results = []
        total = len(proxies)
        self.logger.info(f"开始检测 {total} 个代理")

        # 设置日志级别为DEBUG以获取更多信息
        self.logger.setLevel(logging.DEBUG)

        # 单线程顺序检测
        for i, proxy in enumerate(proxies):
            proxy_name = proxy.get('name', 'Unknown')
            self.logger.info(f"检测进度: {i + 1}/{total} - {proxy_name}")

            result = self.check_single_proxy(proxy)
            results.append(result)

            # 记录结果
            status_emoji = {
                'full': '✅',
                'partial': '⚠️',
                'blocked': '❌',
                'failed': '💔'
            }.get(result['status'], '❓')

            log_msg = f"{status_emoji} {result['name']} - {result['status']}"
            if result['region']:
                log_msg += f" - {result['region']}"
            log_msg += f" - {result['details']}"
            self.logger.info(log_msg)

            # 每10个节点输出进度
            if (i + 1) % 10 == 0:
                unlocked_count = sum(1 for r in results if r['status'] in ['full', 'partial'])
                self.logger.info(f"已测试 {i + 1} 个节点，找到 {unlocked_count} 个可解锁节点")

        return results

    def save_results(self, results: List[Dict]):
        """保存检测结果"""
        try:
            # 添加汇总信息
            summary = {
                'check_time': datetime.now().isoformat(),
                'total': len(results),
                'full': sum(1 for r in results if r['status'] == 'full'),
                'partial': sum(1 for r in results if r['status'] == 'partial'),
                'blocked': sum(1 for r in results if r['status'] == 'blocked'),
                'failed': sum(1 for r in results if r['status'] == 'failed')
            }

            # 按地区统计
            region_stats = {}
            for r in results:
                if r['status'] in ['full', 'partial'] and r['region']:
                    region = r['region']
                    if region not in region_stats:
                        region_stats[region] = {'full': 0, 'partial': 0}
                    region_stats[region][r['status']] += 1

            summary['regions'] = region_stats

            data = {
                'summary': summary,
                'results': results
            }

            with open(self.results_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            self.logger.info(f"结果已保存到: {self.results_file}")

            self.save_clash_subscription(results)

            # 输出汇总信息
            self.logger.info(f"检测完成 - 总计: {summary['total']}, "
                           f"完全解锁: {summary['full']}, "
                           f"部分解锁: {summary['partial']}, "
                           f"被封锁: {summary['blocked']}, "
                           f"失败: {summary['failed']}")

            # 输出地区统计
            if region_stats:
                self.logger.info("地区分布:")
                for region, stats in sorted(region_stats.items()):
                    self.logger.info(f"  {region}: 完全解锁 {stats['full']}, 部分解锁 {stats['partial']}")

        except Exception as e:
            self.logger.error(f"保存结果失败: {e}")

    def save_clash_subscription(self, results: List[Dict]):
        """保存完全解锁的节点为Clash订阅格式"""
        try:
            # 只筛选完全解锁的节点
            unlocked_proxies = []

            for result in results:
                if result['status'] == 'full':  # 只要完全解锁的
                    # 复制原始代理配置
                    proxy = result['proxy'].copy()

                    # 修改节点名称，添加 -NF 后缀
                    original_name = proxy.get('name', '')
                    proxy['name'] = f"{original_name}-NF"

                    unlocked_proxies.append(proxy)

            if unlocked_proxies:
                # 创建Clash订阅格式
                clash_config = {
                    'proxies': unlocked_proxies
                }

                # 保存为YAML文件
                clash_file = os.path.join(self.results_dir, 'netflix_unlocked_proxies.yaml')
                with open(clash_file, 'w', encoding='utf-8') as f:
                    yaml.dump(clash_config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

                self.logger.info(f"Clash订阅已保存到: {clash_file}")
                self.logger.info(f"共保存 {len(unlocked_proxies)} 个完全解锁节点")
            else:
                self.logger.warning("没有找到完全解锁的节点")
                # 创建一个空的订阅文件
                clash_file = os.path.join(self.results_dir, 'netflix_unlocked_proxies.yaml')
                with open(clash_file, 'w', encoding='utf-8') as f:
                    yaml.dump({'proxies': []}, f, allow_unicode=True)

        except Exception as e:
            self.logger.error(f"保存Clash订阅失败: {e}")
    def load_results(self) -> Optional[Dict]:
        """加载上次的检测结果"""
        try:
            if os.path.exists(self.results_file):
                with open(self.results_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return None
        except Exception as e:
            self.logger.error(f"加载结果失败: {e}")
            return None