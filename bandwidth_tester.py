import requests
import time
from concurrent.futures import ThreadPoolExecutor
import random
import logging
from logging.handlers import RotatingFileHandler
import os
import signal
import threading


def setup_logging():
    """
    配置日志系统：控制台输出 + 可选的文件轮转日志

    日志文件会自动轮转，单个文件最大10MB，最多保留3个历史文件
    """
    # 获取日志级别配置
    log_level_str = os.getenv('LOG_LEVEL', 'INFO').upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    # 创建日志格式器
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # 配置根日志记录器
    logger = logging.getLogger()
    logger.setLevel(log_level)

    # 控制台处理器（主要用于Docker容器）
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 可选：文件日志处理器（仅在非容器环境或显式启用时）
    if os.getenv('ENABLE_FILE_LOG', 'false').lower() == 'true':
        try:
            # 轮转日志：单个文件最大10MB，保留3个备份
            file_handler = RotatingFileHandler(
                'bandwidth_tester.log',
                maxBytes=10 * 1024 * 1024,  # 10MB
                backupCount=3,
                encoding='utf-8'
            )
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
            logging.info("文件日志已启用: bandwidth_tester.log")
        except Exception as e:
            logging.warning("无法启用文件日志: %s", e)


# 配置日志系统
setup_logging()


def parse_env_config():
    """
    解析和验证环境变量配置

    Returns:
        tuple: (url_list, thread_count, pool_size, goal)

    Raises:
        SystemExit: 配置验证失败时退出程序
    """
    # 默认提供多个高速CDN下载URL，确保持续稳定的下载速度
    # 所有 URL 已验证可用（最后验证: 2025-10-16）
    default_urls = [
        'https://speedtest.dallas.linode.com/100MB-dallas.bin',  # Linode 100MB（美国，快速稳定）
        'http://nj-us-ping.vultr.com/vultr.com.100MB.bin',  # Vultr 100MB（美国，稳定）
        'http://speedtest.tele2.net/100MB.zip',  # Tele2 Speedtest（欧洲，稳定）
        'https://img.cmvideo.cn/publish/noms/2023/12/06/1O4SHFIFR36BD.gif',  # 中国移动（中国优化）
    ]

    # 解析 URL 列表（使用分号分隔避免 URL 查询参数中的逗号问题）
    url_list_str = os.getenv('URL_LIST', ';'.join(default_urls))
    # 兼容逗号分隔（向后兼容）
    if ';' in url_list_str:
        url_list = [url.strip() for url in url_list_str.split(';') if url.strip()]
    else:
        url_list = [url.strip() for url in url_list_str.split(',') if url.strip()]

    if not url_list:
        logging.error("配置错误: URL_LIST 为空，至少需要一个有效的下载URL")
        raise SystemExit(1)

    # 解析线程数
    try:
        thread_count = int(os.getenv('THREAD_COUNT', '5'))
        if not (1 <= thread_count <= 100):
            logging.error("配置错误: THREAD_COUNT 必须在 1-100 之间，当前值: %s", thread_count)
            raise SystemExit(1)
    except ValueError:
        logging.error("配置错误: THREAD_COUNT 必须是整数，当前值: %s", os.getenv('THREAD_COUNT'))
        raise SystemExit(1)

    # 解析目标流量
    try:
        goal = int(os.getenv('GOAL_GB', '0'))
        if goal < 0:
            logging.error("配置错误: GOAL_GB 不能为负数，当前值: %s", goal)
            raise SystemExit(1)
        if goal > 10000:
            logging.warning("警告: GOAL_GB 设置过大 (%s GB)，可能需要很长时间完成", goal)
        if goal > 0:
            goal = goal * 1024 * 1024 * 1024  # GB转为B
    except ValueError:
        logging.error("配置错误: GOAL_GB 必须是整数，当前值: %s", os.getenv('GOAL_GB'))
        raise SystemExit(1)

    # 计算连接池大小
    pool_size = max(thread_count * 2, 20)  # 至少20个连接

    return url_list, thread_count, pool_size, goal


# 解析配置
url_list, thread_count, pool_size, goal = parse_env_config()


