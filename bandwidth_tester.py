import requests
import time
from concurrent.futures import ThreadPoolExecutor
import random
import logging
import os
import signal
import threading

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# 从环境变量读取配置,如果没有则使用默认值
# 默认提供多个高速CDN下载URL，确保持续稳定的下载速度
default_urls = [
    'https://speed.cloudflare.com/__down?bytes=100000000',  # Cloudflare 100MB测试文件
    'https://proof.ovh.net/files/100Mb.dat',  # OVH 100MB测试文件
    'https://ash-speed.hetzner.com/100MB.bin',  # Hetzner 100MB测试文件
    'https://speed.hetzner.de/100MB.bin',  # Hetzner DE 100MB
    'https://mirror.init7.net/speedtest/data/1000mb.bin',  # Init7 1GB测试文件
    'https://bouygues.testdebit.info/100M.iso',  # Bouygues 100MB
    'https://img.cmvideo.cn/publish/noms/2023/12/06/1O4SHFIFR36BD.gif'  # 原默认URL
]

url_list = os.getenv('URL_LIST', ','.join(default_urls)).split(',')
thread_count = int(os.getenv('THREAD_COUNT', '5'))  # 线程数量
# 增加连接池大小以支持更高并发
pool_size = max(thread_count * 2, 20)  # 至少20个连接
goal = int(os.getenv('GOAL_GB', '0'))  # 消耗的流量单位GB
if goal > 0:
    goal = goal * 1024 * 1024 * 1024  # GB转为B


# 线程安全的状态管理类
class ThreadSafeStats:
    """线程安全的统计信息管理"""

    def __init__(self):
        self._lock = threading.Lock()
        self._bytes_downloaded = 0
        self._running_threads = 0

    def add_bytes(self, bytes_count):
        """增加已下载字节数(线程安全)"""
        with self._lock:
            self._bytes_downloaded += bytes_count
            return self._bytes_downloaded

    def increment_running(self):
        """增加运行中的线程数(线程安全)"""
        with self._lock:
            self._running_threads += 1
            return self._running_threads

    def decrement_running(self):
        """减少运行中的线程数(线程安全)"""
        with self._lock:
            self._running_threads -= 1
            return self._running_threads

    def get_running_count(self):
        """获取当前运行中的线程数(线程安全)"""
        with self._lock:
            return self._running_threads

    def get_bytes_downloaded(self):
        """获取已下载字节数(线程安全)"""
        with self._lock:
            return self._bytes_downloaded

    def reset(self):
        """重置统计信息(线程安全)"""
        with self._lock:
            self._bytes_downloaded = 0
            self._running_threads = 0


# 全局状态对象
stats = ThreadSafeStats()
# 使用 threading.Event 替代全局布尔变量,更加线程安全
shutdown_event = threading.Event()


def signal_handler(_sig, _frame):
    """处理SIGTERM和SIGINT信号,优雅退出"""
    logging.info("收到退出信号,正在优雅关闭...")
    shutdown_event.set()


# 线程池
executor = ThreadPoolExecutor(max_workers=thread_count)

# 下载连接池 - 增大连接池以提高并发性能
session = requests.Session()
adapter = requests.adapters.HTTPAdapter(
    pool_connections=pool_size,
    pool_maxsize=pool_size,
    max_retries=3,  # 增加重试次数
    pool_block=False
)
session.mount('http://', adapter)
session.mount('https://', adapter)


def download(url):
    """
    下载文件函数(线程安全版本)

    Args:
        url: 下载URL

    Returns:
        bool: True表示下载完成或达到目标
    """
    response = None  # 初始化response,避免finally中未定义错误

    try:
        stats.increment_running()

        # 增加块大小以提高下载速度，设置超时避免挂起
        # 使用元组格式: (连接超时, 读取超时)
        response = session.get(url, stream=True, timeout=(5, 30))

        if response.status_code == 200:
            # 使用更大的块大小(100KB)提高下载效率
            for chunk in response.iter_content(chunk_size=102400):
                # 检查退出标志
                if shutdown_event.is_set():
                    break

                # 如果goal为0,不记录流量(无限制模式)
                if goal > 0 and chunk:
                    current_bytes = stats.add_bytes(len(chunk))

                    if current_bytes >= goal:
                        logging.info(
                            "流量已经消费了 %s B,达到目标 %s B,终止下载",
                            current_bytes,
                            goal
                        )
                        shutdown_event.set()  # 通知所有线程停止
                        return True
        else:
            logging.warning("HTTP状态码错误: %s - %s", response.status_code, url)

    except requests.exceptions.Timeout:
        logging.debug("下载超时: %s", url)
    except requests.exceptions.ConnectionError as e:
        logging.debug("连接错误: %s - %s", url, e)
    except requests.exceptions.RequestException as e:
        logging.debug("下载失败: %s - %s", url, e)
    except Exception as e:
        logging.error("未预期的错误: %s - %s", url, e)
    finally:
        stats.decrement_running()

        # 安全关闭响应对象
        if response is not None:
            try:
                response.close()
            except Exception as e:
                logging.debug("关闭响应失败: %s", e)

    return True


def start_download():
    """初始化启动所有下载线程，立即开始工作"""
    stats.reset()  # 重置统计信息
    logging.info("快速启动 %s 个下载线程...", thread_count)

    # 立即启动所有线程，无延迟
    for _ in range(thread_count):
        executor.submit(download, random.choice(url_list))


if __name__ == "__main__":
    # 注册信号处理器
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    logging.info("启动刷下行服务...")
    logging.info(
        "配置: 线程数=%s, 目标流量=%s GB, URL数量=%s",
        thread_count,
        goal // (1024 * 1024 * 1024) if goal > 0 else 0,
        len(url_list)
    )

    # 无限制模式警告
    if goal == 0:
        logging.warning("=" * 60)
        logging.warning("⚠️  无限制流量模式已启用")
        logging.warning("请确保:")
        logging.warning("  1. 您有权使用目标URL进行测试")
        logging.warning("  2. 了解您的网络带宽和流量费用")
        logging.warning("  3. 不会影响其他用户的网络使用")
        logging.warning("=" * 60)

    start_download()

    # 主循环：快速检查并补充线程，保持持续下载
    check_interval = 0.5  # 每0.5秒检查一次，确保连续性

    while not shutdown_event.is_set():
        current_running = stats.get_running_count()
        current_bytes = stats.get_bytes_downloaded()

        # 检查是否需要补充线程
        if (goal == 0 or current_bytes < goal) and current_running < thread_count:
            need_count = thread_count - current_running
            logging.info("补充下载线程: %s 个", need_count)

            for _ in range(need_count):
                if shutdown_event.is_set():
                    break
                executor.submit(download, random.choice(url_list))

        time.sleep(check_interval)

    # 优雅退出
    logging.info("正在关闭线程池...")
    executor.shutdown(wait=True, cancel_futures=True)

    # 输出最终统计
    final_bytes = stats.get_bytes_downloaded()
    if goal > 0:
        logging.info(
            "程序已退出 - 总流量: %.2f GB",
            final_bytes / (1024 * 1024 * 1024)
        )
    else:
        logging.info("程序已退出")
