"""
定时任务调度模块
"""

import time
import threading
from datetime import datetime
from croniter import croniter
from typing import Optional, Callable

from app.core.logger import LoggerManager
from app.core.config import Config
from app.core.clash_manager import LocalClashManager
from app.core.netflix_checker import NetflixChecker


class TaskScheduler:
    """任务调度器"""

    def __init__(self, config: Config):
        self.config = config
        self.logger = LoggerManager.get_logger()
        self._running = False
        self._thread = None
        self._stop_event = threading.Event()
        self._task_running = False

    def start(self):
        """启动调度器"""
        if self._running:
            self.logger.warning("调度器已经在运行")
            return

        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="TaskScheduler")
        self._thread.daemon = True
        self._thread.start()
        self.logger.info("任务调度器已启动")

    def stop(self):
        """停止调度器"""
        if not self._running:
            return

        self._running = False
        self._stop_event.set()

        if self._thread:
            self._thread.join(timeout=5)

        self.logger.info("任务调度器已停止")

    def shutdown(self):
        """关闭调度器"""
        self.stop()

    def is_running(self) -> bool:
        """检查调度器是否在运行"""
        return self._running

    def is_task_running(self) -> bool:
        """检查是否有任务在执行"""
        return self._task_running

    def run_task_now(self):
        """立即执行一次任务"""
        if self._task_running:
            self.logger.warning("任务正在执行中，请稍后再试")
            return False

        # 在新线程中执行任务
        thread = threading.Thread(target=self._execute_task, name="ImmediateTask")
        thread.daemon = True
        thread.start()
        return True

    def _run(self):
        """调度器主循环"""
        cron_expr = self.config.get('schedule.cron', '0 */6 * * *')
        self.logger.info(f"调度器使用Cron表达式: {cron_expr}")

        while self._running:
            try:
                # 计算下次执行时间
                cron = croniter(cron_expr, datetime.now())
                next_run = cron.get_next(datetime)
                wait_seconds = (next_run - datetime.now()).total_seconds()

                self.logger.info(f"下次执行时间: {next_run.strftime('%Y-%m-%d %H:%M:%S')}")

                # 等待到执行时间或被中断
                if self._stop_event.wait(timeout=wait_seconds):
                    break

                # 执行任务
                if self._running:
                    self._execute_task()

            except Exception as e:
                self.logger.error(f"调度器错误: {e}", exc_info=True)
                # 出错后等待一段时间
                self._stop_event.wait(timeout=300)

    def _execute_task(self):
        """执行检查任务"""
        if self._task_running:
            self.logger.warning("任务已在执行中，跳过本次执行")
            return

        self._task_running = True
        start_time = datetime.now()

        try:
            self.logger.info(f"开始执行Netflix检查任务")

            # 创建管理器实例
            clash_manager = LocalClashManager(self.config)
            checker = NetflixChecker(self.config)

            # 下载并合并配置
            urls = self.config.get('proxy_config_urls', [])
            if not urls:
                self.logger.error("没有配置代理URL")
                return

            self.logger.info(f"开始下载 {len(urls)} 个配置文件")
            merged_config, all_proxies = clash_manager.download_and_merge_configs(urls)

            if not merged_config:
                self.logger.error("下载配置失败")
                return

            self.logger.info(f"成功合并配置，共 {len(all_proxies)} 个代理")

            # 重启Clash
            if not clash_manager.restart_clash(merged_config):
                self.logger.error("Clash重启失败")
                return

            # 测试所有代理
            results = checker.check_all_proxies(all_proxies)

            # 保存结果
            checker.save_results(results)

            # 统计结果
            total = len(results)
            unlocked = sum(1 for r in results if r['status'] == 'full')
            partial = sum(1 for r in results if r['status'] == 'partial')
            blocked = sum(1 for r in results if r['status'] == 'blocked')
            failed = sum(1 for r in results if r['status'] == 'failed')

            self.logger.info(
                f"检查完成 - 总计: {total}, "
                f"完全解锁: {unlocked}, "
                f"部分解锁: {partial}, "
                f"被封锁: {blocked}, "
                f"失败: {failed}"
            )

            # 计算耗时
            duration = (datetime.now() - start_time).total_seconds()
            self.logger.info(f"任务执行完成，耗时: {duration:.2f}秒")

        except Exception as e:
            self.logger.error(f"任务执行失败: {e}", exc_info=True)
        finally:
            self._task_running = False