# 线程安全的状态管理类
class ThreadSafeStats:
    """线程安全的统计信息管理"""

    def __init__(self):
        self._lock = threading.Lock()
        self._bytes_downloaded = 0
        self._running_threads = 0
        self._consecutive_failures = 0  # 连续失败次数
        self._last_success_time = time.time()  # 上次成功时间

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

    def record_failure(self):
        """记录失败(线程安全)"""
        with self._lock:
            self._consecutive_failures += 1
            return self._consecutive_failures

    def record_success(self):
        """记录成功(线程安全)"""
        with self._lock:
            self._consecutive_failures = 0
            self._last_success_time = time.time()

    def get_consecutive_failures(self):
        """获取连续失败次数(线程安全)"""
        with self._lock:
            return self._consecutive_failures

    def reset(self):
        """重置统计信息(线程安全)"""
        with self._lock:
            self._bytes_downloaded = 0
            self._running_threads = 0
            self._consecutive_failures = 0
            self._last_success_time = time.time()


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
        bool: True表示下载完成或达到目标, False表示失败
    """
    response = None  # 初始化response,避免finally中未定义错误
    is_running = False  # 标记是否已计入运行中
    download_success = False  # 标记下载是否成功

    try:
        # 增加块大小以提高下载速度，设置超时避免挂起
        # 使用元组格式: (连接超时, 读取超时)
        response = session.get(url, stream=True, timeout=(5, 30))

        if response.status_code == 200:
            # 连接成功后才计入运行中的线程
            stats.increment_running()
            is_running = True

            # 使用更大的块大小(100KB)提高下载效率
            for chunk in response.iter_content(chunk_size=102400):
                # 检查退出标志（双重检查避免超额下载）
                if shutdown_event.is_set():
                    break

                # 跳过空chunk
                if not chunk:
                    continue

                # 统一记录流量（无论是否有目标限制）
                current_bytes = stats.add_bytes(len(chunk))

                # 如果设置了目标流量，检查是否达到
                if goal > 0 and current_bytes >= goal:
                    logging.info(
                        "流量已经消费了 %.2f GB, 达到目标 %.2f GB, 终止下载",
                        current_bytes / (1024 * 1024 * 1024),
                        goal / (1024 * 1024 * 1024)
                    )
                    shutdown_event.set()  # 通知所有线程停止
                    download_success = True
                    return True

            # 正常下载完成（文件结束）
            download_success = True
            stats.record_success()
        else:
            logging.warning("HTTP状态码错误: %s - %s", response.status_code, url)
            stats.record_failure()

    except requests.exceptions.Timeout:
        logging.warning("下载超时: %s", url)
        stats.record_failure()
    except requests.exceptions.ConnectionError as e:
        logging.warning("连接错误: %s - %s", url, str(e)[:100])
        stats.record_failure()
    except requests.exceptions.RequestException as e:
        logging.warning("下载失败: %s - %s", url, str(e)[:100])
        stats.record_failure()
    except Exception as e:
        logging.error("未预期的错误: %s - %s", url, e)
        stats.record_failure()
    finally:
        # 只有计入的线程才减少计数
        if is_running:
            stats.decrement_running()

        # 安全关闭响应对象
        if response is not None:
            try:
                response.close()
            except Exception as e:
                logging.debug("关闭响应失败: %s", e)

    return download_success


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
    last_log_time = time.time()  # 上次日志输出时间
    log_interval = 10  # 每10秒输出一次统计信息
    last_bytes = 0  # 上次记录的字节数

    while not shutdown_event.is_set():
        current_running = stats.get_running_count()
        current_bytes = stats.get_bytes_downloaded()
        consecutive_failures = stats.get_consecutive_failures()

        # 防止无限重试风暴：如果连续失败次数过多，延迟重试
        if consecutive_failures > thread_count * 3:
            backoff_time = min(consecutive_failures * 2, 60)  # 最多延迟60秒
            logging.warning(
                "连续失败 %s 次，暂停 %s 秒后重试（可能所有URL都不可用）",
                consecutive_failures,
                backoff_time
            )
            time.sleep(backoff_time)
            # 重置失败计数，给一次机会
            stats.record_success()

        # 定期输出统计信息（仅在无限模式或还未达到目标时）
        current_time = time.time()
        if current_time - last_log_time >= log_interval:
            if goal == 0 or current_bytes < goal:
                speed_mbps = ((current_bytes - last_bytes) * 8 / (1024 * 1024)) / log_interval
                logging.info(
                    "运行状态 - 活跃线程: %s/%s, 已下载: %.2f GB, 速度: %.2f Mbps",
                    current_running,
                    thread_count,
                    current_bytes / (1024 * 1024 * 1024),
                    speed_mbps
                )
                last_log_time = current_time
                last_bytes = current_bytes

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
    # Python 3.9+ 支持 cancel_futures 参数
    import sys
    if sys.version_info >= (3, 9):
        executor.shutdown(wait=True, cancel_futures=True)
    else:
        executor.shutdown(wait=True)

    # 关闭 HTTP Session 释放连接
    logging.info("正在关闭 HTTP 会话...")
    try:
        session.close()
    except Exception as e:
        logging.warning("关闭 HTTP 会话时出错: %s", e)

    # 输出最终统计
    final_bytes = stats.get_bytes_downloaded()
    if final_bytes > 0:
        logging.info(
            "程序已退出 - 总流量: %.2f GB (%.2f MB)",
            final_bytes / (1024 * 1024 * 1024),
            final_bytes / (1024 * 1024)
        )
    else:
        logging.info("程序已退出 - 未下载任何数据")
