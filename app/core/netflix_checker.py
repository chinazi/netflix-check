"""
Netflix检测核心模块
"""
import os
import json
import time
import requests
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple
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

    def _test_single_url(self, url: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """测试单个URL

        返回: (是否成功, 地区码, 响应内容)
        """
        try:
            headers = {
                'User-Agent': self.user_agent,
                'Accept-Language': self.accept_language,
            }

            response = requests.get(
                url,
                headers=headers,
                proxies=self.proxies,
                timeout=self.timeout,
                allow_redirects=True
            )

            if response.status_code == 200:
                content = response.text

                # 检查是否被封锁
                if self.error_msg in content:
                    return False, None, content

                # 尝试从重定向URL中提取地区
                # 参考代码的逻辑：从最终URL中提取地区码
                final_url = response.url
                match = re.search(r'netflix\.com/([a-z]{2}(?:-[a-z]{2})?)/title', final_url)
                if match:
                    region = match.group(1).upper()
                    # 转换地区码格式 (例如 'sg' -> 'SG')
                    if '-' in region:
                        parts = region.split('-')
                        region = f"{parts[0].upper()}-{parts[1].upper()}"
                    else:
                        region = region.upper()
                else:
                    # 如果URL中没有地区信息，尝试从内容中提取
                    region = self._extract_region_from_content(content)
                    if not region:
                        region = 'US'  # 默认为美国

                return True, region, content
            else:
                return False, None, f"HTTP {response.status_code}"

        except requests.exceptions.Timeout:
            return False, None, "Timeout"
        except requests.exceptions.ConnectionError:
            return False, None, "Connection Error"
        except Exception as e:
            self.logger.error(f"测试URL {url} 时出错: {e}")
            return False, None, str(e)

    def _extract_region_from_content(self, content: str) -> Optional[str]:
        """从响应内容中提取地区信息"""
        # 尝试多种模式匹配地区
        patterns = [
            r'"geoCountry":"([A-Z]{2})"',
            r'"countryCode":"([A-Z]{2})"',
            r'data-geo="([A-Z]{2})"',
            r'"location":"([A-Z]{2})"',
            r'\"geolocation\"\s*:\s*\"([A-Z]{2})\"',
            r'window\.netflix\.reactContext\.models\.geo\.country\s*=\s*["\']([A-Z]{2})["\']'
        ]

        for pattern in patterns:
            match = re.search(pattern, content)
            if match:
                return match.group(1)

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
            if not self.clash_manager.switch_proxy(proxy_name):
                result['details'] = '切换代理失败'
                return result

            # 等待代理切换生效
            time.sleep(2)

            # 测试所有URL
            test_results = []
            regions_found = []

            for url in self.test_urls:
                success, region, content = self._test_single_url(url)
                test_results.append({
                    'url': url,
                    'success': success,
                    'region': region
                })
                if success and region:
                    regions_found.append(region)

            # 分析结果
            successful_tests = [t for t in test_results if t['success']]

            # 判断最终状态（参考代码的逻辑）
            if len(successful_tests) == len(self.test_urls):
                # 所有URL都成功 - 全区解锁
                result['status'] = 'full'
                # 使用第一个检测到的地区
                result['region'] = regions_found[0] if regions_found else 'US'
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

            # 记录详细信息
            self.logger.debug(f"代理 {proxy_name} 测试结果: {test_results}")

        except Exception as e:
            result['status'] = 'failed'
            result['details'] = f'测试错误: {str(e)}'
            self.logger.error(f"检测代理 {proxy_name} 时出错: {e}")

        return result

    def check_all_proxies(self, proxies: List[Dict], max_workers: int = 1) -> List[Dict]:
        """检测所有代理"""
        results = []
        total = len(proxies)
        self.logger.info(f"开始检测 {total} 个代理")

        # 单线程顺序检测（因为需要切换代理）
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

            # 定期输出进度
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