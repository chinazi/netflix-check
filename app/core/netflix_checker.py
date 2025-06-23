"""
Netflix检测核心模块
"""
import os
import json
import time
import requests
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
            time.sleep(1)  # 等待代理切换生效

            # 测试Netflix
            headers = {
                'User-Agent': self.user_agent,
                'Accept-Language': self.accept_language,
            }

            # 记录每个URL的测试结果
            test_results = []
            regions_found = []

            # 测试所有URL
            for test_url in self.test_urls:
                try:
                    response = requests.get(
                        test_url,
                        headers=headers,
                        proxies=self.proxies,
                        timeout=self.timeout,
                        allow_redirects=True
                    )

                    # 分析响应
                    if response.status_code == 200:
                        content = response.text
                        # 检查是否包含错误信息
                        if self.error_msg in content:
                            test_results.append({
                                'url': test_url,
                                'status': 'blocked',
                                'reason': 'Netflix检测到代理'
                            })
                        else:
                            # 尝试提取地区信息
                            region = self._extract_region(content)
                            if region:
                                regions_found.append(region)
                            test_results.append({
                                'url': test_url,
                                'status': 'success',
                                'region': region
                            })
                    elif response.status_code == 403:
                        test_results.append({
                            'url': test_url,
                            'status': 'blocked',
                            'reason': '访问被拒绝 (403)'
                        })
                    else:
                        test_results.append({
                            'url': test_url,
                            'status': 'failed',
                            'reason': f'HTTP {response.status_code}'
                        })
                except requests.exceptions.Timeout:
                    test_results.append({
                        'url': test_url,
                        'status': 'failed',
                        'reason': '请求超时'
                    })
                except requests.exceptions.ConnectionError:
                    test_results.append({
                        'url': test_url,
                        'status': 'failed',
                        'reason': '连接错误'
                    })
                except Exception as e:
                    test_results.append({
                        'url': test_url,
                        'status': 'failed',
                        'reason': f'测试失败: {str(e)}'
                    })

            # 分析所有测试结果
            successful_tests = [t for t in test_results if t['status'] == 'success']
            blocked_tests = [t for t in test_results if t['status'] == 'blocked']
            failed_tests = [t for t in test_results if t['status'] == 'failed']

            # 判断最终状态
            if len(successful_tests) == len(self.test_urls):
                # 所有URL都成功访问
                result['status'] = 'full'
                if regions_found:
                    # 使用第一个找到的地区
                    result['region'] = regions_found[0]
                    result['details'] = f'完全解锁 - 地区: {", ".join(set(regions_found))}'
                else:
                    result['details'] = '完全解锁 - 未检测到具体地区'
            elif successful_tests:
                # 部分URL成功访问
                result['status'] = 'partial'
                result['details'] = f'部分解锁 ({len(successful_tests)}/{len(self.test_urls)}个URL成功)'
                if regions_found:
                    result['region'] = regions_found[0]
                    result['details'] += f' - 地区: {", ".join(set(regions_found))}'
            elif blocked_tests:
                # 被Netflix检测到
                result['status'] = 'blocked'
                result['details'] = 'Netflix检测到代理'
            else:
                # 所有测试都失败
                result['status'] = 'failed'
                if failed_tests:
                    reasons = [t['reason'] for t in failed_tests]
                    result['details'] = f'连接失败: {"; ".join(set(reasons))}'
                else:
                    result['details'] = '未知错误'

            # 记录详细测试结果
            self.logger.debug(f"代理 {proxy_name} 测试详情: {test_results}")

        except Exception as e:
            result['details'] = f'代理错误: {str(e)}'
            self.logger.error(f"检测代理 {proxy_name} 时出错: {e}")

        return result

    def check_all_proxies(self, proxies: List[Dict], max_workers: int = 1) -> List[Dict]:
        """检测所有代理"""
        results = []
        total = len(proxies)
        self.logger.info(f"开始检测 {total} 个代理")

        # 单线程顺序检测（因为需要切换代理）
        for i, proxy in enumerate(proxies):
            self.logger.info(f"检测进度: {i + 1}/{total} - {proxy.get('name', 'Unknown')}")
            result = self.check_single_proxy(proxy)
            results.append(result)

            # 记录结果
            status_emoji = {
                'full': '✅',
                'partial': '⚠️',
                'blocked': '❌',
                'failed': '💔'
            }.get(result['status'], '❓')
            self.logger.info(
                f"{status_emoji} {result['name']} - {result['status']} - {result['details']}"
            )

        return results

    def _extract_region(self, content: str) -> Optional[str]:
        """从响应内容中提取地区信息"""
        # 这里需要根据实际的Netflix响应来解析地区信息
        # 简单示例：查找特定的标记
        import re
        # 尝试多种模式匹配地区
        patterns = [
            r'"geoCountry":"([A-Z]{2})"',
            r'"countryCode":"([A-Z]{2})"',
            r'data-geo="([A-Z]{2})"',
            r'"location":"([A-Z]{2})"',
            r'\"geolocation\"\s*:\s*\"([A-Z]{2})\"'
        ]

        for pattern in patterns:
            match = re.search(pattern, content)
            if match:
                return match.group(1)

        # 如果没找到，记录一下响应内容的一部分用于调试
        self.logger.debug(f"未能从响应中提取地区信息，响应片段: {content[:500]}")
        return None

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